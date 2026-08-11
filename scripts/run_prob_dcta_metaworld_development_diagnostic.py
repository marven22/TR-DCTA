"""Development-only oracle decomposition for Meta-World publication v2."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time

import _bootstrap

from mcx.publication_v2_oracle import ExactBayesReplayPlanner, hindsight_selection
from mcx.publication_v2_posterior import (
    cascade_from_json, sample_posterior, stable_seed,
)
from mcx.publication_v2_source import SourceEstimator


ORACLES = (
    "full_information_oracle",
    "posterior_optimal",
    "known_source_optimal",
    "known_provenance_optimal",
    "known_source_provenance_optimal",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_model(value):
    return SourceEstimator(
        tuple(map(float, value["means"])), tuple(map(float, value["scales"])),
        tuple(map(float, value["coefficients"])),
    )


def harm_weights(archive):
    """Mirror the frozen publication-v2 evaluator's harm weights."""
    candidates = list(map(str, archive["candidate_ids"]))
    created = archive["created_at"]
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
                found.add(child)
                frontier.extend(children.get(child, ()))
        reach[node] = len(found)
    times = [int(created[node]) for node in candidates]
    minimum, maximum = min(times), max(times)
    max_reach = max(reach.values()) or 1
    return {
        node: 1.0
        + .25 * (int(created[node]) - minimum) / max(maximum - minimum, 1)
        + .25 * reach[node] / max_reach
        for node in candidates
    }


def score(affected, replayed, weights):
    hits = set(replayed) & affected
    total = sum(weights[node] for node in affected)
    return {
        "replayed_ids": list(replayed),
        "discoveries": len(hits),
        "recall": len(hits) / len(affected),
        "weighted_recall": sum(weights[node] for node in hits) / total,
    }


def belief_quality(posterior, affected, true_source):
    probabilities = {node: posterior.marginal(node) for node in posterior.candidates}
    brier = statistics.fmean(
        (probabilities[node] - float(node in affected)) ** 2
        for node in posterior.candidates
    )
    epsilon = 1e-12
    log_loss = statistics.fmean(
        -math.log(max(probabilities[node], epsilon)) if node in affected
        else -math.log(max(1.0 - probabilities[node], epsilon))
        for node in posterior.candidates
    )
    ordered = sorted(posterior.candidates, key=lambda node: (-probabilities[node], node))
    hits = 0
    precision_sum = 0.0
    for rank, node in enumerate(ordered, start=1):
        if node in affected:
            hits += 1
            precision_sum += hits / rank
    source_probabilities = posterior.source_probabilities()
    predicted_source = min(
        posterior.source_ids,
        key=lambda source: (-source_probabilities[source], source),
    )
    return {
        "label_brier": brier,
        "label_log_loss": log_loss,
        "label_average_precision": precision_sum / len(affected),
        "predicted_affected_count": sum(probabilities.values()),
        "actual_affected_count": len(affected),
        "affected_count_bias": sum(probabilities.values()) - len(affected),
        "source_top1_correct": int(predicted_source == true_source),
        "source_brier": sum(
            (source_probabilities[source] - float(source == true_source)) ** 2
            for source in posterior.source_ids
        ),
    }


def task_bootstrap(rows, left, right, draws, seed):
    by_task = {}
    for row in rows:
        if row["method"] not in {left, right}:
            continue
        by_task.setdefault(row["task_key"], {}).setdefault(row["method"], []).append(
            row["weighted_recall"]
        )
    tasks = sorted(key for key, methods in by_task.items() if left in methods and right in methods)
    differences = [
        statistics.fmean(by_task[key][left]) - statistics.fmean(by_task[key][right])
        for key in tasks
    ]
    rng = random.Random(seed)
    samples = sorted(
        statistics.fmean(differences[rng.randrange(len(differences))] for _ in differences)
        for _ in range(draws)
    )
    return {
        "estimate": statistics.fmean(differences),
        "lower_95": samples[int(.025 * draws)],
        "upper_95": samples[int(.975 * draws)],
        "task_count": len(tasks),
        "wins": sum(value > 0 for value in differences),
        "ties": sum(value == 0 for value in differences),
        "losses": sum(value < 0 for value in differences),
    }


