"""Run locked TR-DCTA transfer on the cached OpenDoorColor evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.confidence_aware_dcta import confidence_aware_decision
from mcx.prob_dcta_benchmark import LatentSourceWorld, run_latent_policy
from mcx.terminal_recovery_dcta import (
    run_terminal_recovery_dcta, terminal_quarantine_decision,
)
from run_babyai_minigrid_partial_provenance_v1 import (
    build_posterior, opaque_lineages,
)
from run_babyai_unlockpickup_method_v1 import condition_trace


ROOT = Path(__file__).resolve().parents[1]
BASELINES = ("sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "source_ig",
             "static_risk", "oracle_source")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_row(
    archive: dict[str, Any], condition: str, method: str, budget: int,
    replicate: int | None, replayed: tuple[str, ...], final,
    affected: frozenset[str], capacity: int, sc_mode: str | None,
    quarantine_override: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    weights = {node: 1.0 for node in final.candidates}
    decision = terminal_quarantine_decision(final, weights, capacity)
    removed = decision.quarantined_ids if quarantine_override is None else quarantine_override
    hits = set(replayed) & affected
    removed_hits = set(removed) & affected
    probabilities = final.source_probabilities()
    predicted = min(final.source_ids, key=lambda source: (-probabilities[source], source))
    return {
        "archive_id": archive["archive_id"], "seed": archive["target_seed"],
        "regime": archive["regime"], "condition": condition, "method": method,
        "budget": budget, "replicate": replicate, "replayed_ids": list(replayed),
        "labels": [int(node in affected) for node in replayed],
        "corrupt_discoveries": len(hits),
        "corrupt_descendant_recall": len(hits) / len(affected),
        "predicted_source": predicted,
        "source_identification_accuracy": float(predicted == archive["true_source"]),
        "quarantined_ids": list(removed),
        "posterior_expected_recovery": (decision.value.recovery_probability
                                         if quarantine_override is None else 1.0),
        "posterior_expected_captured_harm": (decision.value.expected_captured_harm
                                              if quarantine_override is None else 3.0),
        "quarantine_recall": len(removed_hits) / len(affected),
        "clean_descendants_removed": capacity - len(removed_hits),
        "corrupt_descendants_left": len(affected) - len(removed_hits),
        "robot_recovery_success": float(affected.issubset(removed)), "sc_mode": sc_mode,
    }


def process_archive(payload: tuple[dict, list[dict], list[dict], dict]) -> dict[str, Any]:
    archive, archive_views, old_archive_rows, config = payload
    colors = tuple(config["colors"])
    variants = tuple(config["variants"])
    capacity = int(config["quarantine_capacity"])
    old = {(r["condition"], r["method"], r["budget"], r["replicate"]): r
           for r in old_archive_rows}
    views = {v["condition"]: v for v in archive_views}
    _, private_to_opaque, by_depth = opaque_lineages(archive, variants)
    affected = frozenset(private_to_opaque[node] for node in archive["affected_ids"])
    truth = LatentSourceWorld(archive["true_source"], affected, 1.0)
    rows = []
    baseline_match = True
    for condition in config["conditions"]:
        view = views[condition]
        posterior, _ = build_posterior(
            colors, by_depth, tuple(map(tuple, view["observed_edges"])), archive["source_prior"])
        weights = {node: 1.0 for node in posterior.candidates}
        for budget in map(int, config["budgets"]):
            tr = run_terminal_recovery_dcta(
                posterior, truth, budget, weights=weights, quarantine_capacity=capacity)
            rows.append(make_row(archive, condition, "tr_dcta", budget, None,
                                 tr.replayed_ids, tr.final_posterior, affected, capacity, None))
            for method in BASELINES:
                sc_mode = None
                if method == "sc_dcta":
                    decision = confidence_aware_decision(posterior, budget, weights)
                    sc_mode = decision.mode
                    policy = "top1_dcta" if decision.mode == "hard" else "prob_dcta"
                    outcome = run_latent_policy(
                        posterior, truth, budget, method=policy, weights=weights)
                elif method == "hard_source_dcta":
                    outcome = run_latent_policy(
                        posterior, truth, budget, method="top1_dcta", weights=weights)
                elif method == "oracle_source":
                    outcome = run_latent_policy(
                        posterior.restrict_source(archive["true_source"]), truth, budget,
                        method="prob_dcta", weights=weights)
                else:
                    outcome = run_latent_policy(
                        posterior, truth, budget, method=method, weights=weights)
                baseline_match &= list(outcome.replayed_ids) == old[
                    (condition, method, budget, None)]["replayed_ids"]
                rows.append(make_row(archive, condition, method, budget, None,
                                     outcome.replayed_ids, outcome.final_posterior,
                                     affected, capacity, sc_mode))
            ordered = tuple(sorted(affected)) + tuple(
                node for node in sorted(posterior.candidates) if node not in affected)
            replayed = ordered[:budget]
            final = condition_trace(posterior, replayed, affected)
            quarantine = tuple(sorted(affected))
            rows.append(make_row(
                archive, condition, "full_information_hindsight", budget, None,
                replayed, final, affected, capacity, None, quarantine))
            for replicate in range(int(config["random_replicates"])):
                prior = old[(condition, "random", budget, replicate)]
                replayed = tuple(prior["replayed_ids"])
                final = condition_trace(posterior, replayed, affected)
                baseline_match &= list(replayed) == prior["replayed_ids"]
                rows.append(make_row(archive, condition, "random", budget, replicate,
                                     replayed, final, affected, capacity, None))
    return {"archive_id": archive["archive_id"], "rows": rows,
            "baseline_trajectories_match": baseline_match,
            "labels_exact": all(
                value["labels"] == [int(node in affected) for node in value["replayed_ids"]]
                for value in rows),
            "outcome_accounting_exact": all(
                int(value["corrupt_descendants_left"])
                == len(affected - set(value["quarantined_ids"]))
                and bool(value["robot_recovery_success"])
                == affected.issubset(set(value["quarantined_ids"]))
                for value in rows)}


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["condition"], row["method"], row["budget"])].append(row)
    metrics = ("corrupt_discoveries", "corrupt_descendant_recall",
               "source_identification_accuracy", "posterior_expected_recovery",
               "posterior_expected_captured_harm", "quarantine_recall",
               "clean_descendants_removed", "corrupt_descendants_left",
               "robot_recovery_success")
    output = []
    for key, values in sorted(groups.items(), key=lambda item: str(item[0])):
        item = {"condition": key[0], "method": key[1], "budget": key[2],
                "runs": len(values)}
        for metric in metrics:
            item[f"mean_{metric}"] = statistics.fmean(float(row[metric]) for row in values)
        output.append(item)
    return output


def archive_means(rows: list[dict], condition: str, budget: int, metric: str) -> dict[str, dict[str, float]]:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["condition"] == condition and row["budget"] == budget:
            groups[(row["archive_id"], row["method"])].append(float(row[metric]))
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for (archive, method), values in groups.items():
        output[archive][method] = statistics.fmean(values)
    return dict(output)


def paired_bootstrap(values: dict[str, dict[str, float]], right: str,
                     draws: int, seed: int) -> dict[str, Any]:
    ids = sorted(values)
    differences = [values[key]["tr_dcta"] - values[key][right] for key in ids]
    rng = random.Random(seed)
    samples = sorted(sum(differences[rng.randrange(len(ids))] for _ in ids) / len(ids)
                     for _ in range(draws))
    return {"left": "tr_dcta", "right": right, "paired_archives": len(ids),
            "estimate": statistics.fmean(differences),
            "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[min(int(.975 * draws), draws - 1)],
            "wins": sum(x > 0 for x in differences),
            "ties": sum(x == 0 for x in differences),
            "losses": sum(x < 0 for x in differences)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    input_path = ROOT / config["input_report"]
    development_path = ROOT / config["tr_development_report"]
    if digest(input_path) != config["input_report_sha256"]:
        raise ValueError("pinned OpenDoorColor report changed")
    if digest(development_path) != config["tr_development_report_sha256"]:
        raise ValueError("pinned TR-DCTA development report changed")
    source = json.loads(input_path.read_text(encoding="utf-8"))
    expected_seeds = set(range(int(config["seed_start"]), int(config["seed_stop_exclusive"])))
    archives = [a for a in source["archives"] if int(a["target_seed"]) in expected_seeds]
    archives.sort(key=lambda a: int(a["target_seed"]))
    if args.limit is not None:
        archives = archives[:args.limit]
    selected = {a["archive_id"] for a in archives}
    by_view: dict[str, list[dict]] = defaultdict(list)
    by_row: dict[str, list[dict]] = defaultdict(list)
    for view in source["views"]:
        if view["archive_id"] in selected:
            by_view[view["archive_id"]].append(view)
    for row in source["rows"]:
        if row["archive_id"] in selected:
            by_row[row["archive_id"]].append(row)
    payloads = [(a, by_view[a["archive_id"]], by_row[a["archive_id"]], config)
                for a in archives]
    started = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        for index, result in enumerate(executor.map(process_archive, payloads), start=1):
            results.append(result)
            if index % 20 == 0 or index == len(payloads):
                print(f"[transfer archives] {index}/{len(payloads)}", flush=True)
    rows = [row for result in results for row in result["rows"]]
    comparisons = []
    if args.limit is None:
        for condition_index, condition in enumerate(("partial_33", "partial_67")):
            for metric_index, metric in enumerate(
                    ("robot_recovery_success", "quarantine_recall")):
                values = archive_means(rows, condition, int(config["primary_budget"]), metric)
                for comparison_index, right in enumerate(
                        ("sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "random")):
                    comparisons.append({"condition": condition, "metric": metric, "budget": 4,
                                        **paired_bootstrap(
                                            values, right, int(config["bootstrap_draws"]),
                                            int(config["bootstrap_seed"]) + 100*condition_index
                                            + 10*metric_index + comparison_index)})
    expected_archives = len(archives)
    grid = expected_archives * len(config["conditions"]) * len(config["budgets"])
    structured_count = len(tuple(m for m in config["methods"] if m != "random"))
    integrity = {
        "archive_count_exact": expected_archives == (args.limit or 240),
        "seed_set_exact": {int(a["target_seed"]) for a in archives}
        == (set(sorted(expected_seeds)[:args.limit]) if args.limit else expected_seeds),
        "baseline_trajectories_unchanged": all(
            result["baseline_trajectories_match"] for result in results),
        "structured_grid_complete": sum(r["method"] != "random" for r in rows)
        == grid * structured_count,
        "random_grid_complete": sum(r["method"] == "random" for r in rows)
        == grid * int(config["random_replicates"]),
        "budgets_exact": all(len(r["replayed_ids"]) == r["budget"] for r in rows),
        "labels_exact": all(result["labels_exact"] for result in results),
        "outcome_accounting_exact": all(
            result["outcome_accounting_exact"] for result in results),
    }
    report = {
        "schema_version": "babyai-opendoorcolor-terminal-recovery-transfer-v1",
        "protocol": config["protocol"], "phase": config["phase"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_status": "SMOKE" if args.limit is not None else "COMPLETE",
        "method_frozen": True,
        "artifact_hashes": {"config": digest(args.config), "runner": digest(Path(__file__)),
                            "method": digest(ROOT / "src" / "mcx" / "terminal_recovery_dcta.py"),
                            "input_report": digest(input_path),
                            "tr_development_report": digest(development_path)},
        "counts": {"archives": expected_archives, "method_runs": len(rows)},
        "integrity": integrity, "summary": aggregate(rows),
        "paired_bootstrap": comparisons, "rows": rows,
        "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    primary = [item for item in report["summary"] if item["condition"] != "complete"
               and item["budget"] == 4 and item["method"] in
               {"tr_dcta", "sc_dcta", "ens", "random", "full_information_hindsight"}]
    print(json.dumps({"status": report["evaluation_status"], "counts": report["counts"],
                      "integrity": integrity, "primary": primary,
                      "elapsed_s": report["elapsed_s"]}, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
