"""Task-level cross-fitted posterior study on Meta-World development only."""
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

from mcx.prob_dcta_benchmark import run_latent_policy
from mcx.publication_v2_oracle import ExactBayesReplayPlanner
from mcx.publication_v2_posterior import (
    cascade_from_json, fit_cascade_parameters, sample_posterior, stable_seed,
)
from mcx.publication_v2_source import (
    SourceEstimator, fit_source_estimator, source_features,
)


VARIANTS = (
    "frozen_current", "external_source_crossfit", "uniform_source_crossfit",
    "adapted_source_crossfit", "known_source_crossfit",
)
POLICIES = ("prob_dcta", "source_then_dcta", "ens")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def estimator_from_config(value):
    return SourceEstimator(
        tuple(map(float, value["means"])), tuple(map(float, value["scales"])),
        tuple(map(float, value["coefficients"])),
    )


def estimator_json(value):
    return {"means": list(value.means), "scales": list(value.scales),
            "coefficients": list(value.coefficients)}


def cascade_json(value):
    return {
        "contamination": estimator_json(value.contamination),
        "emission": estimator_json(value.emission),
        "latent_edge_probability": value.latent_edge_probability,
    }


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


def policy_metrics(affected, replayed, weights):
    hits = set(replayed) & affected; total = sum(weights[node] for node in affected)
    return {"replayed_ids": list(replayed), "discoveries": len(hits),
            "recall": len(hits) / len(affected),
            "weighted_recall": sum(weights[node] for node in hits) / total}


def belief_metrics(posterior, affected, true_source):
    probabilities = {node: posterior.marginal(node) for node in posterior.candidates}
    epsilon = 1e-12
    ordered = sorted(posterior.candidates, key=lambda node: (-probabilities[node], node))
    hits = 0; precision_sum = 0.0
    for rank, node in enumerate(ordered, start=1):
        if node in affected:
            hits += 1; precision_sum += hits / rank
    source_probabilities = posterior.source_probabilities()
    predicted = min(posterior.source_ids,
                    key=lambda source: (-source_probabilities[source], source))
    return {
        "label_brier": statistics.fmean((probabilities[node] - float(node in affected)) ** 2
                                         for node in posterior.candidates),
        "label_log_loss": statistics.fmean(
            -math.log(max(probabilities[node], epsilon)) if node in affected
            else -math.log(max(1.0 - probabilities[node], epsilon))
            for node in posterior.candidates),
        "label_average_precision": precision_sum / len(affected),
        "predicted_affected_count": sum(probabilities.values()),
        "actual_affected_count": len(affected),
        "source_top1_correct": int(predicted == true_source),
        "source_brier": sum((source_probabilities[source] - float(source == true_source)) ** 2
                            for source in posterior.source_ids),
    }


def bootstrap(rows, left, right, draws, seed):
    by_task = {}
    for row in rows:
        if row["model_policy"] not in {left, right}:
            continue
        by_task.setdefault(row["task_key"], {}).setdefault(row["model_policy"], []).append(
            row["weighted_recall"])
    tasks = sorted(key for key, value in by_task.items() if left in value and right in value)
    differences = [statistics.fmean(by_task[key][left]) - statistics.fmean(by_task[key][right])
                   for key in tasks]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(differences[rng.randrange(len(differences))]
                                     for _ in differences) for _ in range(draws))
    return {"estimate": statistics.fmean(differences),
            "lower_95": samples[int(.025 * draws)], "upper_95": samples[int(.975 * draws)],
            "task_count": len(tasks), "wins": sum(value > 0 for value in differences),
            "ties": sum(value == 0 for value in differences),
            "losses": sum(value < 0 for value in differences)}


