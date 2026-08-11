"""Verify the frozen BabyAI/MiniGrid partial-provenance experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from run_babyai_minigrid_partial_provenance_v1 import opaque_lineages


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "babyai_minigrid_partial_provenance_v1.json"
OUTPUT = ROOT / "reports" / "babyai_minigrid_partial_provenance_verified_v1.json"
CONFIG = ROOT / "configs" / "babyai_minigrid_partial_provenance_freeze_v1.json"
PROTOCOL = ROOT / "docs" / "BABYAI_MINIGRID_PARTIAL_PROVENANCE_PROTOCOL_V1.md"
RUNNER = ROOT / "scripts" / "run_babyai_minigrid_partial_provenance_v1.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_mean(rows: list[dict], method: str, metric: str) -> float:
    values = [float(row[metric]) for row in rows if row["method"] == method
              and row["budget"] == 4 and row["condition"] != "complete"]
    return statistics.fmean(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    base_path = ROOT / config["base_report"]
    base = json.loads(base_path.read_text(encoding="utf-8"))
    rows = report["rows"]
    views = report["views"]
    base_by_id = {archive["archive_id"]: archive for archive in base["archives"]}

    expected_edges = {"complete": 18, "partial_33": 12, "partial_67": 6}
    expected_completions = {"complete": 1, "partial_33": 8, "partial_67": 13824}
    expected_structured = 60 * 3 * 3 * 7
    expected_random = 60 * 3 * 3 * 50
    structured_keys = [(row["archive_id"], row["condition"], row["method"], row["budget"])
                       for row in rows if row["method"] != "random"]
    random_keys = [(row["archive_id"], row["condition"], row["budget"], row["replicate"])
                   for row in rows if row["method"] == "random"]

    true_nodes = {}
    for archive_id, archive in base_by_id.items():
        _, private_to_opaque, _ = opaque_lineages(
            archive, ("nearest", "farthest", "middle"))
        true_nodes[archive_id] = {
            private_to_opaque[node] for node in archive["affected_ids"]
        }
    label_checks = all(
        row["labels"] == [int(node in true_nodes[row["archive_id"]])
                          for node in row["replayed_ids"]]
        and math.isclose(
            float(row["corrupt_descendant_recall"]),
            len(set(row["replayed_ids"]) & true_nodes[row["archive_id"]]) / 3,
            abs_tol=1e-12)
        for row in rows
    )
    quarantine_checks = all(
        math.isclose(
            float(row["quarantine_recall"]),
            len(set(row["quarantined_ids"]) & true_nodes[row["archive_id"]]) / 3,
            abs_tol=1e-12)
        and float(row["robot_recovery_success"]) == float(
            true_nodes[row["archive_id"]].issubset(row["quarantined_ids"]))
        for row in rows
    )

    sc = selected_mean(rows, "sc_dcta", "corrupt_descendant_recall")
    ens = selected_mean(rows, "ens", "corrupt_descendant_recall")
    random_value = selected_mean(rows, "random", "corrupt_descendant_recall")
    recovery = selected_mean(rows, "sc_dcta", "robot_recovery_success")
    threshold = float(config["decision_criteria"][
        "sc_dcta_partial_recovery_at_budget_4_minimum"])
    recomputed_decision = "GO" if sc >= ens - 1e-12 and sc > random_value + 1e-12 \
        and recovery >= threshold else "NO_GO"

    checks = {
        "schema_valid": report["schema_version"] == "babyai-minigrid-partial-provenance-v1",
        "artifact_hashes_match": report["artifact_hashes"] == {
            "config": digest(CONFIG), "protocol": digest(PROTOCOL),
            "runner": digest(RUNNER), "base_report": digest(base_path)},
        "base_report_frozen": digest(base_path) == config["base_report_sha256"],
        "view_grid_complete": len(views) == 180 and Counter(
            view["condition"] for view in views) == Counter(
                {"complete": 60, "partial_33": 60, "partial_67": 60}),
        "mask_edge_counts_valid": all(view["observed_edge_count"] == expected_edges[
            view["condition"]] for view in views),
        "completion_counts_valid": all(view["completion_count"] == expected_completions[
            view["condition"]] for view in views),
        "structured_grid_complete": len(structured_keys) == expected_structured
        and len(set(structured_keys)) == expected_structured,
        "random_grid_complete": len(random_keys) == expected_random
        and len(set(random_keys)) == expected_random,
        "replay_labels_and_recall_valid": label_checks,
        "quarantine_and_recovery_valid": quarantine_checks,
        "budgets_exact_and_unique": all(len(row["replayed_ids"]) == row["budget"]
                                        and len(row["replayed_ids"]) == len(
                                            set(row["replayed_ids"])) for row in rows),
        "decision_metrics_match": all((
            math.isclose(sc, report["partial_budget_4_decision_metrics"][
                "sc_dcta_corrupt_descendant_recall"], abs_tol=1e-12),
            math.isclose(ens, report["partial_budget_4_decision_metrics"][
                "ens_corrupt_descendant_recall"], abs_tol=1e-12),
            math.isclose(random_value, report["partial_budget_4_decision_metrics"][
                "random_corrupt_descendant_recall"], abs_tol=1e-12),
            math.isclose(recovery, report["partial_budget_4_decision_metrics"][
                "sc_dcta_robot_recovery_success"], abs_tol=1e-12))),
        "decision_recomputed": report["decision"] == recomputed_decision,
    }
    verified = all(checks.values())
    recovery_counts: dict[str, dict[str, int]] = defaultdict(dict)
    for condition in config["provenance_conditions"]:
        for budget in config["budgets"]:
            selected = [row for row in rows if row["method"] == "sc_dcta"
                        and row["condition"] == condition and row["budget"] == budget]
            recovery_counts[condition][str(budget)] = sum(
                int(row["robot_recovery_success"]) for row in selected)
    output = {
        "schema_version": "babyai-minigrid-partial-provenance-verification-v1",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "verified": verified, "report_sha256": digest(args.report),
        "checks": checks,
        "recomputed_partial_budget_4": {
            "sc_dcta_recall": sc, "ens_recall": ens, "random_recall": random_value,
            "sc_dcta_recovery": recovery, "decision": recomputed_decision},
        "sc_dcta_recovery_counts_out_of_60": recovery_counts,
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
