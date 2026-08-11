"""Independently verify the frozen UnlockPickup TR-DCTA development report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401

from mcx.terminal_recovery_dcta import terminal_quarantine_decision
from run_babyai_minigrid_partial_provenance_v1 import opaque_lineages
from run_babyai_unlockpickup_method_v1 import (
    build_stochastic_posterior, condition_trace,
)


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
    input_path = ROOT / config["input_report"]
    source = json.loads(input_path.read_text(encoding="utf-8"))
    rows = report["rows"]
    source_rows = {(r["archive_id"], r["condition"], r["method"], r["budget"], r["replicate"]): r
                   for r in source["rows"]}
    archives = {a["archive_id"]: a for a in source["archives"]}
    views = {(v["archive_id"], v["condition"]): v for v in source["views"]}
    methods = tuple(config["methods"])
    budgets = tuple(map(int, config["budgets"]))
    conditions = ("complete", "partial_33", "partial_67")
    structured = tuple(method for method in methods if method != "random")
    expected_structured = 60 * len(conditions) * len(budgets) * len(structured)
    expected_random = 60 * len(conditions) * len(budgets) * 50
    structured_keys = [(r["archive_id"], r["condition"], r["method"], r["budget"])
                       for r in rows if r["method"] != "random"]
    random_keys = [(r["archive_id"], r["condition"], r["budget"], r["replicate"])
                   for r in rows if r["method"] == "random"]

    baseline_trajectories_unchanged = all(
        r["replayed_ids"] == source_rows[(r["archive_id"], r["condition"], r["method"],
                                          r["budget"], r["replicate"])]["replayed_ids"]
        for r in rows if r["method"] != "tr_dcta"
    )
    labels_valid = all(
        r["labels"] == [int(node in set(archives[r["archive_id"]]["affected_ids"]))
                        for node in r["replayed_ids"]] for r in rows
    )
    outcome_accounting_valid = all(
        int(r["corrupt_descendants_left"]) == len(
            set(archives[r["archive_id"]]["affected_ids"]) - set(r["quarantined_ids"])
        ) and bool(r["robot_recovery_success"]) == (
            set(archives[r["archive_id"]]["affected_ids"]) <= set(r["quarantined_ids"])
        ) for r in rows
    )

    # Independently reconstruct twelve primary TR-DCTA terminal beliefs and
    # exhaustively optimize their capacity-three quarantine decisions.
    colors = tuple(config["colors"])
    variants = tuple(config["variants"])
    lengths = tuple(map(float, config["cascade_length_prior"]))
    stage_weights = tuple(map(float, config["stage_harm_weights"]))
    samples = []
    sampled_archives = list(archives.values())[::10]
    for archive in sampled_archives:
        _, mapping, by_depth = opaque_lineages(archive, variants)
        weights = {mapping[f"{color}::{variant}"]: stage_weights[depth]
                   for color in colors for depth, variant in enumerate(variants)}
        affected = frozenset(archive["affected_ids"])
        for condition in ("partial_33", "partial_67"):
            view = views[(archive["archive_id"], condition)]
            posterior, _ = build_stochastic_posterior(
                colors, by_depth, tuple(map(tuple, view["observed_edges"])),
                archive["source_prior"], lengths,
            )
            saved = next(r for r in rows if r["archive_id"] == archive["archive_id"]
                         and r["condition"] == condition and r["method"] == "tr_dcta"
                         and r["budget"] == 4)
            final = condition_trace(posterior, tuple(saved["replayed_ids"]), affected)
            decision = terminal_quarantine_decision(
                final, weights, int(config["quarantine_capacity"]),
            )
            samples.append({
                "archive_id": archive["archive_id"], "condition": condition,
                "quarantine_match": list(decision.quarantined_ids) == saved["quarantined_ids"],
                "expected_recovery_match": math.isclose(
                    decision.value.recovery_probability,
                    float(saved["posterior_expected_recovery"]), abs_tol=1e-12),
                "expected_harm_match": math.isclose(
                    decision.value.expected_captured_harm,
                    float(saved["posterior_expected_captured_harm"]), abs_tol=1e-12),
            })

    primary = int(config["primary_budget"])
    selected_methods = ("tr_dcta", "sc_dcta", "prob_dcta", "hard_source_dcta",
                        "ens", "random", "oracle_source", "full_information_hindsight")
    metrics = {method: {
        "recovery": partial_mean(rows, method, "robot_recovery_success", primary),
        "weighted_quarantine_recall": partial_mean(
            rows, method, "weighted_quarantine_recall", primary),
        "weighted_discovery_recall": partial_mean(
            rows, method, "weighted_corrupt_recall", primary),
    } for method in selected_methods}
    margin = float(config["noninferiority_margin"])
    gates = {
        "tr_recovery_noninferior_to_ens":
            metrics["tr_dcta"]["recovery"] >= metrics["ens"]["recovery"] - margin,
        "tr_recovery_at_least_sc":
            metrics["tr_dcta"]["recovery"] >= metrics["sc_dcta"]["recovery"],
        "tr_weighted_quarantine_noninferior_to_ens":
            metrics["tr_dcta"]["weighted_quarantine_recall"]
            >= metrics["ens"]["weighted_quarantine_recall"] - margin,
        "tr_recovery_better_than_random":
            metrics["tr_dcta"]["recovery"] > metrics["random"]["recovery"],
    }
    checks = {
        "schema_valid": report["schema_version"]
        == "babyai-unlockpickup-terminal-recovery-development-v1",
        "frozen_hashes_match": report["artifact_hashes"] == {
            "config": digest(args.config),
            "runner": digest(ROOT / "scripts" / "run_babyai_unlockpickup_terminal_recovery_development_v1.py"),
            "method": digest(ROOT / "src" / "mcx" / "terminal_recovery_dcta.py"),
            "input_report": digest(input_path),
        },
        "input_hash_pinned": digest(input_path) == config["input_report_sha256"],
        "structured_grid_complete": len(structured_keys) == expected_structured
        and len(set(structured_keys)) == expected_structured,
        "random_grid_complete": len(random_keys) == expected_random
        and len(set(random_keys)) == expected_random,
        "baseline_trajectories_unchanged": baseline_trajectories_unchanged,
        "labels_valid": labels_valid,
        "outcome_accounting_valid": outcome_accounting_valid,
        "terminal_samples_exact": len(samples) == 12 and all(
            all((s["quarantine_match"], s["expected_recovery_match"], s["expected_harm_match"]))
            for s in samples),
        "primary_metrics_recomputed": all(
            math.isclose(metrics[m][metric], report["primary_partial_budget4"][m][metric],
                         abs_tol=1e-12) for m in metrics for metric in metrics[m]),
        "gates_recomputed": gates == report["development_gate"],
        "decision_recomputed": report["decision"] == ("GO" if all(gates.values()) else "NO_GO"),
    }
    output = {
        "schema_version": "babyai-unlockpickup-terminal-recovery-development-verification-v1",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "verified": all(checks.values()), "report_sha256": digest(args.report),
        "checks": checks, "recomputed_primary": metrics, "recomputed_gates": gates,
        "terminal_samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if output["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
