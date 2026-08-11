"""Run the frozen MemoRepair compatibility study on V6 task-matched archives."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import random

import _bootstrap

from mcx.memorepair import Artifact, plan_repair
from mcx.memoryarena_v6 import (
    DiscoveryCase,
    ObservableMemory,
    adaptive_replay,
    build_task_matched_cases,
    formation_contexts_for_unit,
    mask_edges_with_forced_hidden_direct,
    mask_observable_edges,
)


PROTOCOL_VERSION = "memoryarena-v6/memorepair-compatibility-v1"
LAMBDA = 0.3
FULL_REPLAY_COST = 49


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _logical_edges(case):
    return {
        (source, memory.memory_id)
        for memory in case.memories
        for source in (*memory.parent_memory_ids, *memory.exposed_memory_ids)
    }


def _add_spurious_edges(case, fraction, seed, complete_edges):
    possible = [
        (source.memory_id, target.memory_id)
        for source in case.memories
        for target in case.memories
        if source.created_at < target.created_at
        and (source.memory_id, target.memory_id) not in complete_edges
    ]
    possible.sort(key=lambda edge: hashlib.sha256(
        f"spurious|{seed}|{case.case_id}|{edge[0]}|{edge[1]}".encode()
    ).digest())
    target_count = math.ceil(fraction * len(complete_edges))
    added = set(possible[:target_count])
    memories = tuple(
        ObservableMemory(
            memory.memory_id,
            memory.content,
            memory.created_at,
            tuple(sorted(set(memory.parent_memory_ids) | {
                source for source, target in added if target == memory.memory_id
            })),
            memory.origin_case_id,
            memory.exposed_memory_ids,
            memory.formation_context,
        )
        for memory in case.memories
    )
    result = DiscoveryCase(
        f"{case.case_id}__spurious_{seed}", case.source_id, memories, case.affected_ids
    )
    result.validate()
    return result, added


def _artifacts(case, role_to_id):
    summaries = {
        opaque_id for role, opaque_id in role_to_id.items()
        if role.endswith(":m4") or role.endswith(":m6")
    }
    return {
        memory.memory_id: Artifact(
            memory.memory_id,
            kind="summary" if memory.memory_id in summaries else "record",
            replayable=memory.memory_id not in summaries,
            value=1.0,
            cost=1.0,
        )
        for memory in case.memories
    }


def _metrics(case, role_to_id, acis_result, hybrid=False):
    edges = _logical_edges(case)
    if hybrid:
        edges |= {(case.source_id, node) for node in acis_result["repaired_ids"]}
    plan = plan_repair(
        _artifacts(case, role_to_id), edges, {case.source_id}, LAMBDA
    )
    affected = set(case.affected_ids)
    scoped = set(plan.descendants)
    repaired = set(plan.republished) & affected
    selected_cost = sum(plan.candidates[node].cost for node in plan.selected)
    repair_all_cost = sum(
        candidate.cost for candidate in plan.candidates.values()
        if candidate.executable
    )
    return {
        "scope_recall": len(scoped & affected) / len(affected),
        "validated_repair_recall": len(repaired) / len(affected),
        "stale_leak": len(affected - scoped) / len(affected),
        "collateral_scope_count": len(scoped - affected),
        "collateral_scope_rate": len(scoped - affected) / len(scoped) if scoped else 0.0,
        "republished_count": len(plan.republished),
        "candidate_count": len(plan.candidates),
        "native_republication_rate": (
            len(plan.republished) / len(plan.candidates) if plan.candidates else 0.0
        ),
        "selected_operator_cost": selected_cost,
        "repair_all_operator_cost": repair_all_cost,
        "native_normalized_cost": (
            selected_cost / repair_all_cost if repair_all_cost else 0.0
        ),
        "end_to_end_operations": selected_cost + (13 if hybrid else 0),
        "end_to_end_cost_vs_full_replay": (
            selected_cost + (13 if hybrid else 0)
        ) / FULL_REPLAY_COST,
        "cascade_ids": sorted(plan.cascade),
        "selected_ids": sorted(plan.selected),
        "republished_ids": sorted(plan.republished),
    }


def _evaluate(case, metadata, condition, mask_seed, spurious_count=0):
    acis = adaptive_replay(case, 13, 42, use_exposure=True, use_trajectory=True)
    affected = set(case.affected_ids)
    acis_repaired = set(acis["repaired_ids"])
    return {
        "base_case_id": metadata["case_id"],
        "condition": condition,
        "mask_seed": mask_seed,
        "attack_type": metadata["attack_type"],
        "spurious_edge_count": spurious_count,
        "memorepair": _metrics(case, metadata["role_to_opaque_id"], acis),
        "acis_t": {
            "validated_repair_recall": len(acis_repaired & affected) / len(affected),
            "precision": len(acis_repaired & affected) / len(acis_repaired) if acis_repaired else 0.0,
            "replay_cost": len(acis["replayed_ids"]),
            "end_to_end_cost_vs_full_replay": len(acis["replayed_ids"]) / FULL_REPLAY_COST,
            "replayed_ids": acis["replayed_ids"],
            "repaired_ids": acis["repaired_ids"],
        },
        "hybrid": _metrics(case, metadata["role_to_opaque_id"], acis, hybrid=True),
    }


def _bootstrap_difference(rows, left, right, seed=42, draws=10000):
    by_archive = {}
    for row in rows:
        left_value = row[left]["validated_repair_recall"]
        right_value = row[right]["validated_repair_recall"]
        by_archive.setdefault(row["base_case_id"], []).append(left_value - right_value)
    archive_values = [_mean(by_archive[key]) for key in sorted(by_archive)]
    rng = random.Random(seed)
    samples = sorted(
        _mean(archive_values[rng.randrange(len(archive_values))] for _ in archive_values)
        for _ in range(draws)
    )
    return {
        "estimate": _mean(archive_values),
        "lower": samples[int(0.025 * draws)],
        "upper": samples[int(0.975 * draws) - 1],
        "archive_count": len(archive_values),
    }


def _aggregate(rows):
    output = {}
    for condition in sorted({row["condition"] for row in rows}):
        subset = [row for row in rows if row["condition"] == condition]
        methods = {}
        for method in ("memorepair", "acis_t", "hybrid"):
            methods[method] = {
                key: _mean(row[method][key] for row in subset)
                for key in row_keys(method)
            }
            if method != "acis_t":
                republished = sum(row[method]["republished_count"] for row in subset)
                candidates = sum(row[method]["candidate_count"] for row in subset)
                selected_cost = sum(
                    row[method]["selected_operator_cost"] for row in subset
                )
                repair_all_cost = sum(
                    row[method]["repair_all_operator_cost"] for row in subset
                )
                methods[method]["native_micro_republication_rate"] = (
                    republished / candidates if candidates else 0.0
                )
                methods[method]["native_micro_normalized_cost"] = (
                    selected_cost / repair_all_cost if repair_all_cost else 0.0
                )
        output[condition] = {
            "case_mask_pairs": len(subset),
            "methods": methods,
            "paired_recall_difference_95": {
                "memorepair_minus_acis_t": _bootstrap_difference(
                    subset, "memorepair", "acis_t"
                ),
                "hybrid_minus_acis_t": _bootstrap_difference(
                    subset, "hybrid", "acis_t"
                ),
            },
        }
    return output


def row_keys(method):
    common = ("validated_repair_recall", "end_to_end_cost_vs_full_replay")
    if method == "acis_t":
        return common + ("precision", "replay_cost")
    return common + (
        "scope_recall", "stale_leak", "collateral_scope_count",
        "collateral_scope_rate", "selected_operator_cost",
        "end_to_end_operations",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation-dir", required=True)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    generation_dir = os.path.abspath(args.generation_dir)
    summary = _read(os.path.join(generation_dir, "generation_summary.json"))
    attack_dir = summary["manifest"]["source_attack_dir"]
    units = [
        _read(os.path.join(generation_dir, "units", name))
        for name in sorted(os.listdir(os.path.join(generation_dir, "units")))
        if name.endswith(".json")
    ]
    contexts = {
        unit["unit_id"]: formation_contexts_for_unit(
            unit, _read(os.path.join(attack_dir, "units", f"{unit['unit_id']}.json"))
        )
        for unit in units
    }
    constructed = build_task_matched_cases(units, contexts)
    rows = []
    for base_case, metadata in constructed:
        rows.append(_evaluate(base_case, metadata, "complete", None))
        for fraction in (0.25, 0.50, 0.75, 1.00):
            for seed in range(10):
                masked, _ = mask_observable_edges(base_case, fraction, seed)
                rows.append(_evaluate(masked, metadata, f"mcar_{int(fraction*100)}", seed))
        for seed in range(10):
            masked, _ = mask_edges_with_forced_hidden_direct(
                base_case, 0.75, seed, metadata["direct_child_id"]
            )
            rows.append(_evaluate(masked, metadata, "forced_direct_plus_75", seed))
            noisy, added = _add_spurious_edges(
                masked, 0.25, seed, _logical_edges(base_case)
            )
            rows.append(_evaluate(
                noisy, metadata, "forced_direct_plus_75_spurious_25", seed, len(added)
            ))
    aggregate = {
        "protocol_version": PROTOCOL_VERSION,
        "scientific_result": False,
        "implementation_label": "MemoRepair reimplementation; not authors' code",
        "paper_url": "https://arxiv.org/abs/2605.07242",
        "lambda": LAMBDA,
        "candidate_value_cost_adapter": "uniform w_i=1, c_i=1",
        "archive_count": len(constructed),
        "archive_size": 50,
        "full_replay_cost": FULL_REPLAY_COST,
        "conditions": _aggregate(rows),
        "run": {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_generation_dir": generation_dir,
        },
    }
    output_dir = os.path.abspath(
        args.output_dir or os.path.join(_bootstrap.RESULTS_DIR, "memoryarena_v6_memorepair")
    )
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "cases.json"), "w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2)
    with open(os.path.join(output_dir, "aggregate.json"), "w", encoding="utf-8") as handle:
        json.dump(aggregate, handle, indent=2)
    print(json.dumps(aggregate, indent=2))
    print(f"results: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
