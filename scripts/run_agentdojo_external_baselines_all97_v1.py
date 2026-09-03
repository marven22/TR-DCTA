"""Run Graph Active Search and MemoRepair on the frozen AgentDojo all-97 study."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import random
import statistics
import time
from pathlib import Path

import _bootstrap  # noqa: F401

from mcx.active_search_baselines import GraphActiveSearchParameters
from mcx.agentdojo_external_baselines import (
    PriorSafeGraphActiveSearch,
    native_graph_quarantine,
)
from mcx.agentdojo_method import condition_trace
from mcx.agentdojo_variable_depth import posterior
from mcx.memorepair import Artifact, plan_repair
from mcx.terminal_recovery_dcta import terminal_quarantine_decision
from run_agentdojo_tr_dcta_development_v1 import digest
from run_agentdojo_tr_dcta_heldout_v1 import (
    archive_values,
    stratified_paired_bootstrap,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "agentdojo_external_baselines_all97_freeze_v1.json"
OUTPUT = ROOT / "reports" / "agentdojo_external_baselines_all97_v1.json"


def graph_row(instance, archive, view, budget, method, replayed, quarantine, weights):
    affected = frozenset(instance["affected_ids"])
    replayed_set, quarantined = set(replayed), set(quarantine)
    total_harm = sum(weights[node] for node in affected)
    return {
        "archive_id": archive["archive_id"],
        "instance_id": instance["instance_id"],
        "suite": archive["suite"],
        "depth": archive["depth"],
        "condition": view["condition"],
        "mask_replicate": view["mask_replicate"],
        "method": method,
        "budget": budget,
        "effective_budget": min(budget, len(weights)),
        "replayed_ids": list(replayed),
        "labels": [int(node in affected) for node in replayed],
        "quarantined_ids": list(quarantine),
        "corrupt_discoveries": len(replayed_set & affected),
        "weighted_discovery_recall": sum(
            weights[node] for node in replayed_set & affected
        ) / total_harm,
        "quarantine_recall": len(quarantined & affected) / len(affected),
        "weighted_quarantine_recall": sum(
            weights[node] for node in quarantined & affected
        ) / total_harm,
        "clean_descendants_removed": len(quarantined - affected),
        "corrupt_descendants_left": len(affected - quarantined),
        "safe_recovery_success": float(
            affected.issubset(quarantined) and archive["clean_fallback_safe"]
        ),
    }


def repair_row(instance, archive, view, method, root, repaired, weights):
    affected, repaired = frozenset(instance["affected_ids"]), frozenset(repaired)
    candidates = frozenset(weights)
    total_harm = sum(weights[node] for node in affected)
    return {
        "archive_id": archive["archive_id"],
        "instance_id": instance["instance_id"],
        "suite": archive["suite"],
        "depth": archive["depth"],
        "condition": view["condition"],
        "mask_replicate": view["mask_replicate"],
        "method": method,
        "root": root,
        "repaired_ids": sorted(repaired),
        "repair_operations": len(repaired),
        "normalized_repair_cost": len(repaired) / len(candidates),
        "repair_recall": len(repaired & affected) / len(affected),
        "weighted_repair_recall": sum(
            weights[node] for node in repaired & affected
        ) / total_harm,
        "clean_descendants_repaired": len((repaired & candidates) - affected),
        "corrupt_descendants_left": len(affected - repaired),
        "safe_recovery_success": float(
            affected.issubset(repaired) and archive["clean_fallback_safe"]
        ),
    }


def aggregate(rows, metrics, budgeted):
    groups = defaultdict(list)
    for row in rows:
        key = (row["condition"], row["method"])
        if budgeted:
            key += (row["budget"],)
        groups[key].append(row)
    output = []
    for key, values in sorted(groups.items(), key=lambda item: str(item[0])):
        record = {
            "condition": key[0], "method": key[1], "runs": len(values)
        }
        if budgeted:
            record["budget"] = key[2]
        for metric in metrics:
            record[f"mean_{metric}"] = statistics.fmean(
                float(row[metric]) for row in values
            )
        output.append(record)
    return output


def percentile(values, probability):
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def clustered_interval(rows, method, condition, metric, suites_by_archive, draws, seed):
    """Suite-stratified task bootstrap after averaging all within-task views."""
    grouped = defaultdict(list)
    for row in rows:
        if row["method"] == method and row["condition"] == condition:
            grouped[row["archive_id"]].append(float(row[metric]))
    archive_values = {
        archive_id: statistics.fmean(values)
        for archive_id, values in grouped.items()
    }
    by_suite = defaultdict(list)
    for archive_id in sorted(archive_values):
        by_suite[suites_by_archive[archive_id]].append(archive_id)
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        selected = []
        for suite in sorted(by_suite):
            members = by_suite[suite]
            selected.extend(
                archive_values[rng.choice(members)] for _ in members
            )
        samples.append(statistics.fmean(selected))
    samples.sort()
    return {
        "method": method,
        "condition": condition,
        "metric": metric,
        "archives": len(archive_values),
        "draws": draws,
        "estimate": statistics.fmean(archive_values.values()),
        "lower_95": percentile(samples, 0.025),
        "upper_95": percentile(samples, 0.975),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    source_path = ROOT / config["source_report"]
    verification_path = ROOT / config["source_verification"]
    if digest(source_path) != config["source_report_sha256"]:
        raise RuntimeError("frozen all-97 source report changed")
    if digest(verification_path) != config["source_verification_sha256"]:
        raise RuntimeError("frozen all-97 verification changed")
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if verification.get("verified") is not True:
        raise RuntimeError("source report is not independently verified")
    expected_hashes = config["implementation_hashes"]
    for relative, key in (
        ("src/mcx/active_search_baselines.py", "active_search_core"),
        ("src/mcx/memorepair.py", "memorepair_core"),
        ("src/mcx/agentdojo_external_baselines.py", "agentdojo_adapter"),
    ):
        if digest(ROOT / relative) != expected_hashes[key]:
            raise RuntimeError(f"frozen implementation changed: {relative}")

    started = time.perf_counter()
    source = json.loads(source_path.read_text(encoding="utf-8"))
    archives = {item["archive_id"]: item for item in source["archives"]}
    instances = {item["instance_id"]: item for item in source["instances"]}
    all97_config = json.loads(
        (ROOT / "configs" / "agentdojo_tr_dcta_all97_freeze_v1.json").read_text()
    )
    gas_spec = config["graph_active_search"]
    gas_parameters = GraphActiveSearchParameters(
        eta=float(gas_spec["eta"]),
        prior_strength=gas_spec["prior_strength"],
        prior_probability=float(gas_spec["prior_probability"]),
        alpha=float(gas_spec["alpha"]),
        tolerance=float(gas_spec["tolerance"]),
        max_iterations=int(gas_spec["max_iterations"]),
    )
    graph_rows, repair_rows = [], []
    budgets = tuple(int(value) for value in config["budgets"])
    for index, view in enumerate(source["views"]):
        instance = instances[view["instance_id"]]
        archive = archives[instance["archive_id"]]
        sources = tuple(sorted(archive["lineages"]))
        layers = tuple(tuple(layer) for layer in archive["by_depth"])
        candidates = tuple(node for layer in layers for node in layer)
        edges = tuple(tuple(edge) for edge in view["observed_edges"])
        depth = int(archive["depth"])
        weights = {
            node: float(all97_config["stage_harm_weights"][stage])
            for stage, layer in enumerate(layers) for node in layer
        }
        affected = frozenset(instance["affected_ids"])
        source_prior = {
            key: float(value) for key, value in instance["source_prior"].items()
        }
        signaled_root = min(sources, key=lambda node: (-source_prior[node], node))
        belief, _ = posterior(
            sources, layers, edges, source_prior, (1 / depth,) * depth
        )
        for root_label, graph_root in (
            ("known_root", instance["true_source"]),
            ("signaled_root", signaled_root),
        ):
            graph = PriorSafeGraphActiveSearch(
                sources + candidates, edges, {graph_root: 1}, gas_parameters
            )
            max_replayed, _, _ = graph.run(candidates, affected, max(budgets))
            for budget in budgets:
                effective = min(budget, len(candidates))
                replayed = max_replayed[:effective]
                labels = {graph_root: 1}
                labels.update({node: int(node in affected) for node in replayed})
                probabilities = graph.probabilities(labels)
                native = native_graph_quarantine(
                    candidates, probabilities, replayed, affected, depth
                )
                graph_rows.append(graph_row(
                    instance, archive, view, budget,
                    f"graph_active_search_{root_label}_native",
                    replayed, native, weights,
                ))
                final = condition_trace(belief, replayed, affected)
                shared = terminal_quarantine_decision(
                    final, weights, depth
                ).quarantined_ids
                graph_rows.append(graph_row(
                    instance, archive, view, budget,
                    f"graph_active_search_{root_label}_shared_terminal",
                    replayed, shared, weights,
                ))

        artifacts = {
            node: Artifact(
                node, value=float(config["memorepair"]["artifact_value"]),
                cost=float(config["memorepair"]["artifact_cost"]),
            ) for node in candidates
        }
        for method, root in (
            ("memorepair_known_root", instance["true_source"]),
            ("memorepair_signaled_root", signaled_root),
        ):
            plan = plan_repair(
                artifacts, edges, {root},
                lambda_cost=float(config["memorepair"]["lambda_cost"]),
                validation={node: True for node in candidates},
            )
            repair_rows.append(repair_row(
                instance, archive, view, method, root, plan.republished, weights
            ))
        if (index + 1) % 250 == 0:
            print(f"[external-baselines] evaluated {index + 1}/{len(source['views'])} views", flush=True)

    graph_metrics = (
        "corrupt_discoveries", "weighted_discovery_recall", "quarantine_recall",
        "weighted_quarantine_recall", "clean_descendants_removed",
        "corrupt_descendants_left", "safe_recovery_success",
    )
    repair_metrics = (
        "repair_operations", "normalized_repair_cost", "repair_recall",
        "weighted_repair_recall", "clean_descendants_repaired",
        "corrupt_descendants_left", "safe_recovery_success",
    )
    primary = int(config["primary_budget"])
    combined = [
        row for row in source["rows"]
        if row["method"] == "tr_dcta" and row["budget"] == primary
    ] + [row for row in graph_rows if row["budget"] == primary]
    suites_by_archive = {key: value["suite"] for key, value in archives.items()}
    comparisons = {}
    for condition_index, condition in enumerate(config["conditions"]):
        values = archive_values(combined, condition, primary, "safe_recovery_success")
        comparisons[condition] = {}
        for method_index, method in enumerate((
            "graph_active_search_known_root_native",
            "graph_active_search_known_root_shared_terminal",
            "graph_active_search_signaled_root_native",
            "graph_active_search_signaled_root_shared_terminal",
        )):
            comparisons[condition][method] = stratified_paired_bootstrap(
                values, suites_by_archive, "tr_dcta", method,
                int(config["bootstrap_draws"]),
                int(config["bootstrap_seed"]) + 10 * condition_index + method_index,
            )
    memorepair_intervals = {}
    for condition_index, condition in enumerate(config["conditions"]):
        memorepair_intervals[condition] = {}
        for method_index, method in enumerate((
            "memorepair_known_root", "memorepair_signaled_root"
        )):
            memorepair_intervals[condition][method] = {}
            for metric_index, metric in enumerate(repair_metrics):
                memorepair_intervals[condition][method][metric] = clustered_interval(
                    repair_rows, method, condition, metric, suites_by_archive,
                    int(config["bootstrap_draws"]),
                    int(config["bootstrap_seed"]) + 1000
                    + 100 * condition_index + 10 * method_index + metric_index,
                )

    report = {
        "schema_version": "agentdojo-external-baselines-all97-v1",
        "protocol": config["protocol"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE",
        "claim_boundary": "locked_posthoc_external_baseline_extension",
        "method_notes": {
            "graph_active_search_known_root_native": "privileged paper-native positive seed; native graph-score terminal",
            "graph_active_search_known_root_shared_terminal": "privileged paper-native seed; generous shared Bayesian terminal",
            "graph_active_search_signaled_root_native": "information-matched seed adaptation; native graph-score terminal",
            "graph_active_search_signaled_root_shared_terminal": "information-matched seed adaptation; generous shared Bayesian terminal",
            "memorepair_known_root": "privileged native known-invalid-root assumption; not budget matched",
            "memorepair_signaled_root": "information-matched root adaptation; not budget matched",
        },
        "counts": {
            "official_tasks": len(archives),
            "truth_instances": len(instances),
            "posterior_views": len(source["views"]),
            "graph_method_runs": len(graph_rows),
            "memorepair_method_runs": len(repair_rows),
        },
        "graph_summary": aggregate(graph_rows, graph_metrics, True),
        "memorepair_summary": aggregate(repair_rows, repair_metrics, False),
        "memorepair_task_clustered_bootstrap": memorepair_intervals,
        "paired_task_bootstrap_vs_tr_dcta_budget4": comparisons,
        "graph_rows": graph_rows,
        "memorepair_rows": repair_rows,
        "elapsed_s": time.perf_counter() - started,
        "artifact_hashes": {
            "config": digest(args.config),
            "runner": digest(Path(__file__)),
            "adapter": digest(ROOT / "src/mcx/agentdojo_external_baselines.py"),
            "source_report": digest(source_path),
            "source_verification": digest(verification_path),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "counts": report["counts"],
        "graph_summary": report["graph_summary"],
        "memorepair_summary": report["memorepair_summary"],
        "memorepair_task_clustered_bootstrap": report[
            "memorepair_task_clustered_bootstrap"
        ],
        "elapsed_s": report["elapsed_s"],
    }, indent=2))


if __name__ == "__main__":
    main()
