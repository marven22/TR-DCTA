"""Integrity verifier for the AgentDojo external-baseline extension."""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
import math
import random
import statistics
from pathlib import Path

import _bootstrap  # noqa: F401

from run_agentdojo_tr_dcta_development_v1 import digest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "agentdojo_external_baselines_all97_v1.json"
OUTPUT = ROOT / "reports" / "agentdojo_external_baselines_all97_verified_v1.json"
CONFIG = ROOT / "configs" / "agentdojo_external_baselines_all97_freeze_v1.json"


def close(left, right):
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)


def descendants(root, edges):
    children = defaultdict(set)
    for left, right in edges:
        children[left].add(right)
    found, queue = {root}, deque([root])
    while queue:
        for child in children[queue.popleft()]:
            if child not in found:
                found.add(child)
                queue.append(child)
    return found - {root}


def percentile(values, probability):
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def clustered_interval(rows, method, condition, metric, suites, draws, seed):
    grouped = defaultdict(list)
    for row in rows:
        if row["method"] == method and row["condition"] == condition:
            grouped[row["archive_id"]].append(float(row[metric]))
    values = {key: statistics.fmean(items) for key, items in grouped.items()}
    by_suite = defaultdict(list)
    for archive_id in sorted(values):
        by_suite[suites[archive_id]].append(archive_id)
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        draw = []
        for suite in sorted(by_suite):
            members = by_suite[suite]
            draw.extend(values[rng.choice(members)] for _ in members)
        samples.append(statistics.fmean(draw))
    samples.sort()
    return statistics.fmean(values.values()), percentile(samples, .025), percentile(samples, .975)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    source_path = ROOT / config["source_report"]
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_config = json.loads(
        (ROOT / "configs" / "agentdojo_tr_dcta_all97_freeze_v1.json").read_text()
    )
    archives = {item["archive_id"]: item for item in source["archives"]}
    instances = {item["instance_id"]: item for item in source["instances"]}
    views = {
        (item["instance_id"], item["condition"], item["mask_replicate"]): item
        for item in source["views"]
    }
    failures = []
    acquisition = defaultdict(dict)

    for index, row in enumerate(report["graph_rows"]):
        instance = instances[row["instance_id"]]
        archive = archives[row["archive_id"]]
        affected = set(instance["affected_ids"])
        replayed = list(row["replayed_ids"])
        replayed_set = set(replayed)
        quarantined = set(row["quarantined_ids"])
        weights = {
            node: float(source_config["stage_harm_weights"][stage])
            for stage, layer in enumerate(archive["by_depth"]) for node in layer
        }
        total = sum(weights[node] for node in affected)
        expected = {
            "effective_budget": min(int(row["budget"]), len(weights)),
            "labels": [int(node in affected) for node in replayed],
            "corrupt_discoveries": len(replayed_set & affected),
            "weighted_discovery_recall": sum(
                weights[node] for node in replayed_set & affected
            ) / total,
            "quarantine_recall": len(quarantined & affected) / len(affected),
            "weighted_quarantine_recall": sum(
                weights[node] for node in quarantined & affected
            ) / total,
            "clean_descendants_removed": len(quarantined - affected),
            "corrupt_descendants_left": len(affected - quarantined),
            "safe_recovery_success": float(
                affected.issubset(quarantined) and archive["clean_fallback_safe"]
            ),
        }
        if len(replayed) != len(replayed_set) or len(quarantined) != archive["depth"]:
            failures.append(("graph_cardinality", index))
        for key, value in expected.items():
            actual = row[key]
            if actual != value and not (
                isinstance(value, float) and close(actual, value)
            ):
                failures.append(("graph_metric", index, key))
        method = row["method"]
        terminal = "shared" if method.endswith("shared_terminal") else "native"
        root_rule = "known" if "known_root" in method else "signaled"
        key = (
            row["instance_id"], row["condition"], row["mask_replicate"],
            row["budget"], root_rule,
        )
        acquisition[key][terminal] = tuple(replayed)

    for key, pair in acquisition.items():
        if set(pair) != {"native", "shared"} or pair["native"] != pair["shared"]:
            failures.append(("terminal_acquisition_mismatch", key))

    for index, row in enumerate(report["memorepair_rows"]):
        instance = instances[row["instance_id"]]
        archive = archives[row["archive_id"]]
        view = views[(row["instance_id"], row["condition"], row["mask_replicate"])]
        affected = set(instance["affected_ids"])
        candidates = {
            node for layer in archive["by_depth"] for node in layer
        }
        repaired = set(row["repaired_ids"])
        expected_scope = descendants(
            row["root"], (tuple(edge) for edge in view["observed_edges"])
        ) & candidates
        if repaired != expected_scope:
            failures.append(("memorepair_scope", index))
        weights = {
            node: float(source_config["stage_harm_weights"][stage])
            for stage, layer in enumerate(archive["by_depth"]) for node in layer
        }
        total = sum(weights[node] for node in affected)
        expected = {
            "repair_operations": len(repaired),
            "normalized_repair_cost": len(repaired) / len(candidates),
            "repair_recall": len(repaired & affected) / len(affected),
            "weighted_repair_recall": sum(
                weights[node] for node in repaired & affected
            ) / total,
            "clean_descendants_repaired": len(repaired - affected),
            "corrupt_descendants_left": len(affected - repaired),
            "safe_recovery_success": float(
                affected.issubset(repaired) and archive["clean_fallback_safe"]
            ),
        }
        for key, value in expected.items():
            actual = row[key]
            if actual != value and not (
                isinstance(value, float) and close(actual, value)
            ):
                failures.append(("memorepair_metric", index, key))

    expected_graph_keys = 3201 * 2 * 2 * 3
    expected_repair_keys = 3201 * 2
    interval_failures = []
    suites = {key: value["suite"] for key, value in archives.items()}
    repair_metrics = (
        "repair_operations", "normalized_repair_cost", "repair_recall",
        "weighted_repair_recall", "clean_descendants_repaired",
        "corrupt_descendants_left", "safe_recovery_success",
    )
    intervals = report.get("memorepair_task_clustered_bootstrap", {})
    for condition_index, condition in enumerate(config["conditions"]):
        for method_index, method in enumerate((
            "memorepair_known_root", "memorepair_signaled_root"
        )):
            for metric_index, metric in enumerate(repair_metrics):
                expected = clustered_interval(
                    report["memorepair_rows"], method, condition, metric, suites,
                    int(config["bootstrap_draws"]),
                    int(config["bootstrap_seed"]) + 1000
                    + 100 * condition_index + 10 * method_index + metric_index,
                )
                actual = intervals[condition][method][metric]
                if not all(close(actual[key], value) for key, value in zip(
                    ("estimate", "lower_95", "upper_95"), expected
                )):
                    interval_failures.append((condition, method, metric))
    checks = {
        "report_complete": report.get("status") == "COMPLETE",
        "source_report_hash_exact": digest(source_path) == config["source_report_sha256"],
        "config_hash_exact": report["artifact_hashes"]["config"] == digest(CONFIG),
        "runner_hash_exact": report["artifact_hashes"]["runner"] == digest(
            ROOT / "scripts" / "run_agentdojo_external_baselines_all97_v1.py"
        ),
        "adapter_hash_exact": report["artifact_hashes"]["adapter"] == digest(
            ROOT / "src" / "mcx" / "agentdojo_external_baselines.py"
        ),
        "all_97_tasks": report["counts"]["official_tasks"] == len(archives) == 97,
        "all_3201_views": report["counts"]["posterior_views"] == len(views) == 3201,
        "graph_grid_exact": len(report["graph_rows"]) == expected_graph_keys,
        "memorepair_grid_exact": len(report["memorepair_rows"]) == expected_repair_keys,
        "memorepair_cluster_intervals_exact": not interval_failures,
        "all_rows_recomputed": not failures,
    }
    output = {
        "schema_version": "agentdojo-external-baselines-all97-v1-verification",
        "verified": all(checks.values()),
        "report_sha256": digest(args.report),
        "checks": checks,
        "failures": failures[:50],
        "interval_failures": interval_failures,
        "recomputed_graph_rows": len(report["graph_rows"]),
        "recomputed_memorepair_rows": len(report["memorepair_rows"]),
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if output["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
