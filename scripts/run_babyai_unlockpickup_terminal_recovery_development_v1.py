"""Run the frozen TR-DCTA development comparison on cached executable truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.confidence_aware_dcta import confidence_aware_decision
from mcx.prob_dcta_benchmark import LatentSourceWorld, run_latent_policy
from mcx.terminal_recovery_dcta import (
    run_terminal_recovery_dcta, terminal_quarantine_decision,
)
from run_babyai_minigrid_partial_provenance_v1 import opaque_lineages
from run_babyai_unlockpickup_method_v1 import (
    build_stochastic_posterior, condition_trace,
)


ROOT = Path(__file__).resolve().parents[1]
STRUCTURED = ("sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "source_ig",
              "source_then_dcta", "positive_only_dcta", "static_risk",
              "oracle_source", "full_information_hindsight")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(
    archive: dict[str, Any], condition: str, method: str, budget: int,
    replicate: int | None, replayed: tuple[str, ...], final, affected: frozenset[str],
    weights: dict[str, float], capacity: int, sc_mode: str | None,
    quarantine_override: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    decision = terminal_quarantine_decision(final, weights, capacity)
    removed = (decision.quarantined_ids if quarantine_override is None
               else quarantine_override)
    hits = set(replayed) & affected
    removed_hits = set(removed) & affected
    total_weight = sum(weights[node] for node in affected)
    probabilities = final.source_probabilities()
    predicted = min(final.source_ids, key=lambda source: (-probabilities[source], source))
    return {
        "archive_id": archive["archive_id"], "seed": archive["seed"],
        "regime": archive["regime"], "true_cascade_length": archive["true_cascade_length"],
        "condition": condition, "method": method, "budget": budget,
        "replicate": replicate, "replayed_ids": list(replayed),
        "labels": [int(node in affected) for node in replayed],
        "corrupt_discoveries": len(hits),
        "weighted_corrupt_recall": sum(weights[node] for node in hits) / total_weight,
        "predicted_source": predicted,
        "source_identification_accuracy": float(predicted == archive["true_source"]),
        "quarantined_ids": list(removed),
        "posterior_expected_recovery": (decision.value.recovery_probability
                                         if quarantine_override is None else 1.0),
        "posterior_expected_captured_harm": (decision.value.expected_captured_harm
                                              if quarantine_override is None else total_weight),
        "quarantine_recall": len(removed_hits) / len(affected),
        "weighted_quarantine_recall": sum(weights[node] for node in removed_hits) / total_weight,
        "clean_descendants_removed": capacity - len(removed_hits),
        "corrupt_descendants_left": len(affected) - len(removed_hits),
        "robot_recovery_success": float(affected.issubset(removed)),
        "sc_mode": sc_mode,
    }


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for value in rows:
        groups[(value["condition"], value["method"], value["budget"])].append(value)
    metrics = ("corrupt_discoveries", "weighted_corrupt_recall",
               "source_identification_accuracy", "posterior_expected_recovery",
               "posterior_expected_captured_harm", "quarantine_recall",
               "weighted_quarantine_recall", "clean_descendants_removed",
               "corrupt_descendants_left", "robot_recovery_success")
    output = []
    for key, values in sorted(groups.items(), key=lambda item: str(item[0])):
        record = {"condition": key[0], "method": key[1], "budget": key[2],
                  "runs": len(values)}
        for metric in metrics:
            record[f"mean_{metric}"] = statistics.fmean(float(v[metric]) for v in values)
        output.append(record)
    return output


def partial_mean(rows: list[dict[str, Any]], method: str, metric: str, budget: int) -> float:
    values = [float(value[metric]) for value in rows if value["condition"] != "complete"
              and value["method"] == method and value["budget"] == budget]
    return statistics.fmean(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    input_path = ROOT / config["input_report"]
    if digest(input_path) != config["input_report_sha256"]:
        raise ValueError("frozen v1 development report changed")
    source = json.loads(input_path.read_text(encoding="utf-8"))
    colors = tuple(config["colors"])
    variants = tuple(config["variants"])
    lengths = tuple(map(float, config["cascade_length_prior"]))
    stage_weights = tuple(map(float, config["stage_harm_weights"]))
    budgets = tuple(map(int, config["budgets"]))
    capacity = int(config["quarantine_capacity"])
    old_rows = {(r["archive_id"], r["condition"], r["method"], r["budget"], r["replicate"]): r
                for r in source["rows"]}
    views = {(v["archive_id"], v["condition"]): v for v in source["views"]}
    rows = []
    started = time.perf_counter()

    for offset, archive in enumerate(source["archives"]):
        _, private_to_opaque, by_depth = opaque_lineages(archive, variants)
        weights = {private_to_opaque[f"{color}::{variant}"]: stage_weights[depth]
                   for color in colors for depth, variant in enumerate(variants)}
        affected = frozenset(archive["affected_ids"])
        truth = LatentSourceWorld(archive["true_source"], affected, 1.0)
        for condition in ("complete", "partial_33", "partial_67"):
            view = views[(archive["archive_id"], condition)]
            posterior, _ = build_stochastic_posterior(
                colors, by_depth, tuple(map(tuple, view["observed_edges"])),
                archive["source_prior"], lengths,
            )
            for budget in budgets:
                tr = run_terminal_recovery_dcta(
                    posterior, truth, budget, weights=weights, quarantine_capacity=capacity,
                )
                rows.append(row(archive, condition, "tr_dcta", budget, None,
                                tr.replayed_ids, tr.final_posterior, affected, weights,
                                capacity, None))
                for method in STRUCTURED:
                    sc_mode = None
                    quarantine_override = None
                    if method == "sc_dcta":
                        decision = confidence_aware_decision(posterior, budget, weights)
                        sc_mode = decision.mode
                        policy = "top1_dcta" if decision.mode == "hard" else "prob_dcta"
                        outcome = run_latent_policy(posterior, truth, budget,
                                                    method=policy, weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    elif method == "hard_source_dcta":
                        outcome = run_latent_policy(posterior, truth, budget,
                                                    method="top1_dcta", weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    elif method == "positive_only_dcta":
                        outcome = run_latent_policy(posterior, truth, budget,
                                                    method="positive_only_risk", weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    elif method == "oracle_source":
                        restricted = posterior.restrict_source(archive["true_source"])
                        outcome = run_latent_policy(restricted, truth, budget,
                                                    method="prob_dcta", weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    elif method == "full_information_hindsight":
                        prior = old_rows[(archive["archive_id"], condition, method, budget, None)]
                        replayed = tuple(prior["replayed_ids"])
                        final = condition_trace(posterior, replayed, affected)
                        fill = [node for node in sorted(posterior.candidates)
                                if node not in affected]
                        quarantine_override = tuple(sorted(affected)) + tuple(
                            fill[:capacity-len(affected)])
                    else:
                        policy = "source_then_dcta" if method == "source_then_dcta" else method
                        outcome = run_latent_policy(posterior, truth, budget,
                                                    method=policy, weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    rows.append(row(archive, condition, method, budget, None, replayed, final,
                                    affected, weights, capacity, sc_mode, quarantine_override))
                for replicate in range(50):
                    prior = old_rows[(archive["archive_id"], condition, "random", budget, replicate)]
                    replayed = tuple(prior["replayed_ids"])
                    final = condition_trace(posterior, replayed, affected)
                    rows.append(row(archive, condition, "random", budget, replicate, replayed,
                                    final, affected, weights, capacity, None))
        if (offset + 1) % 10 == 0:
            print(f"[archives] {offset+1}/{len(source['archives'])}", flush=True)

    primary = int(config["primary_budget"])
    methods = ("tr_dcta", "sc_dcta", "prob_dcta", "hard_source_dcta", "ens",
               "random", "oracle_source", "full_information_hindsight")
    metrics = {method: {
        "recovery": partial_mean(rows, method, "robot_recovery_success", primary),
        "weighted_quarantine_recall": partial_mean(
            rows, method, "weighted_quarantine_recall", primary),
        "weighted_discovery_recall": partial_mean(
            rows, method, "weighted_corrupt_recall", primary),
    } for method in methods}
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
    expected = len(source["archives"]) * 3 * len(budgets)
    integrity = {
        "input_was_verified_no_go": source["decision"] == "NO_GO",
        "archives_exact": len(source["archives"]) == 60,
        "tr_grid_complete": sum(r["method"] == "tr_dcta" for r in rows) == expected,
        "structured_grid_complete": sum(r["method"] not in {"tr_dcta", "random"} for r in rows)
        == expected * len(STRUCTURED),
        "random_grid_complete": sum(r["method"] == "random" for r in rows) == expected * 50,
        "budgets_exact": all(len(r["replayed_ids"]) == r["budget"] for r in rows),
        "labels_exact": all(r["labels"] == [int(node in set(next(
            a["affected_ids"] for a in source["archives"] if a["archive_id"] == r["archive_id"]
        ))) for node in r["replayed_ids"]] for r in rows),
    }
    decision = "GO" if all(integrity.values()) and all(gates.values()) else "NO_GO"
    report = {
        "schema_version": "babyai-unlockpickup-terminal-recovery-development-v1",
        "protocol": config["protocol"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision, "method_frozen": True,
        "artifact_hashes": {
            "config": digest(args.config), "runner": digest(Path(__file__)),
            "method": digest(ROOT / "src" / "mcx" / "terminal_recovery_dcta.py"),
            "input_report": digest(input_path),
        },
        "counts": {"archives": len(source["archives"]), "method_runs": len(rows)},
        "integrity": integrity, "development_gate": gates,
        "primary_partial_budget4": metrics, "summary": aggregate(rows), "rows": rows,
        "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("decision", "counts", "integrity", "development_gate",
                       "primary_partial_budget4", "elapsed_s")}, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
