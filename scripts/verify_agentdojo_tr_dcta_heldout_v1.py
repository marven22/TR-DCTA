"""Independently verify the frozen AgentDojo method-held-out report."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
from typing import Any

import _bootstrap  # noqa: F401

from mcx.agentdojo_adapter import load_official_suites, replay_workflow


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "agentdojo_tr_dcta_heldout_v1.json"
OUTPUT = ROOT / "reports" / "agentdojo_tr_dcta_heldout_verified_v1.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], probability: float) -> float:
    values = sorted(values)
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def recompute_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["condition"], row["method"], row["budget"])].append(row)
    metrics = (
        "corrupt_discoveries", "weighted_discovery_recall",
        "source_identification_accuracy", "quarantine_recall",
        "weighted_quarantine_recall", "clean_descendants_removed",
        "corrupt_descendants_left", "safe_recovery_success",
    )
    output = []
    for key, values in sorted(groups.items(), key=lambda pair: str(pair[0])):
        record = {"condition": key[0], "method": key[1], "budget": key[2], "runs": len(values)}
        for metric in metrics:
            record[f"mean_{metric}"] = statistics.fmean(float(row[metric]) for row in values)
        output.append(record)
    return output


def archive_values(rows: list[dict[str, Any]], condition: str, budget: int, metric: str):
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["condition"] == condition and row["budget"] == budget:
            groups[(row["archive_id"], row["method"])].append(float(row[metric]))
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for (archive_id, method), values in groups.items():
        output[archive_id][method] = statistics.fmean(values)
    return dict(output)


def paired_bootstrap(values, suites, left, right, draws, seed):
    by_suite = defaultdict(list)
    for archive_id in sorted(values):
        by_suite[suites[archive_id]].append(archive_id)
    differences = {key: values[key][left] - values[key][right] for key in values}
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        draw = []
        for suite in sorted(by_suite):
            members = by_suite[suite]
            draw.extend(differences[rng.choice(members)] for _ in members)
        samples.append(statistics.fmean(draw))
    return {
        "left": left, "right": right, "archives": len(values), "draws": draws,
        "mean_difference": statistics.fmean(differences.values()),
        "lower_95": percentile(samples, .025), "upper_95": percentile(samples, .975),
        "wins": sum(value > 1e-12 for value in differences.values()),
        "ties": sum(abs(value) <= 1e-12 for value in differences.values()),
        "losses": sum(value < -1e-12 for value in differences.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    config_path = ROOT / "configs" / "agentdojo_tr_dcta_heldout_freeze_v1.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if os.environ.get("PYTHONHASHSEED") != config["python_hash_seed"]:
        raise RuntimeError(f"PYTHONHASHSEED must equal {config['python_hash_seed']}")
    checks = {
        "report_complete": report["status"] == "COMPLETE",
        "config_hash_exact": report["artifact_hashes"]["config"] == digest(config_path),
        "runner_hash_exact": report["artifact_hashes"]["runner"] == digest(
            ROOT / "scripts" / "run_agentdojo_tr_dcta_heldout_v1.py"
        ),
        "reported_integrity_all_true": all(report["integrity"].values()),
    }
    files = {
        "terminal_recovery_method": ROOT / "src" / "mcx" / "terminal_recovery_dcta.py",
        "agentdojo_method": ROOT / "src" / "mcx" / "agentdojo_method.py",
        "agentdojo_adapter": ROOT / "src" / "mcx" / "agentdojo_adapter.py",
        "development_runner": ROOT / "scripts" / "run_agentdojo_tr_dcta_development_v1.py",
    }
    checks["all_frozen_source_hashes_exact"] = all(
        report["artifact_hashes"][name] == digest(path) for name, path in files.items()
    )

    archives = {archive["archive_id"]: archive for archive in report["archives"]}
    instances = {instance["instance_id"]: instance for instance in report["instances"]}
    development = json.loads((ROOT / config["development_report"]).read_text(encoding="utf-8"))
    development_users = {(a["suite"], a["user_task_id"]) for a in development["archives"]}
    checks["no_development_user_overlap_recomputed"] = all(
        (archive["suite"], archive["user_task_id"]) not in development_users
        for archive in archives.values()
    )
    partial_patterns = defaultdict(set)
    for view in report["views"]:
        if view["condition"] == "partial_67":
            archive_id = instances[view["instance_id"]]["archive_id"]
            partial_patterns[archive_id].add(tuple(tuple(edge) for edge in view["observed_edges"]))
    checks["five_distinct_masks_recomputed"] = (
        len(partial_patterns) == 32 and all(len(patterns) == 5 for patterns in partial_patterns.values())
    )

    factual_failures = []
    for row_index, row in enumerate(report["rows"]):
        archive = archives[row["archive_id"]]
        affected = set(instances[row["instance_id"]]["affected_ids"])
        replayed = set(row["replayed_ids"])
        quarantine = set(row["quarantined_ids"])
        weights = {
            node: float(config["stage_harm_weights"][depth])
            for depth, layer in enumerate(archive["by_depth"]) for node in layer
        }
        total = sum(weights[node] for node in affected)
        expected = {
            "labels": [int(node in affected) for node in row["replayed_ids"]],
            "corrupt_discoveries": len(replayed & affected),
            "weighted_discovery_recall": sum(weights[node] for node in replayed & affected) / total,
            "quarantine_recall": len(quarantine & affected) / len(affected),
            "weighted_quarantine_recall": sum(weights[node] for node in quarantine & affected) / total,
            "clean_descendants_removed": len(quarantine - affected),
            "corrupt_descendants_left": len(affected - quarantine),
            "safe_recovery_success": float(affected.issubset(quarantine) and archive["clean_fallback_safe"]),
        }
        for field, expected_value in expected.items():
            actual = row[field]
            exact = actual == expected_value if not isinstance(expected_value, float) else math.isclose(actual, expected_value, abs_tol=1e-12)
            if not exact:
                factual_failures.append({"row": row_index, "field": field, "expected": expected_value, "actual": actual})
    checks["all_rows_recomputed"] = not factual_failures
    checks["summary_recomputed_exactly"] = recompute_summary(report["rows"]) == report["summary"]

    suites_by_archive = {key: value["suite"] for key, value in archives.items()}
    primary = {}
    comparisons = {}
    for metric_index, metric in enumerate(config["primary_estimands"]):
        values = archive_values(report["rows"], config["primary_condition"], int(config["primary_budget"]), metric)
        primary[metric] = {
            method: statistics.fmean(methods[method] for methods in values.values())
            for method in config["methods"]
        }
        comparisons[metric] = {}
        for comparator_index, comparator in enumerate(config["primary_comparators"]):
            comparisons[metric][comparator] = paired_bootstrap(
                values, suites_by_archive, "tr_dcta", comparator,
                int(config["bootstrap_draws"]),
                int(config["bootstrap_seed"]) + 100 * metric_index + comparator_index,
            )
    checks["primary_estimates_recomputed_exactly"] = primary == report["primary_partial_67_budget4"]
    checks["bootstrap_recomputed_exactly"] = comparisons == report["paired_suite_stratified_archive_bootstrap"]

    suites = load_official_suites(config["benchmark_version"])
    execution_failures = []
    replay_count = 0
    core = (
        "utility", "attack_success", "safe_success", "error", "planned_call_count",
        "executed_call_count", "trace_digest", "semantic_environment_digest", "trace_functions",
    )
    for archive in report["archives"]:
        suite = suites[archive["suite"]]
        for node, record in archive["replay_map"].items():
            for polarity, variant in (("negative", "clean"), ("positive", record["variant"])):
                replay_count += 1
                fresh = replay_workflow(
                    suite, archive["user_task_id"], record["injection_task_id"], variant,
                    score_clean_against_injection=(variant == "clean"),
                ).to_dict()
                if not all(fresh[key] == record[polarity][key] for key in core):
                    execution_failures.append({
                        "archive_id": archive["archive_id"], "node": node, "polarity": polarity,
                    })
    checks["576_workflows_reexecuted"] = replay_count == 576
    checks["executable_replays_semantically_exact"] = not execution_failures
    verification = {
        "schema_version": "agentdojo-tr-dcta-method-heldout-v1-verification",
        "verified": all(checks.values()), "report_sha256": digest(args.report),
        "checks": checks, "factual_failures": factual_failures,
        "execution_failures": execution_failures,
        "recomputed_rows": len(report["rows"]), "reexecuted_workflows": replay_count,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, indent=2))
    return 0 if verification["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
