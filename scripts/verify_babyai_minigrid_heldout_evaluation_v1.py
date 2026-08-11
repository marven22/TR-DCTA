"""Verify the frozen BabyAI/MiniGrid held-out evaluation artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from run_babyai_minigrid_heldout_evaluation_v1 import (
    archive_method_means,
    paired_bootstrap,
)
from run_babyai_minigrid_partial_provenance_v1 import opaque_lineages, stable_seed


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "babyai_minigrid_heldout_evaluation_v1.json"
OUTPUT = ROOT / "reports" / "babyai_minigrid_heldout_evaluation_verified_v1.json"
CONFIG = ROOT / "configs" / "babyai_minigrid_heldout_evaluation_freeze_v1.json"
PROTOCOL = ROOT / "docs" / "BABYAI_MINIGRID_HELDOUT_EVALUATION_PROTOCOL_V1.md"
RUNNER = ROOT / "scripts" / "run_babyai_minigrid_heldout_evaluation_v1.py"
PARTIAL_RUNNER = ROOT / "scripts" / "run_babyai_minigrid_partial_provenance_v1.py"
PLANNER = ROOT / "scripts" / "run_babyai_minigrid_go_no_go_v1.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    archives = report["archives"]
    views = report["views"]
    rows = report["rows"]
    archive_ids = {archive["archive_id"] for archive in archives}
    seeds = {int(archive["target_seed"]) for archive in archives}
    true_nodes = {}
    for archive in archives:
        _, private_to_opaque, _ = opaque_lineages(
            archive, ("nearest", "farthest", "middle"))
        true_nodes[archive["archive_id"]] = {
            private_to_opaque[node] for node in archive["affected_ids"]
        }

    structured_keys = [(row["archive_id"], row["condition"], row["budget"], row["method"])
                       for row in rows if row["method"] != "random"]
    random_keys = [(row["archive_id"], row["condition"], row["budget"], row["replicate"])
                   for row in rows if row["method"] == "random"]
    row_truth_valid = all(
        row["archive_id"] in archive_ids
        and row["labels"] == [int(node in true_nodes[row["archive_id"]])
                              for node in row["replayed_ids"]]
        and math.isclose(float(row["corrupt_descendant_recall"]),
                         len(set(row["replayed_ids"]) & true_nodes[row["archive_id"]]) / 3,
                         abs_tol=1e-12)
        and math.isclose(float(row["quarantine_recall"]),
                         len(set(row["quarantined_ids"]) & true_nodes[row["archive_id"]]) / 3,
                         abs_tol=1e-12)
        and int(row["robot_recovery_success"]) == int(
            true_nodes[row["archive_id"]].issubset(row["quarantined_ids"]))
        for row in rows
    )

    expected_edges = {"complete": 18, "partial_33": 12, "partial_67": 6}
    expected_completions = {"complete": 1, "partial_33": 8, "partial_67": 13824}
    recomputed = []
    for condition in ("partial_33", "partial_67"):
        for metric_index, metric in enumerate(config["primary_estimands"]):
            values = archive_method_means(rows, condition, 4, metric)
            for comparison_index, comparison in enumerate(config["confirmatory_comparisons"]):
                value = paired_bootstrap(
                    values, comparison["left"], comparison["right"],
                    int(config["bootstrap"]["draws"]),
                    stable_seed(config["bootstrap"]["seed"], condition, metric,
                                comparison_index, metric_index),
                    float(config["noninferiority_margin"]), comparison["claim"])
                recomputed.append({"condition": condition, "budget": 4,
                                   "metric": metric, **value})
    comparison_valid = len(recomputed) == len(report["confirmatory_comparisons"]) and all(
        left == right for left, right in zip(recomputed, report["confirmatory_comparisons"])
    )

    checks = {
        "schema_and_status_valid": report["schema_version"]
        == "babyai-minigrid-heldout-evaluation-v1"
        and report["evaluation_status"] == "COMPLETE" and report["method_frozen"],
        "artifact_hashes_match": report["artifact_hashes"] == {
            "config": digest(CONFIG), "protocol": digest(PROTOCOL), "runner": digest(RUNNER),
            "partial_runner_dependency": digest(PARTIAL_RUNNER),
            "planner_dependency": digest(PLANNER)},
        "heldout_seeds_exact": seeds == set(range(60, 300)) and len(archives) == 240,
        "development_disjoint": not seeds.intersection(range(0, 60)),
        "regimes_balanced": Counter(a["regime"] for a in archives) == Counter(
            {name: 60 for name in config["confidence_regimes"]}),
        "environment_labels_valid": all(
            {node for node, value in archive["replay_map"].items() if not value["success"]}
            == set(archive["affected_ids"]) for archive in archives),
        "local_correctness_valid": len(report["local_checks"]) == 720
        and all(row["success"] for row in report["local_checks"]),
        "view_grid_and_masks_valid": len(views) == 720 and all(
            view["observed_edge_count"] == expected_edges[view["condition"]]
            and view["completion_count"] == expected_completions[view["condition"]]
            for view in views),
        "structured_grid_unique": len(structured_keys) == 15120
        and len(set(structured_keys)) == 15120,
        "random_grid_unique": len(random_keys) == 108000
        and len(set(random_keys)) == 108000,
        "row_truth_and_outcomes_valid": row_truth_valid,
        "budgets_exact_unique": all(len(row["replayed_ids"]) == row["budget"]
                                    and len(row["replayed_ids"]) == len(
                                        set(row["replayed_ids"])) for row in rows),
        "bootstrap_comparisons_reproduced": comparison_valid,
        "reported_integrity_all_true": all(report["integrity"].values()),
    }
    recovery_counts = {}
    for condition in config["provenance_conditions"]:
        recovery_counts[condition] = {}
        for budget in config["budgets"]:
            selected = [row for row in rows if row["method"] == "sc_dcta"
                        and row["condition"] == condition and row["budget"] == budget]
            recovery_counts[condition][str(budget)] = sum(
                int(row["robot_recovery_success"]) for row in selected)
    verified = all(checks.values())
    output = {
        "schema_version": "babyai-minigrid-heldout-evaluation-verification-v1",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "verified": verified, "report_sha256": digest(args.report),
        "checks": checks, "sc_dcta_recovery_counts_out_of_240": recovery_counts,
        "confirmatory_claims_passed": sum(
            int(row["claim_passed"]) for row in recomputed),
        "confirmatory_claims_total": len(recomputed),
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
