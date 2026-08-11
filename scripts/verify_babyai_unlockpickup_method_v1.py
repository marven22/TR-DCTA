"""Independently verify an UnlockPickup stochastic-cascade method report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401

from run_babyai_unlockpickup_go_no_go_v1 import execute


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def partial_mean(rows: list[dict], method: str, metric: str, budget: int) -> float:
    values = [float(row[metric]) for row in rows if row["method"] == method
              and row["condition"] != "complete" and int(row["budget"]) == budget]
    return sum(values) / len(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    rows = report["rows"]
    archives = report["archives"]
    views = report["views"]
    archive_by_id = {archive["archive_id"]: archive for archive in archives}
    structured = tuple(method for method in config["methods"] if method != "random")
    archive_count = int(config["seed_stop_exclusive"]) - int(config["seed_start"])
    budgets = tuple(map(int, config["budgets"]))
    conditions = tuple(config["provenance_conditions"])
    expected_structured = archive_count * len(conditions) * len(budgets) * len(structured)
    expected_random = (archive_count * len(conditions) * len(budgets)
                       * int(config["random_replicates"]))

    structured_keys = [(row["archive_id"], row["condition"], int(row["budget"]),
                        row["method"]) for row in rows if row["method"] != "random"]
    random_keys = [(row["archive_id"], row["condition"], int(row["budget"]),
                    int(row["replicate"])) for row in rows if row["method"] == "random"]
    environment_truth_valid = all(
        (node in set(archive["affected_ids"])) == (not bool(value["success"]))
        for archive in archives for node, value in archive["replay_map"].items()
    )
    row_labels_valid = all(
        row["labels"] == [int(node in set(archive_by_id[row["archive_id"]]["affected_ids"]))
                          for node in row["replayed_ids"]] for row in rows
    )
    quarantine_metrics_valid = all(
        int(row["corrupt_descendants_left"]) == len(
            set(archive_by_id[row["archive_id"]]["affected_ids"])
            - set(row["quarantined_ids"])
        ) and bool(row["robot_recovery_success"]) == (
            set(archive_by_id[row["archive_id"]]["affected_ids"])
            <= set(row["quarantined_ids"])
        ) for row in rows
    )

    # Re-execute one active and one clean memory from every tenth archive.
    repeat_checks = []
    for archive in archives[::10]:
        for active in (True, False):
            node, cached = next((node, value) for node, value in archive["replay_map"].items()
                                if bool(value["active_corruption"]) == active)
            again = execute(config["env_id"], int(archive["seed"]),
                            cached["behavior_source"], cached["variant"])
            repeat_checks.append({
                "archive_id": archive["archive_id"], "node_id": node, "active": active,
                "success_match": bool(again["success"]) == bool(cached["success"]),
                "steps_match": int(again["steps"]) == int(cached["steps"]),
                "milestones_match": again["milestones"] == cached["milestones"],
            })

    primary = int(config["primary_budget"])
    margin = float(config["development_gate"]["noninferiority_margin"])
    metrics = {method: {
        "weighted_recall": partial_mean(rows, method, "weighted_corrupt_recall", primary),
        "recovery": partial_mean(rows, method, "robot_recovery_success", primary),
    } for method in ("sc_dcta", "ens", "random")}
    gates = {
        "sc_weighted_recall_noninferior_to_ens_partial_budget4":
            metrics["sc_dcta"]["weighted_recall"] >= metrics["ens"]["weighted_recall"] - margin,
        "sc_recovery_noninferior_to_ens_partial_budget4":
            metrics["sc_dcta"]["recovery"] >= metrics["ens"]["recovery"] - margin,
        "sc_weighted_recall_better_than_random_partial_budget4":
            metrics["sc_dcta"]["weighted_recall"] > metrics["random"]["weighted_recall"],
    }
    expected_decision = "GO" if all(gates.values()) else "NO_GO"
    checks = {
        "schema_valid": report["schema_version"] == "babyai-unlockpickup-method-v1",
        "frozen_hashes_match": report["artifact_hashes"] == {
            "config": digest(args.config),
            "runner": digest(ROOT / "scripts" / "run_babyai_unlockpickup_method_v1.py"),
            "go_no_go_report": digest(ROOT / config["go_no_go_report"]),
        },
        "archive_count_exact": len(archives) == archive_count,
        "seed_set_exact": {int(a["seed"]) for a in archives}
        == set(range(int(config["seed_start"]), int(config["seed_stop_exclusive"]))),
        "cascade_lengths_balanced": Counter(a["true_cascade_length"] for a in archives)
        == Counter({1: archive_count // 3, 2: archive_count // 3, 3: archive_count // 3}),
        "views_complete": len(views) == archive_count * len(conditions),
        "environment_truth_valid": environment_truth_valid,
        "structured_grid_complete": len(structured_keys) == expected_structured
        and len(set(structured_keys)) == expected_structured,
        "random_grid_complete": len(random_keys) == expected_random
        and len(set(random_keys)) == expected_random,
        "row_labels_valid": row_labels_valid,
        "quarantine_metrics_valid": quarantine_metrics_valid,
        "budgets_exact": all(len(row["replayed_ids"]) == int(row["budget"]) for row in rows),
        "replays_unique": all(len(row["replayed_ids"]) == len(set(row["replayed_ids"]))
                              for row in rows),
        "repeat_executions_exact": all(all((row["success_match"], row["steps_match"],
                                                   row["milestones_match"]))
                                       for row in repeat_checks),
        "primary_metrics_recomputed": all(
            math.isclose(metrics[method][metric],
                         report["decision_metrics_partial_budget4"][method][metric],
                         abs_tol=1e-12)
            for method in metrics for metric in metrics[method]
        ),
        "gate_recomputed": gates == report["development_gate"],
        "decision_recomputed": report["decision"] == expected_decision,
    }
    output = {
        "schema_version": "babyai-unlockpickup-method-verification-v1",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "verified": all(checks.values()), "report_sha256": digest(args.report),
        "checks": checks, "recomputed_metrics": metrics,
        "recomputed_gate": gates, "recomputed_decision": expected_decision,
        "repeat_checks": repeat_checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if output["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
