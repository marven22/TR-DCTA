"""Independently verify the OpenDoorColor TR-DCTA transfer artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401

from mcx.terminal_recovery_dcta import terminal_quarantine_decision
from run_babyai_minigrid_partial_provenance_v1 import build_posterior, opaque_lineages
from run_babyai_unlockpickup_method_v1 import condition_trace


ROOT = Path(__file__).resolve().parents[1]
BASELINES = {"sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "source_ig",
             "static_risk", "oracle_source", "random"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_means(rows: list[dict], condition: str, metric: str) -> dict[str, dict[str, float]]:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["condition"] == condition and row["budget"] == 4:
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
    return {"left": "tr_dcta", "right": right, "paired_archives": len(ids),
            "estimate": statistics.fmean(differences),
            "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[min(int(.975 * draws), draws - 1)],
            "wins": sum(x > 0 for x in differences), "ties": sum(x == 0 for x in differences),
            "losses": sum(x < 0 for x in differences)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    input_path = ROOT / config["input_report"]
    development_path = ROOT / config["tr_development_report"]
    source = json.loads(input_path.read_text(encoding="utf-8"))
    rows = report["rows"]
    old = {(r["archive_id"], r["condition"], r["method"], r["budget"], r["replicate"]): r
           for r in source["rows"]}
    baseline_unchanged = all(
        row["replayed_ids"] == old[(row["archive_id"], row["condition"], row["method"],
                                    row["budget"], row["replicate"])]["replayed_ids"]
        for row in rows if row["method"] in BASELINES)
    structured_keys = [(r["archive_id"], r["condition"], r["method"], r["budget"])
                       for r in rows if r["method"] != "random"]
    random_keys = [(r["archive_id"], r["condition"], r["budget"], r["replicate"])
                   for r in rows if r["method"] == "random"]

    # Reconstruct terminal decisions for twelve evenly spaced TR-DCTA cases.
    archives = {a["archive_id"]: a for a in source["archives"]}
    views = {(v["archive_id"], v["condition"]): v for v in source["views"]}
    tr_rows = {(r["archive_id"], r["condition"]): r for r in rows
               if r["method"] == "tr_dcta" and r["budget"] == 4}
    samples = []
    for archive in list(archives.values())[::40]:
        _, mapping, by_depth = opaque_lineages(archive, tuple(config["variants"]))
        affected = frozenset(mapping[node] for node in archive["affected_ids"])
        for condition in ("partial_33", "partial_67"):
            view = views[(archive["archive_id"], condition)]
            posterior, _ = build_posterior(
                tuple(config["colors"]), by_depth, tuple(map(tuple, view["observed_edges"])),
                archive["source_prior"])
            saved = tr_rows[(archive["archive_id"], condition)]
            final = condition_trace(posterior, tuple(saved["replayed_ids"]), affected)
            decision = terminal_quarantine_decision(
                final, {node: 1.0 for node in posterior.candidates},
                int(config["quarantine_capacity"]))
            samples.append({"archive_id": archive["archive_id"], "condition": condition,
                            "quarantine_match": list(decision.quarantined_ids)
                            == saved["quarantined_ids"],
                            "expected_recovery_match": math.isclose(
                                decision.value.recovery_probability,
                                saved["posterior_expected_recovery"], abs_tol=1e-12)})

    recomputed = []
    for ci, condition in enumerate(("partial_33", "partial_67")):
        for mi, metric in enumerate(("robot_recovery_success", "quarantine_recall")):
            values = archive_means(rows, condition, metric)
            for ri, right in enumerate(
                    ("sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "random")):
                recomputed.append({"condition": condition, "metric": metric, "budget": 4,
                                   **bootstrap(values, right, int(config["bootstrap_draws"]),
                                               int(config["bootstrap_seed"]) + 100*ci + 10*mi + ri)})
    recovery_counts = {}
    for condition in config["conditions"]:
        recovery_counts[condition] = {}
        for budget in map(int, config["budgets"]):
            recovery_counts[condition][str(budget)] = {
                method: sum(float(r["robot_recovery_success"]) for r in rows
                            if r["condition"] == condition and r["budget"] == budget
                            and r["method"] == method)
                for method in ("tr_dcta", "sc_dcta", "ens")}
    checks = {
        "schema_and_status_valid": report["schema_version"]
        == "babyai-opendoorcolor-terminal-recovery-transfer-v1"
        and report["evaluation_status"] == "COMPLETE",
        "frozen_hashes_match": report["artifact_hashes"] == {
            "config": digest(args.config),
            "runner": digest(ROOT / "scripts" / "run_babyai_opendoorcolor_terminal_recovery_transfer_v1.py"),
            "method": digest(ROOT / "src" / "mcx" / "terminal_recovery_dcta.py"),
            "input_report": digest(input_path),
            "tr_development_report": digest(development_path)},
        "pinned_inputs_match": digest(input_path) == config["input_report_sha256"]
        and digest(development_path) == config["tr_development_report_sha256"],
        "baseline_trajectories_unchanged": baseline_unchanged,
        "structured_grid_unique": len(structured_keys) == 240 * 3 * 3 * 9
        and len(set(structured_keys)) == len(structured_keys),
        "random_grid_unique": len(random_keys) == 240 * 3 * 3 * 50
        and len(set(random_keys)) == len(random_keys),
        "budgets_and_replays_valid": all(len(r["replayed_ids"]) == r["budget"]
                                         and len(r["replayed_ids"]) == len(set(r["replayed_ids"]))
                                         for r in rows),
        "outcome_accounting_valid": all(
            bool(r["robot_recovery_success"]) == (r["corrupt_descendants_left"] == 0)
            and r["clean_descendants_removed"] == r["corrupt_descendants_left"] for r in rows),
        "terminal_samples_exact": len(samples) == 12
        and all(s["quarantine_match"] and s["expected_recovery_match"] for s in samples),
        "bootstrap_exact": recomputed == report["paired_bootstrap"],
        "reported_integrity_all_true": all(report["integrity"].values()),
    }
    output = {"schema_version": "babyai-opendoorcolor-terminal-recovery-transfer-verification-v1",
              "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "verified": all(checks.values()), "report_sha256": digest(args.report),
              "checks": checks, "recovery_counts_out_of_240": recovery_counts,
              "terminal_samples": samples}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if output["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