def summarize(rows):
    result = {}
    keys = sorted({(int(row["budget"]), float(row["provenance_missing_rate"])) for row in rows})
    for budget, mask in keys:
        selected = [row for row in rows if row["budget"] == budget
                    and row["provenance_missing_rate"] == mask]
        methods = sorted({row["method"] for row in selected})
        result[f"budget_{budget}_mask_{mask:.2f}"] = {
            method: {
                "macro_recall": statistics.fmean(
                    row["recall"] for row in selected if row["method"] == method
                ),
                "weighted_recall": statistics.fmean(
                    row["weighted_recall"] for row in selected if row["method"] == method
                ),
                "archive_count": sum(row["method"] == method for row in selected),
            }
            for method in methods
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, default=Path("results/prob_dcta_publication_v2_development_public.json"))
    parser.add_argument("--private", type=Path, default=Path("results/prob_dcta_publication_v2_development_private.json"))
    parser.add_argument("--evaluation", type=Path, default=Path("results/prob_dcta_publication_v2_development_evaluation.json"))
    parser.add_argument("--source-config", type=Path, default=Path("configs/prob_dcta_publication_v2_source_estimator.json"))
    parser.add_argument("--cascade-config", type=Path, default=Path("configs/prob_dcta_publication_v2_cascade_development.json"))
    parser.add_argument("--inference-config", type=Path, default=Path("configs/prob_dcta_publication_v2_inference_final.json"))
    parser.add_argument("--output", type=Path, default=Path("results/prob_dcta_metaworld_development_oracle_diagnostic.json"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    source_config = json.loads(args.source_config.read_text(encoding="utf-8"))
    cascade_config = json.loads(args.cascade_config.read_text(encoding="utf-8"))
    inference = json.loads(args.inference_config.read_text(encoding="utf-8"))

    archives = [row for row in public["archives"] if row["benchmark"] == "metaworld"]
    if any(row["split"] != "development" for row in archives):
        raise ValueError("diagnostic refuses non-development archives")
    if args.limit is not None:
        archives = archives[:args.limit]
    allowed_ids = {row["archive_id"] for row in archives}
    truths = {row["archive_id"]: row for row in private["archives"] if row["archive_id"] in allowed_ids}
    if set(truths) != allowed_ids:
        raise ValueError("public/private archive mismatch")
    existing = [row for row in evaluation["rows"] if row["archive_id"] in allowed_ids]

    estimator = source_model(source_config)
    cascade = cascade_from_json(cascade_config)
    particles = int(inference["particles"])
    primary_budget = int(inference["primary_budget"])
    primary_mask = float(inference["primary_provenance_missing_rate"])
    posterior_budgets = (2, primary_budget)
    all_budgets = tuple(map(int, inference["budgets"]))
    by_condition = {
        (row["task_key"], int(row["rotation"]), float(row["provenance_missing_rate"])): row
        for row in archives
    }

    rows = []
    planner_diagnostics = []
    belief_diagnostics = []
    started = time.perf_counter()
    for index, archive in enumerate(archives, start=1):
        truth = truths[archive["archive_id"]]
        affected = frozenset(map(str, truth["affected_ids"]))
        weights = harm_weights(archive)
        prior = estimator.prior(archive, float(source_config["minimum_source_probability"]))
        posterior = sample_posterior(
            archive, prior, cascade, particles,
            stable_seed(str(archive["archive_id"]), particles),
        )
        planner = ExactBayesReplayPlanner(posterior, weights)

        for budget in all_budgets:
            replayed = hindsight_selection(
                posterior.candidates, affected, budget, weights,
                enumerate_subsets=(budget == primary_budget and float(archive["provenance_missing_rate"]) == primary_mask),
            )
            rows.append({
                "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                "rotation": archive["rotation"],
                "provenance_missing_rate": archive["provenance_missing_rate"],
                "budget": budget, "method": "full_information_oracle",
                "affected_count": len(affected), **score(affected, replayed, weights),
            })

        for budget in posterior_budgets:
            outcome = planner.run(affected, budget)
            rows.append({
                "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                "rotation": archive["rotation"],
                "provenance_missing_rate": archive["provenance_missing_rate"],
                "budget": budget, "method": "posterior_optimal",
                "affected_count": len(affected),
                "expected_weighted_utility": outcome.expected_weighted_utility,
                "zero_support_observations": outcome.zero_support_observations,
                **score(affected, outcome.replayed_ids, weights),
            })

        if float(archive["provenance_missing_rate"]) == primary_mask:
            true_source = str(truth["active_source_id"])
            known_posterior = posterior.restrict_source(true_source)
            known = ExactBayesReplayPlanner(known_posterior, weights).run(
                affected, primary_budget,
            )
            rows.append({
                "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                "rotation": archive["rotation"], "provenance_missing_rate": primary_mask,
                "budget": primary_budget, "method": "known_source_optimal",
                "affected_count": len(affected),
                "expected_weighted_utility": known.expected_weighted_utility,
                "zero_support_observations": known.zero_support_observations,
                **score(affected, known.replayed_ids, weights),
            })

            full_graph = by_condition[(archive["task_key"], int(archive["rotation"]), 0.0)]
            full_prior = estimator.prior(
                full_graph, float(source_config["minimum_source_probability"]),
            )
            full_posterior = sample_posterior(
                full_graph, full_prior, cascade, particles,
                stable_seed(str(full_graph["archive_id"]), particles),
            )
            provenance = ExactBayesReplayPlanner(full_posterior, weights).run(
                affected, primary_budget,
            )
            rows.append({
                "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                "rotation": archive["rotation"], "provenance_missing_rate": primary_mask,
                "budget": primary_budget, "method": "known_provenance_optimal",
                "affected_count": len(affected),
                "expected_weighted_utility": provenance.expected_weighted_utility,
                "zero_support_observations": provenance.zero_support_observations,
                **score(affected, provenance.replayed_ids, weights),
            })
            full_known_posterior = full_posterior.restrict_source(true_source)
            both = ExactBayesReplayPlanner(full_known_posterior, weights).run(
                affected, primary_budget,
            )
            rows.append({
                "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                "rotation": archive["rotation"], "provenance_missing_rate": primary_mask,
                "budget": primary_budget, "method": "known_source_provenance_optimal",
                "affected_count": len(affected),
                "expected_weighted_utility": both.expected_weighted_utility,
                "zero_support_observations": both.zero_support_observations,
                **score(affected, both.replayed_ids, weights),
            })
            planner_diagnostics.append({
                "archive_id": archive["archive_id"],
                "posterior_worlds": len(posterior.worlds),
                "posterior_dynamic_program_states": planner._solve.cache_info().currsize,
                "posterior_zero_support_observations": rows[-4].get("zero_support_observations", 0),
                "known_source_zero_support_observations": known.zero_support_observations,
                "known_provenance_zero_support_observations": provenance.zero_support_observations,
                "known_source_provenance_zero_support_observations": both.zero_support_observations,
            })
            for condition, diagnostic_posterior in (
                ("deployable", posterior),
                ("known_source", known_posterior),
                ("known_provenance", full_posterior),
                ("known_source_provenance", full_known_posterior),
            ):
                belief_diagnostics.append({
                    "archive_id": archive["archive_id"],
                    "task_key": archive["task_key"],
                    "rotation": archive["rotation"],
                    "condition": condition,
                    **belief_quality(diagnostic_posterior, affected, true_source),
                })
        if index % 10 == 0 or index == len(archives):
            print(f"diagnosed {index}/{len(archives)} archives", flush=True)

    # Existing rows are immutable prior results; retain only cells for which an
    # oracle was computed so summaries compare like with like.
    oracle_cells = {(row["budget"], row["provenance_missing_rate"]) for row in rows}
    for row in existing:
        cell = (int(row["budget"]), float(row["provenance_missing_rate"]))
        if cell in oracle_cells:
            rows.append({
                "archive_id": row["archive_id"], "task_key": row["task_key"],
                "rotation": row["rotation"],
                "provenance_missing_rate": row["provenance_missing_rate"],
                "budget": row["budget"], "method": row["method"],
                "affected_count": row["affected_count"], "recall": row["recall"],
                "weighted_recall": row["weighted_recall"],
                "replayed_ids": row["replayed_ids"], "discoveries": row["discoveries"],
            })

    primary = [row for row in rows if row["budget"] == primary_budget
               and row["provenance_missing_rate"] == primary_mask]
    primary_methods = sorted({row["method"] for row in primary})
    primary_summary = {
        method: {
            "macro_recall": statistics.fmean(row["recall"] for row in primary if row["method"] == method),
            "weighted_recall": statistics.fmean(row["weighted_recall"] for row in primary if row["method"] == method),
        }
        for method in primary_methods
    }
    random_score = primary_summary["random"]["weighted_recall"]
    ceiling_score = primary_summary["full_information_oracle"]["weighted_recall"]
    for method, values in primary_summary.items():
        denominator = ceiling_score - random_score
        values["hindsight_gap_closure_over_random"] = (
            (values["weighted_recall"] - random_score) / denominator
            if denominator > 0 else None
        )

    comparisons = {
        f"{left}_minus_{right}": task_bootstrap(
            primary, left, right, int(inference["bootstrap_draws"]),
            int(inference["bootstrap_seed"]) + offset,
        )
        for offset, (left, right) in enumerate((
            ("full_information_oracle", "prob_dcta"),
            ("posterior_optimal", "prob_dcta"),
            ("known_source_optimal", "posterior_optimal"),
            ("known_provenance_optimal", "posterior_optimal"),
            ("posterior_optimal", "ens"),
        ))
    }
    belief_summary = {
        condition: {
            metric: statistics.fmean(
                row[metric] for row in belief_diagnostics if row["condition"] == condition
            )
            for metric in (
                "label_brier", "label_log_loss", "label_average_precision",
                "predicted_affected_count", "actual_affected_count", "affected_count_bias",
                "source_top1_correct", "source_brier",
            )
        }
        for condition in sorted({row["condition"] for row in belief_diagnostics})
    }
    payload = {
        "protocol": "memory-corruption/multi-origin-publication-v2/metaworld-development-oracle-diagnostic-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "development_only": True,
        "benchmark": "metaworld",
        "task_count": len({row["task_key"] for row in archives}),
        "archive_count": len(archives),
        "primary_budget": primary_budget,
        "primary_provenance_missing_rate": primary_mask,
        "primary_subset_count_per_archive": math.comb(21, primary_budget),
        "particles": particles,
        "ceiling_definitions": {
            "full_information_oracle": "Exact realized upper bound; knows every harmful label.",
            "posterior_optimal": "Exact Bayes-optimal adaptive policy under the sampled deployable posterior; model-relative, not an information-theoretic upper bound.",
            "known_source_optimal": "Exact posterior planner additionally told the true origin.",
            "known_provenance_optimal": "Exact posterior planner using the complete formation graph but not the source.",
            "known_source_provenance_optimal": "Exact posterior planner told the source and complete graph.",
        },
        "primary_summary": primary_summary,
        "primary_task_clustered_comparisons": comparisons,
        "primary_initial_belief_quality": belief_summary,
        "sensitivity_summary": summarize(rows),
        "zero_support_observations": sum(
            int(row.get("zero_support_observations", 0)) for row in rows
        ),
        "elapsed_seconds": time.perf_counter() - started,
        "hashes": {
            "public": sha256(args.public), "private": sha256(args.private),
            "prior": sha256(args.source_config), "cascade": sha256(args.cascade_config),
            "inference": sha256(args.inference_config), "prior_evaluation": sha256(args.evaluation),
            "oracle_implementation": sha256(Path("src/mcx/publication_v2_oracle.py")),
            "diagnostic_script": sha256(Path(__file__)),
        },
        "planner_diagnostics": planner_diagnostics,
        "belief_diagnostics": belief_diagnostics,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in {"rows", "planner_diagnostics", "belief_diagnostics", "sensitivity_summary"}}, indent=2))


if __name__ == "__main__":
    main()
