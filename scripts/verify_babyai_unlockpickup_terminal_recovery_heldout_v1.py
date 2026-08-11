"""Independently verify the confirmatory UnlockPickup TR-DCTA report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401

from mcx.terminal_recovery_dcta import terminal_quarantine_decision
from run_babyai_minigrid_partial_provenance_v1 import opaque_lineages
from run_babyai_unlockpickup_go_no_go_v1 import execute
from run_babyai_unlockpickup_method_v1 import build_stochastic_posterior, condition_trace


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "BABYAI_UNLOCKPICKUP_TERMINAL_RECOVERY_HELDOUT_PROTOCOL_V1.md"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cluster_values(rows: list[dict], metric: str, condition: str | None) -> dict[str, dict[str, float]]:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["budget"] != 4 or row["condition"] == "complete":
            continue
        if condition is not None and row["condition"] != condition:
            continue
        groups[(row["archive_id"], row["method"])].append(float(row[metric]))
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for (archive, method), values in groups.items():
        output[archive][method] = statistics.fmean(values)
    return dict(output)


def bootstrap(values: dict[str, dict[str, float]], right: str,
              draws: int, seed: int) -> dict:
    ids = sorted(values)
    differences = [values[key]["tr_dcta"] - values[key][right] for key in ids]
    rng = random.Random(seed)
    samples = sorted(sum(differences[rng.randrange(len(ids))] for _ in ids) / len(ids)
                     for _ in range(draws))
    lower, upper = samples[int(.025*draws)], samples[min(int(.975*draws), draws-1)]
    return {"left": "tr_dcta", "right": right, "paired_archives": len(ids),
            "estimate": statistics.fmean(differences), "lower_95": lower,
            "upper_95": upper, "superiority_supported": lower > 0.0,
            "wins": sum(x > 0 for x in differences),
            "ties": sum(x == 0 for x in differences),
            "losses": sum(x < 0 for x in differences)}


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
    archive_by_id = {a["archive_id"]: a for a in archives}
    views = {(v["archive_id"], v["condition"]): v for v in report["views"]}
    structured_keys = [(r["archive_id"], r["condition"], r["method"], r["budget"])
                       for r in rows if r["method"] != "random"]
    random_keys = [(r["archive_id"], r["condition"], r["budget"], r["replicate"])
                   for r in rows if r["method"] == "random"]
    labels_exact = all(
        r["labels"] == [int(node in set(archive_by_id[r["archive_id"]]["affected_ids"]))
                        for node in r["replayed_ids"]] for r in rows)
    accounting_exact = all(
        int(r["corrupt_descendants_left"]) == len(
            set(archive_by_id[r["archive_id"]]["affected_ids"])
            - set(r["quarantined_ids"]))
        and bool(r["robot_recovery_success"]) == (
            set(archive_by_id[r["archive_id"]]["affected_ids"])
            <= set(r["quarantined_ids"])) for r in rows)

    # Re-execute one active and one clean memory in six evenly spaced contexts.
    repeat_checks = []
    terminal_checks = []
    colors = tuple(config["colors"])
    variants = tuple(config["variants"])
    stage_weights = tuple(map(float, config["stage_harm_weights"]))
    length_prior = tuple(map(float, config["cascade_length_prior"]))
    for archive in archives[::40]:
        for active in (True, False):
            node, cached = next((node, value) for node, value in archive["replay_map"].items()
                                if bool(value["active_corruption"]) == active)
            again = execute(config["env_id"], int(archive["seed"]),
                            cached["behavior_source"], cached["variant"])
            repeat_checks.append({"archive_id": archive["archive_id"], "node": node,
                                  "active": active,
                                  "success_match": bool(again["success"]) == bool(cached["success"]),
                                  "steps_match": int(again["steps"]) == int(cached["steps"]),
                                  "milestones_match": again["milestones"] == cached["milestones"]})
        _, mapping, by_depth = opaque_lineages(archive, variants)
        affected = frozenset(archive["affected_ids"])
        weights = {mapping[f"{color}::{variant}"]: stage_weights[depth]
                   for color in colors for depth, variant in enumerate(variants)}
        for condition in ("partial_33", "partial_67"):
            view = views[(archive["archive_id"], condition)]
            posterior, _ = build_stochastic_posterior(
                colors, by_depth, tuple(map(tuple, view["observed_edges"])),
                archive["source_prior"], length_prior)
            saved = next(r for r in rows if r["archive_id"] == archive["archive_id"]
                         and r["condition"] == condition and r["budget"] == 4
                         and r["method"] == "tr_dcta")
            final = condition_trace(posterior, tuple(saved["replayed_ids"]), affected)
            decision = terminal_quarantine_decision(
                final, weights, int(config["quarantine_capacity"]))
            terminal_checks.append({"archive_id": archive["archive_id"],
                                    "condition": condition,
                                    "quarantine_match": list(decision.quarantined_ids)
                                    == saved["quarantined_ids"],
                                    "expected_recovery_match": math.isclose(
                                        decision.value.recovery_probability,
                                        saved["posterior_expected_recovery"], abs_tol=1e-12),
                                    "expected_harm_match": math.isclose(
                                        decision.value.expected_captured_harm,
                                        saved["posterior_expected_captured_harm"], abs_tol=1e-12)})

    recomputed = []
    strata = [("pooled_partial", None), ("partial_33", "partial_33"),
              ("partial_67", "partial_67")]
    for si, (stratum, condition) in enumerate(strata):
        for mi, metric in enumerate(config["primary_estimands"]):
            values = cluster_values(rows, metric, condition)
            for ci, right in enumerate(config["primary_comparators"]):
                recomputed.append({"stratum": stratum, "metric": metric, "budget": 4,
                                   **bootstrap(values, right, int(config["bootstrap_draws"]),
                                               int(config["bootstrap_seed"]) + 100*si + 10*mi + ci)})
    recovery_counts = {}
    for condition in config["provenance_conditions"]:
        recovery_counts[condition] = {}
        for budget in map(int, config["budgets"]):
            recovery_counts[condition][str(budget)] = {
                method: sum(float(r["robot_recovery_success"]) for r in rows
                            if r["condition"] == condition and r["budget"] == budget
                            and r["method"] == method)
                for method in ("tr_dcta", "sc_dcta", "ens")}
    frozen_paths = {
        "method": ROOT / "src" / "mcx" / "terminal_recovery_dcta.py",
        "development_report": ROOT / config["development_report"],
        "opendoor_transfer_report": ROOT / config["opendoor_transfer_report"],
        "go_no_go_report": ROOT / config["go_no_go_report"],
    }
    checks = {
        "schema_status_phase_valid": report["schema_version"]
        == "babyai-unlockpickup-terminal-recovery-heldout-v1"
        and report["evaluation_status"] == "COMPLETE" and report["phase"] == "confirmatory_heldout",
        "artifact_hashes_match": report["artifact_hashes"] == {
            "config": digest(args.config), "protocol": digest(PROTOCOL),
            "runner": digest(ROOT / "scripts" / "run_babyai_unlockpickup_terminal_recovery_heldout_v1.py"),
            **{name: digest(path) for name, path in frozen_paths.items()}},
        "frozen_method_hash_match": digest(frozen_paths["method"])
        == config["terminal_recovery_method_sha256"],
        "seed_set_exact": {a["seed"] for a in archives} == set(range(60, 300)),
        "cascade_lengths_balanced": Counter(a["true_cascade_length"] for a in archives)
        == Counter({1: 80, 2: 80, 3: 80}),
        "regimes_balanced": Counter(a["regime"] for a in archives)
        == Counter({name: 60 for name in config["confidence_regimes"]}),
        "environment_truth_valid": all(
            {node for node, value in a["replay_map"].items() if not value["success"]}
            == set(a["affected_ids"]) for a in archives),
        "structured_grid_unique": len(structured_keys) == 240*3*3*11
        and len(set(structured_keys)) == len(structured_keys),
        "random_grid_unique": len(random_keys) == 240*3*3*50
        and len(set(random_keys)) == len(random_keys),
        "labels_exact": labels_exact, "accounting_exact": accounting_exact,
        "budgets_unique": all(len(r["replayed_ids"]) == r["budget"]
                              and len(r["replayed_ids"]) == len(set(r["replayed_ids"])) for r in rows),
        "repeat_executions_exact": len(repeat_checks) == 12 and all(
            c["success_match"] and c["steps_match"] and c["milestones_match"]
            for c in repeat_checks),
        "terminal_decisions_exact": len(terminal_checks) == 12 and all(
            c["quarantine_match"] and c["expected_recovery_match"] and c["expected_harm_match"]
            for c in terminal_checks),
        "bootstrap_exact": recomputed == report["paired_bootstrap"],
        "reported_integrity_all_true": all(report["integrity"].values()),
    }
    output = {"schema_version": "babyai-unlockpickup-terminal-recovery-heldout-verification-v1",
              "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "verified": all(checks.values()), "report_sha256": digest(args.report),
              "checks": checks, "recovery_counts_out_of_240": recovery_counts,
              "repeat_checks": repeat_checks, "terminal_checks": terminal_checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if output["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
