"""Run the frozen paired BabyAI/MiniGrid partial-provenance experiment."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.confidence_aware_dcta import confidence_aware_decision
from mcx.prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld, run_latent_policy


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "babyai_minigrid_partial_provenance_freeze_v1.json"
PROTOCOL = ROOT / "docs" / "BABYAI_MINIGRID_PARTIAL_PROVENANCE_PROTOCOL_V1.md"
OUTPUT = ROOT / "reports" / "babyai_minigrid_partial_provenance_v1.json"
STRUCTURED = ("sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "source_ig",
              "static_risk", "oracle_source")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_seed(*parts: object) -> int:
    value = ":".join(map(str, parts))
    return int(hashlib.sha256(value.encode()).hexdigest()[:16], 16)


def opaque_lineages(archive: dict[str, Any], variants: tuple[str, ...]) -> tuple[
    dict[str, tuple[str, ...]], dict[str, str], tuple[tuple[str, ...], ...]
]:
    colors = tuple(archive["lineages"])
    lineages: dict[str, list[str]] = {color: [] for color in colors}
    private_to_opaque: dict[str, str] = {}
    by_depth = []
    for depth, variant in enumerate(variants):
        shuffled = list(colors)
        random.Random(stable_seed("opaque", archive["archive_id"], depth)).shuffle(shuffled)
        nodes = []
        for rank, color in enumerate(shuffled):
            node = f"m{depth}_{rank:02d}"
            private = f"{color}::{variant}"
            lineages[color].append(node)
            private_to_opaque[private] = node
            nodes.append(node)
        by_depth.append(tuple(sorted(nodes)))
    return ({color: tuple(nodes) for color, nodes in lineages.items()},
            private_to_opaque, tuple(by_depth))


def observed_edges(
    archive_id: str, lineages: dict[str, tuple[str, ...]], hidden: int,
) -> tuple[tuple[str, str], ...]:
    colors = tuple(lineages)
    edges = []
    for layer in range(3):
        rotation = stable_seed("mask", archive_id, hidden, layer) % len(colors)
        hidden_sources = {
            colors[(rotation + offset) % len(colors)] for offset in range(hidden)
        }
        for color in colors:
            if color in hidden_sources:
                continue
            left = color if layer == 0 else lineages[color][layer - 1]
            right = lineages[color][layer]
            edges.append((left, right))
    return tuple(sorted(edges))


def layer_options(
    parents: tuple[str, ...], children: tuple[str, ...], observed: tuple[tuple[str, str], ...],
) -> tuple[tuple[tuple[str, str], ...], ...]:
    fixed = tuple((left, right) for left, right in observed
                  if left in parents and right in children)
    used_parents = {left for left, _ in fixed}
    used_children = {right for _, right in fixed}
    missing_parents = tuple(node for node in parents if node not in used_parents)
    missing_children = tuple(node for node in children if node not in used_children)
    if len(missing_parents) != len(missing_children):
        raise ValueError("partial layer is not a one-to-one partial matching")
    return tuple(tuple(sorted(fixed + tuple(zip(missing_parents, order))))
                 for order in itertools.permutations(missing_children))


def build_posterior(
    colors: tuple[str, ...], by_depth: tuple[tuple[str, ...], ...],
    observed: tuple[tuple[str, str], ...], prior: dict[str, float],
) -> tuple[LatentSourcePosterior, int]:
    options = (
        layer_options(colors, by_depth[0], observed),
        layer_options(by_depth[0], by_depth[1], observed),
        layer_options(by_depth[1], by_depth[2], observed),
    )
    completion_count = math.prod(len(value) for value in options)
    counts: Counter[tuple[str, frozenset[str]]] = Counter()
    for first, second, third in itertools.product(*options):
        maps = [dict(first), dict(second), dict(third)]
        for source in colors:
            n0 = maps[0][source]
            n1 = maps[1][n0]
            n2 = maps[2][n1]
            counts[(source, frozenset((n0, n1, n2)))] += 1
    candidates = tuple(node for depth in by_depth for node in depth)
    worlds = tuple(
        LatentSourceWorld(source, affected, prior[source] * count / completion_count)
        for (source, affected), count in sorted(
            counts.items(), key=lambda item: (item[0][0], sorted(item[0][1]))
        )
        if prior[source] > 0.0
    )
    return LatentSourcePosterior(candidates, colors, worlds).normalize(), completion_count


def random_policy(
    posterior: LatentSourcePosterior, affected: frozenset[str], budget: int, seed: int,
) -> tuple[tuple[str, ...], LatentSourcePosterior]:
    rng = random.Random(seed)
    remaining = list(posterior.candidates)
    belief = posterior
    replayed = []
    for _ in range(budget):
        chosen = remaining.pop(rng.randrange(len(remaining)))
        replayed.append(chosen)
        updated = belief.condition(chosen, int(chosen in affected))
        if updated is not None:
            belief = updated
    return tuple(replayed), belief


def prediction(posterior: LatentSourcePosterior) -> str:
    values = posterior.source_probabilities()
    return min(posterior.source_ids, key=lambda source: (-values[source], source))


def quarantine(posterior: LatentSourcePosterior, capacity: int) -> tuple[str, ...]:
    return tuple(sorted(posterior.candidates,
                        key=lambda node: (-posterior.marginal(node), node))[:capacity])


def make_row(
    archive: dict[str, Any], condition: str, hidden: int, completion_count: int,
    posterior_worlds: int, method: str, budget: int, replicate: int | None,
    replayed: tuple[str, ...], final: LatentSourcePosterior,
    affected: frozenset[str], labels_by_node: dict[str, int], capacity: int,
    sc_mode: str | None,
) -> dict[str, Any]:
    labels = tuple(labels_by_node[node] for node in replayed)
    hits = len(set(replayed) & affected)
    removed = quarantine(final, capacity)
    removed_hits = len(set(removed) & affected)
    predicted = prediction(final)
    return {
        "archive_id": archive["archive_id"], "regime": archive["regime"],
        "condition": condition, "hidden_links_per_layer": hidden,
        "completion_count": completion_count, "posterior_worlds": posterior_worlds,
        "method": method, "budget": budget, "replicate": replicate,
        "replayed_ids": list(replayed), "labels": list(labels),
        "corrupt_discoveries": hits,
        "corrupt_descendant_recall": hits / len(affected),
        "audit_yield": hits / budget,
        "predicted_source": predicted,
        "source_identification_accuracy": float(predicted == archive["true_source"]),
        "true_source_probability": final.source_probabilities()[archive["true_source"]],
        "quarantined_ids": list(removed),
        "quarantine_precision": removed_hits / capacity,
        "quarantine_recall": removed_hits / len(affected),
        "clean_descendants_removed": capacity - removed_hits,
        "corrupt_descendants_left": len(affected) - removed_hits,
        "robot_recovery_success": float(removed_hits == len(affected)),
        "sc_mode": sc_mode,
    }


def aggregate(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    metrics = ("corrupt_discoveries", "corrupt_descendant_recall", "audit_yield",
               "source_identification_accuracy", "true_source_probability",
               "quarantine_precision", "quarantine_recall", "clean_descendants_removed",
               "corrupt_descendants_left", "robot_recovery_success")
    output = []
    for key, values in sorted(groups.items(), key=lambda item: str(item[0])):
        record = {name: value for name, value in zip(keys, key)}
        record["runs"] = len(values)
        for metric in metrics:
            record[f"mean_{metric}"] = statistics.fmean(float(row[metric]) for row in values)
        output.append(record)
    return output


def selected_mean(rows: list[dict[str, Any]], method: str, metric: str) -> float:
    values = [float(row[metric]) for row in rows if row["method"] == method
              and row["budget"] == 4 and row["condition"] != "complete"]
    return statistics.fmean(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    base_path = ROOT / config["base_report"]
    if digest(base_path) != config["base_report_sha256"]:
        raise ValueError("frozen base report hash mismatch")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    if base["decision"] != "GO" or len(base["archives"]) != 60:
        raise ValueError("verified 60-archive base result required")
    variants = ("nearest", "farthest", "middle")
    budgets = tuple(map(int, config["budgets"]))
    capacity = int(config["quarantine_capacity"])
    rows = []
    views = []
    started = time.perf_counter()

    for archive_index, archive in enumerate(base["archives"]):
        colors = tuple(archive["lineages"])
        lineages, private_to_opaque, by_depth = opaque_lineages(archive, variants)
        affected = frozenset(private_to_opaque[node] for node in archive["affected_ids"])
        labels = {
            private_to_opaque[node]: int(not value["success"])
            for node, value in archive["replay_map"].items()
        }
        if {node for node, label in labels.items() if label} != set(affected):
            raise RuntimeError("opaque replay labels disagree with true lineage")
        truth = LatentSourceWorld(archive["true_source"], affected, 1.0)
        for condition, specification in config["provenance_conditions"].items():
            hidden = int(specification["hidden_links_per_layer"])
            observed = observed_edges(archive["archive_id"], lineages, hidden)
            posterior, completions = build_posterior(
                colors, by_depth, observed, archive["source_prior"]
            )
            weights = {node: 1.0 for node in posterior.candidates}
            views.append({
                "archive_id": archive["archive_id"], "condition": condition,
                "observed_edges": [list(edge) for edge in observed],
                "observed_edge_count": len(observed), "hidden_edge_count": 18 - len(observed),
                "completion_count": completions, "posterior_world_count": len(posterior.worlds),
            })
            for budget in budgets:
                for method in STRUCTURED:
                    sc_mode = None
                    if method == "sc_dcta":
                        decision = confidence_aware_decision(posterior, budget, weights)
                        sc_mode = decision.mode
                        effective = "top1_dcta" if decision.mode == "hard" else "prob_dcta"
                        outcome = run_latent_policy(
                            posterior, truth, budget, method=effective, weights=weights)
                    elif method == "hard_source_dcta":
                        outcome = run_latent_policy(
                            posterior, truth, budget, method="top1_dcta", weights=weights)
                    elif method == "oracle_source":
                        restricted = posterior.restrict_source(archive["true_source"])
                        outcome = run_latent_policy(
                            restricted, truth, budget, method="prob_dcta", weights=weights)
                    else:
                        outcome = run_latent_policy(
                            posterior, truth, budget, method=method, weights=weights)
                    rows.append(make_row(
                        archive, condition, hidden, completions, len(posterior.worlds),
                        method, budget, None, outcome.replayed_ids, outcome.final_posterior,
                        affected, labels, capacity, sc_mode))
                for replicate in range(int(config["random_replicates"])):
                    replayed, final = random_policy(
                        posterior, affected, budget,
                        stable_seed(config["random_seed"], archive["archive_id"],
                                    condition, budget, replicate))
                    rows.append(make_row(
                        archive, condition, hidden, completions, len(posterior.worlds),
                        "random", budget, replicate, replayed, final, affected, labels,
                        capacity, None))
        if (archive_index + 1) % 10 == 0:
            print(f"[archives] {archive_index + 1}/60", flush=True)

    structured_count = sum(row["method"] != "random" for row in rows)
    random_count = sum(row["method"] == "random" for row in rows)
    expected_structured = 60 * 3 * len(budgets) * len(STRUCTURED)
    expected_random = 60 * 3 * len(budgets) * int(config["random_replicates"])
    sc_primary = selected_mean(rows, "sc_dcta", "corrupt_descendant_recall")
    ens_primary = selected_mean(rows, "ens", "corrupt_descendant_recall")
    random_primary = selected_mean(rows, "random", "corrupt_descendant_recall")
    sc_recovery = selected_mean(rows, "sc_dcta", "robot_recovery_success")
    criteria = {
        "base_report_hash_verified": digest(base_path) == config["base_report_sha256"],
        "paired_views_complete": len(views) == 180,
        "structured_grid_complete": structured_count == expected_structured,
        "random_grid_complete": random_count == expected_random,
        "all_budgets_exact": all(len(row["replayed_ids"]) == row["budget"] for row in rows),
        "no_repeat_replays": all(len(row["replayed_ids"]) == len(set(row["replayed_ids"]))
                                 for row in rows),
        "sc_dcta_not_worse_than_ens_at_budget_4_partial_only": sc_primary >= ens_primary - 1e-12,
        "sc_dcta_better_than_random_at_budget_4_partial_only": sc_primary > random_primary + 1e-12,
        "sc_dcta_partial_recovery_at_budget_4_minimum": sc_recovery >= float(
            config["decision_criteria"]["sc_dcta_partial_recovery_at_budget_4_minimum"]),
    }
    integrity = all(value for key, value in criteria.items()
                    if not key.startswith("sc_dcta_"))
    decision = "GO" if all(criteria.values()) else "NO_GO"
    report = {
        "schema_version": "babyai-minigrid-partial-provenance-v1",
        "protocol": config["protocol"], "phase": config["phase"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "artifact_hashes": {"config": digest(args.config), "protocol": digest(PROTOCOL),
                            "runner": digest(Path(__file__)), "base_report": digest(base_path)},
        "counts": {"base_archives": 60, "paired_provenance_views": len(views),
                   "structured_method_runs": structured_count, "random_runs": random_count,
                   "total_method_runs": len(rows)},
        "criteria": criteria,
        "partial_budget_4_decision_metrics": {
            "sc_dcta_corrupt_descendant_recall": sc_primary,
            "ens_corrupt_descendant_recall": ens_primary,
            "random_corrupt_descendant_recall": random_primary,
            "sc_dcta_robot_recovery_success": sc_recovery,
            "sc_minus_ens": sc_primary - ens_primary,
            "sc_minus_random": sc_primary - random_primary,
        },
        "sc_mode_counts": dict(Counter(row["sc_mode"] for row in rows
                                        if row["method"] == "sc_dcta")),
        "summary": {
            "by_condition_method_budget": aggregate(rows, ("condition", "method", "budget")),
            "by_regime_condition_method_budget": aggregate(
                rows, ("regime", "condition", "method", "budget")),
        },
        "views": views, "rows": rows, "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision, "counts": report["counts"],
                      "partial_budget_4_decision_metrics": report[
                          "partial_budget_4_decision_metrics"],
                      "sc_mode_counts": report["sc_mode_counts"],
                      "criteria": criteria, "elapsed_s": report["elapsed_s"]}, indent=2))
    return 0 if integrity else 2


if __name__ == "__main__":
    raise SystemExit(main())