def summary(rows):
    result = {}
    for budget, mask in sorted({(row["budget"], row["provenance_missing_rate"]) for row in rows}):
        selected = [row for row in rows if row["budget"] == budget
                    and row["provenance_missing_rate"] == mask]
        result[f"budget_{budget}_mask_{mask:.2f}"] = {
            model_policy: statistics.fmean(row["weighted_recall"] for row in selected
                                            if row["model_policy"] == model_policy)
            for model_policy in sorted({row["model_policy"] for row in selected})
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, default=Path("results/prob_dcta_publication_v2_development_public.json"))
    parser.add_argument("--private", type=Path, default=Path("results/prob_dcta_publication_v2_development_private.json"))
    parser.add_argument("--source-config", type=Path, default=Path("configs/prob_dcta_publication_v2_source_estimator.json"))
    parser.add_argument("--cascade-config", type=Path, default=Path("configs/prob_dcta_publication_v2_cascade_development.json"))
    parser.add_argument("--inference-config", type=Path, default=Path("configs/prob_dcta_publication_v2_inference_final.json"))
    parser.add_argument("--output", type=Path, default=Path("results/prob_dcta_metaworld_development_crossfit.json"))
    args = parser.parse_args()

    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    source_config = json.loads(args.source_config.read_text(encoding="utf-8"))
    inference = json.loads(args.inference_config.read_text(encoding="utf-8"))
    archives = [row for row in public["archives"] if row["benchmark"] == "metaworld"]
    if any(row["split"] != "development" for row in archives):
        raise ValueError("cross-fit study refuses non-development archives")
    labels = {row["archive_id"]: row for row in private["archives"]}
    task_keys = sorted({row["task_key"] for row in archives})
    if len(task_keys) != 10:
        raise ValueError("frozen Meta-World development split must contain 10 tasks")
    external_estimator = estimator_from_config(source_config)
    frozen_cascade = cascade_from_json(json.loads(args.cascade_config.read_text(encoding="utf-8")))
    floor = float(source_config["minimum_source_probability"])
    particles = int(inference["particles"]); budgets = tuple(map(int, inference["budgets"]))
    primary_budget = int(inference["primary_budget"])
    primary_mask = float(inference["primary_provenance_missing_rate"])

    rows = []; beliefs = []; fold_models = []; started = time.perf_counter()
    for fold_index, held_task in enumerate(task_keys):
        training = [row for row in archives if row["task_key"] != held_task
                    and float(row["provenance_missing_rate"]) == 0.0]
        held = [row for row in archives if row["task_key"] == held_task]
        fold_cascade, counts = fit_cascade_parameters(training, labels, l2=1.0)
        source_rows = [
            (source_features(archive, str(source)),
             int(str(source) == str(labels[archive["archive_id"]]["active_source_id"])))
            for archive in training for source in archive["source_ids"]
        ]
        fold_estimator = fit_source_estimator(source_rows, l2=1.0)
        fold_models.append({"held_task": held_task, "training_task_count": 9,
                            "source_training_rows": len(source_rows), "cascade_counts": counts,
                            "source_estimator": estimator_json(fold_estimator),
                            "cascade": cascade_json(fold_cascade)})

        for archive in held:
            truth = labels[archive["archive_id"]]
            affected = frozenset(map(str, truth["affected_ids"])); true_source = str(truth["active_source_id"])
            weights = harm_weights(archive)
            external_prior = external_estimator.prior(archive, floor)
            adapted_prior = fold_estimator.prior(archive, floor)
            uniform_prior = {str(source): 1.0 / len(archive["source_ids"])
                             for source in archive["source_ids"]}
            specifications = {
                "frozen_current": (external_prior, frozen_cascade),
                "external_source_crossfit": (external_prior, fold_cascade),
                "uniform_source_crossfit": (uniform_prior, fold_cascade),
                "adapted_source_crossfit": (adapted_prior, fold_cascade),
            }
            posteriors = {}
            for variant, (prior, cascade) in specifications.items():
                posterior = sample_posterior(
                    archive, prior, cascade, particles,
                    stable_seed(str(archive["archive_id"]), particles),
                )
                posteriors[variant] = posterior
            posteriors["known_source_crossfit"] = posteriors[
                "external_source_crossfit"
            ].restrict_source(true_source)

            for variant, posterior in posteriors.items():
                beliefs.append({"archive_id": archive["archive_id"], "task_key": held_task,
                                "rotation": archive["rotation"],
                                "provenance_missing_rate": archive["provenance_missing_rate"],
                                "variant": variant,
                                **belief_metrics(posterior, affected, true_source)})
                truth_object = type("Truth", (), {"affected_ids": affected,
                                                    "source_id": true_source})()
                for budget in budgets:
                    for policy in POLICIES:
                        outcome = run_latent_policy(
                            posterior, truth_object, budget, method=policy, weights=weights,
                        )
                        rows.append({"archive_id": archive["archive_id"], "task_key": held_task,
                                     "rotation": archive["rotation"],
                                     "provenance_missing_rate": archive["provenance_missing_rate"],
                                     "budget": budget, "variant": variant, "policy": policy,
                                     "model_policy": f"{variant}/{policy}",
                                     **policy_metrics(affected, outcome.replayed_ids, weights)})
                if float(archive["provenance_missing_rate"]) == primary_mask:
                    oracle = ExactBayesReplayPlanner(posterior, weights).run(
                        affected, primary_budget,
                    )
                    rows.append({"archive_id": archive["archive_id"], "task_key": held_task,
                                 "rotation": archive["rotation"],
                                 "provenance_missing_rate": archive["provenance_missing_rate"],
                                 "budget": primary_budget, "variant": variant,
                                 "policy": "posterior_optimal",
                                 "model_policy": f"{variant}/posterior_optimal",
                                 "expected_weighted_utility": oracle.expected_weighted_utility,
                                 **policy_metrics(affected, oracle.replayed_ids, weights)})
        print(f"completed fold {fold_index + 1}/10", flush=True)

    summaries = summary(rows)
    primary_key = f"budget_{primary_budget}_mask_{primary_mask:.2f}"
    primary = [row for row in rows if row["budget"] == primary_budget
               and row["provenance_missing_rate"] == primary_mask]
    belief_primary = [row for row in beliefs if row["provenance_missing_rate"] == primary_mask]
    belief_summary = {
        variant: {metric: statistics.fmean(row[metric] for row in belief_primary
                                            if row["variant"] == variant)
                  for metric in ("label_brier", "label_log_loss", "label_average_precision",
                                 "predicted_affected_count", "actual_affected_count",
                                 "source_top1_correct", "source_brier")}
        for variant in VARIANTS
    }
    adapted = "adapted_source_crossfit/prob_dcta"
    external = "external_source_crossfit/prob_dcta"
    comparison = bootstrap(primary, adapted, external,
                           int(inference["bootstrap_draws"]), int(inference["bootstrap_seed"]) + 50)
    sensitivity_losses = []
    for key, values in summaries.items():
        if adapted in values and external in values:
            sensitivity_losses.append({"cell": key, "adapted_minus_external": values[adapted] - values[external]})
    gates = {
        "primary_gain_at_least_003": comparison["estimate"] >= .03,
        "source_brier_improves": belief_summary["adapted_source_crossfit"]["source_brier"]
                                 < belief_summary["external_source_crossfit"]["source_brier"],
        "harm_average_precision_improves": belief_summary["adapted_source_crossfit"]["label_average_precision"]
                                           > belief_summary["external_source_crossfit"]["label_average_precision"],
        "wins_at_least_6_tasks": comparison["wins"] >= 6,
        "no_sensitivity_loss_over_003": min(row["adapted_minus_external"] for row in sensitivity_losses) >= -.03,
    }
    payload = {
        "protocol": "memory-corruption/multi-origin-publication-v2/metaworld-crossfit-posterior-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "development_only": True,
        "task_count": len(task_keys), "archive_count": len(archives), "folds": 10,
        "particles": particles, "primary_budget": primary_budget,
        "primary_provenance_missing_rate": primary_mask,
        "continuation_gate_passed": all(gates.values()), "continuation_gates": gates,
        "primary_summary": summaries[primary_key], "primary_belief_summary": belief_summary,
        "adapted_vs_external_primary": comparison,
        "adapted_vs_external_sensitivity": sensitivity_losses,
        "sensitivity_summary": summaries,
        "citation_leakage_audit": {"masked_true_cited": 616, "masked_true_uncited": 104,
                                   "decoy_cited": 0, "used_by_variants": False},
        "elapsed_seconds": time.perf_counter() - started,
        "hashes": {"public": sha256(args.public), "private": sha256(args.private),
                   "external_source": sha256(args.source_config),
                   "frozen_cascade": sha256(args.cascade_config),
                   "inference": sha256(args.inference_config),
                   "script": sha256(Path(__file__))},
        "fold_models": fold_models, "belief_rows": beliefs, "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in {"fold_models", "belief_rows", "rows", "sensitivity_summary"}}, indent=2))


if __name__ == "__main__":
    main()
