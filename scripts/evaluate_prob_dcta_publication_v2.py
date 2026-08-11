"""Budget-matched v2 evaluation on a specified frozen split."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

import _bootstrap

from mcx.prob_dcta_benchmark import run_latent_policy, source_brier
from mcx.prob_dcta_libero_baselines import run_prior_weighted_acis_risk
from mcx.publication_v2 import PROTOCOL, stable_digest
from mcx.publication_v2_posterior import (
    cascade_from_json, estimator_from_json, sample_posterior, stable_seed,
)
from mcx.publication_v2_source import SourceEstimator
from mcx.risk_aware_acis import LogisticCalibrator


METHODS = ("random", "acis_risk", "static_risk", "positive_only_risk",
           "top1_dcta", "source_ig", "source_then_dcta", "ens",
           "prob_dcta", "known_source_dcta")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_model(value):
    return SourceEstimator(tuple(map(float, value["means"])), tuple(map(float, value["scales"])),
                           tuple(map(float, value["coefficients"])))


def acis_model(value):
    c = value["coefficients"]
    return LogisticCalibrator(c["intercept"], c["provenance"], c["formation_task"], c["content"])


def harm_weights(archive):
    candidates = list(map(str, archive["candidate_ids"])); created = archive["created_at"]
    edges = [tuple(map(str, edge)) for edge in archive["observed_formation_edges"]]
    children = {node: [] for node in candidates}
    for left, right in edges:
        if left in children:
            children[left].append(right)
    reach = {}
    for node in candidates:
        found, frontier = set(), list(children[node])
        while frontier:
            child = frontier.pop()
            if child not in found:
                found.add(child); frontier.extend(children.get(child, ()))
        reach[node] = len(found)
    times = [int(created[node]) for node in candidates]; minimum, maximum = min(times), max(times)
    max_reach = max(reach.values()) or 1
    return {node: 1.0 + .25 * (int(created[node]) - minimum) / max(maximum - minimum, 1)
            + .25 * reach[node] / max_reach for node in candidates}


def random_path(archive_id, candidates, budget):
    return tuple(sorted(candidates, key=lambda node: (
        stable_digest("random", archive_id, node), node
    ))[:budget])


def condition_trace(posterior, replayed, affected):
    current = posterior
    for node in replayed:
        updated = current.condition(node, int(node in affected))
        if updated is not None:
            current = updated
    return current


def metrics(archive, truth, replayed, posterior):
    affected = set(map(str, truth["affected_ids"])); hits = set(replayed) & affected
    weights = harm_weights(archive); total = sum(weights[node] for node in affected)
    probabilities = posterior.source_probabilities()
    predicted = min(probabilities, key=lambda source: (-probabilities[source], source))
    return {
        "replayed_ids": list(replayed), "discoveries": len(hits),
        "recall": len(hits) / len(affected), "audit_yield": len(hits) / len(replayed),
        "weighted_recall": sum(weights[node] for node in hits) / total,
        "source_top1_correct": int(predicted == truth["active_source_id"]),
        "source_brier": source_brier(posterior, str(truth["active_source_id"])),
        "source_entropy": posterior.source_entropy(),
    }


def bootstrap(rows, left, right, draws, seed):
    by_task = {}
    for row in rows:
        by_task.setdefault(row["task_key"], {}).setdefault(row["method"], []).append(row["recall"])
    tasks = sorted(key for key, value in by_task.items() if left in value and right in value)
    differences = [statistics.fmean(by_task[key][left]) - statistics.fmean(by_task[key][right])
                   for key in tasks]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(differences[rng.randrange(len(differences))]
                                     for _ in differences) for _ in range(draws))
    return {"estimate": statistics.fmean(differences),
            "lower_95": samples[int(.025 * draws)], "upper_95": samples[int(.975 * draws)],
            "task_count": len(tasks), "wins": sum(value > 0 for value in differences),
            "ties": sum(value == 0 for value in differences), "losses": sum(value < 0 for value in differences)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--cascade-config", type=Path, required=True)
    parser.add_argument("--inference-config", type=Path, required=True)
    parser.add_argument("--acis-config", type=Path, required=True)
    parser.add_argument("--expected-split", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8")); private = json.loads(args.private.read_text(encoding="utf-8"))
    source_config = json.loads(args.source_config.read_text(encoding="utf-8"))
    cascade_config = json.loads(args.cascade_config.read_text(encoding="utf-8"))
    config = json.loads(args.inference_config.read_text(encoding="utf-8"))
    if public.get("protocol") != f"{PROTOCOL}/public" or private.get("protocol") != f"{PROTOCOL}/private":
        raise ValueError("v2 ledgers required")
    if any(row["split"] != args.expected_split for row in public["archives"]):
        raise ValueError("ledger contains an unexpected split")
    labels = {row["archive_id"]: row for row in private["archives"]}
    estimator = source_model(source_config); cascade = cascade_from_json(cascade_config)
    acis = acis_model(json.loads(args.acis_config.read_text(encoding="utf-8")))
    particles = int(config["particles"]); budgets = tuple(map(int, config["budgets"]))
    rows, diagnostics = [], []; started = time.perf_counter()
    for index, archive in enumerate(public["archives"], start=1):
        truth = labels[archive["archive_id"]]; affected = frozenset(map(str, truth["affected_ids"]))
        prior = estimator.prior(archive, float(source_config["minimum_source_probability"]))
        posterior = sample_posterior(archive, prior, cascade, particles,
                                     stable_seed(str(archive["archive_id"]), particles))
        weights = harm_weights(archive)
        initial_brier = source_brier(posterior, str(truth["active_source_id"]))
        acis_public = {**archive, "formation_edges": archive["observed_formation_edges"],
                       "source_prior": prior}
        for budget in budgets:
            for method in METHODS:
                if method == "random":
                    replayed = random_path(archive["archive_id"], posterior.candidates, budget)
                    final = condition_trace(posterior, replayed, affected)
                elif method == "acis_risk":
                    replayed = run_prior_weighted_acis_risk(acis_public, affected, budget, acis)
                    final = condition_trace(posterior, replayed, affected)
                else:
                    belief = posterior.restrict_source(str(truth["active_source_id"])) if method == "known_source_dcta" else posterior
                    policy_method = "prob_dcta" if method == "known_source_dcta" else method
                    result = run_latent_policy(belief, type("Truth", (), {
                        "affected_ids": affected, "source_id": truth["active_source_id"]
                    })(), budget, method=policy_method, weights=weights)
                    replayed, final = result.replayed_ids, result.final_posterior
                rows.append({
                    "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                    "benchmark": archive["benchmark"], "split": archive["split"],
                    "rotation": archive["rotation"], "provenance_missing_rate": archive["provenance_missing_rate"],
                    "budget": budget, "method": method, "affected_count": len(affected),
                    "initial_source_brier": initial_brier, **metrics(archive, truth, replayed, final),
                })
        diagnostics.append({"archive_id": archive["archive_id"], "task_key": archive["task_key"],
                            "benchmark": archive["benchmark"], "world_count": len(posterior.worlds),
                            "source_prior": prior, "initial_source_brier": initial_brier})
        if index % 20 == 0 or index == len(public["archives"]):
            print(f"evaluated {index}/{len(public['archives'])}", flush=True)
    primary = [row for row in rows if row["budget"] == config["primary_budget"]
               and row["provenance_missing_rate"] == config["primary_provenance_missing_rate"]]
    summary = {}
    benchmarks = tuple(sorted({str(row["benchmark"]) for row in primary})) + ("pooled",)
    for benchmark in benchmarks:
        selected = primary if benchmark == "pooled" else [row for row in primary if row["benchmark"] == benchmark]
        summary[benchmark] = {method: {"macro_recall": statistics.fmean(
            row["recall"] for row in selected if row["method"] == method),
            "weighted_recall": statistics.fmean(row["weighted_recall"] for row in selected if row["method"] == method),
            "source_brier": statistics.fmean(row["source_brier"] for row in selected if row["method"] == method)}
            for method in METHODS}
    comparisons = {benchmark: {
        "prob_minus_top1": bootstrap(
            primary if benchmark == "pooled" else [row for row in primary if row["benchmark"] == benchmark],
            "prob_dcta", "top1_dcta", config["bootstrap_draws"], config["bootstrap_seed"]),
        "prob_minus_acis": bootstrap(
            primary if benchmark == "pooled" else [row for row in primary if row["benchmark"] == benchmark],
            "prob_dcta", "acis_risk", config["bootstrap_draws"], config["bootstrap_seed"] + 1),
        "prob_minus_ens": bootstrap(
            primary if benchmark == "pooled" else [row for row in primary if row["benchmark"] == benchmark],
            "prob_dcta", "ens", config["bootstrap_draws"], config["bootstrap_seed"] + 2),
    } for benchmark in benchmarks}
    payload = {
        "protocol": f"{PROTOCOL}/evaluation", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True, "expected_split": args.expected_split, "task_count": public["task_count"],
        "archive_count": public["archive_count"], "particles": particles, "budgets": list(budgets),
        "hashes": {name: sha256(path) for name, path in {
            "public": args.public, "private": args.private, "source_config": args.source_config,
            "cascade_config": args.cascade_config, "inference_config": args.inference_config,
            "acis_config": args.acis_config, "evaluator": Path(__file__),
            "posterior_implementation": Path("src/mcx/publication_v2_posterior.py")}.items()},
        "primary_summary": summary, "comparisons": comparisons,
        "elapsed_seconds": time.perf_counter() - started, "rows": rows, "diagnostics": diagnostics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key not in {"rows", "diagnostics"}}, indent=2))


if __name__ == "__main__":
    main()
