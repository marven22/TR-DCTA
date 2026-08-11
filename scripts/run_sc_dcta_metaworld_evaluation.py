"""Run frozen SC-DCTA alone on the corrected 29-task Meta-World evaluation set."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

import _bootstrap

from mcx.prob_dcta_benchmark import run_latent_policy, source_brier
from mcx.publication_v2_posterior import (
    fit_cascade_parameters, sample_importance_posterior, stable_seed,
    support_proposal,
)
from mcx.publication_v2_source import fit_source_estimator, source_features


CONFIG = Path("configs/sc_dcta_metaworld_evaluation_freeze.json")
OUTPUT = Path("results/sc_dcta_metaworld_evaluation.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def harm_weights(archive):
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


def prior_brier(prior, true_source):
    return sum((float(value) - float(source == true_source)) ** 2
               for source, value in prior.items())


def task_bootstrap_interval(rows, draws, seed):
    by_task = {}
    for row in rows:
        by_task.setdefault(row["task_key"], []).append(row["weighted_recall"])
    tasks = sorted(by_task)
    values = [statistics.fmean(by_task[task]) for task in tasks]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(values[rng.randrange(len(values))]
                                     for _ in values) for _ in range(draws))
    return {
        "estimate": statistics.fmean(values),
        "lower_95": samples[int(.025 * draws)],
        "upper_95": samples[int(.975 * draws)],
        "task_count": len(tasks),
    }


def estimator_json(estimator):
    return {"means": list(estimator.means), "scales": list(estimator.scales),
            "coefficients": list(estimator.coefficients)}


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    paths = {key: Path(value) for key, value in config["paths"].items()}
    for key, expected in config["artifact_hashes"].items():
        actual = sha256(paths[key])
        if actual != expected:
            raise ValueError(f"frozen artifact changed: {key}: {actual} != {expected}")

    dev_public = json.loads(paths["development_public"].read_text(encoding="utf-8"))
    dev_private = json.loads(paths["development_private"].read_text(encoding="utf-8"))
    val_public = json.loads(paths["validation_public"].read_text(encoding="utf-8"))
    val_private = json.loads(paths["validation_private"].read_text(encoding="utf-8"))
    test_public = json.loads(paths["evaluation_public"].read_text(encoding="utf-8"))
    test_private = json.loads(paths["evaluation_private"].read_text(encoding="utf-8"))

    training_archives = dev_public["archives"] + val_public["archives"]
    training_labels = {row["archive_id"]: row for row in
                       dev_private["archives"] + val_private["archives"]}
    fitting_archives = [row for row in training_archives
                        if float(row["provenance_missing_rate"]) == 0.0]
    evaluation_archives = test_public["archives"]
    evaluation_labels = {row["archive_id"]: row for row in test_private["archives"]}
    training_tasks = {row["task_key"] for row in training_archives}
    evaluation_tasks = {row["task_key"] for row in evaluation_archives}
    if len(training_tasks) != 20 or len(evaluation_tasks) != 29:
        raise ValueError("expected 20 fitting tasks and 29 evaluation tasks")
    if training_tasks & evaluation_tasks:
        raise ValueError("fitting and evaluation task identities overlap")
    if len(evaluation_archives) != 261 or set(evaluation_labels) != {
        row["archive_id"] for row in evaluation_archives
    }:
        raise ValueError("unexpected evaluation ledger")
    if any(row["benchmark"] != "metaworld" or row["split"] != "test"
           for row in evaluation_archives):
        raise ValueError("evaluation ledger must contain only Meta-World test tasks")

    cascade, cascade_counts = fit_cascade_parameters(
        fitting_archives, training_labels, l2=float(config["l2"]),
    )
    source_rows = [
        (source_features(archive, str(source)),
         int(str(source) == str(training_labels[archive["archive_id"]]["active_source_id"])))
        for archive in fitting_archives for source in archive["source_ids"]
    ]
    estimator = fit_source_estimator(source_rows, l2=float(config["l2"]))

    particles = int(config["particles"])
    budgets = tuple(map(int, config["budgets"]))
    proposal_floor = float(config["proposal_floor"])
    rows, diagnostics = [], []
    started = time.perf_counter()
    for index, archive in enumerate(evaluation_archives):
        truth = evaluation_labels[archive["archive_id"]]
        true_source = str(truth["active_source_id"])
        affected = frozenset(map(str, truth["affected_ids"]))
        weights = harm_weights(archive)
        target_prior = estimator.prior(archive, 0.0)
        proposal_prior = support_proposal(target_prior, proposal_floor)
        posterior, importance = sample_importance_posterior(
            archive, target_prior, proposal_prior, cascade, particles,
            stable_seed(str(archive["archive_id"]), particles),
        )
        particle_prior = posterior.source_probabilities()
        diagnostics.append({
            "archive_id": archive["archive_id"], "task_key": archive["task_key"],
            "rotation": archive["rotation"],
            "provenance_missing_rate": archive["provenance_missing_rate"],
            "target_prior": target_prior, "proposal_prior": proposal_prior,
            "target_max_probability": max(target_prior.values()),
            "source_top1_correct": int(max(target_prior, key=target_prior.get) == true_source),
            "target_source_brier": prior_brier(target_prior, true_source),
            "particle_source_brier": prior_brier(particle_prior, true_source),
            "target_particle_l1": sum(abs(target_prior[source] - particle_prior[source])
                                      for source in target_prior),
            "effective_sample_size": importance.effective_sample_size,
            "effective_sample_fraction": importance.effective_sample_size / particles,
        })
        truth_object = type("Truth", (), {"affected_ids": affected,
                                           "source_id": true_source})()
        for budget in budgets:
            outcome = run_latent_policy(
                posterior, truth_object, budget, method="prob_dcta", weights=weights,
            )
            replayed = list(outcome.replayed_ids)
            hits = set(replayed) & affected
            rows.append({
                "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                "rotation": archive["rotation"],
                "provenance_missing_rate": archive["provenance_missing_rate"],
                "budget": budget, "method": "sc_dcta", "replayed_ids": replayed,
                "discoveries": len(hits), "recall": len(hits) / len(affected),
                "weighted_recall": sum(weights[node] for node in hits)
                                   / sum(weights[node] for node in affected),
                "final_source_brier": source_brier(outcome.final_posterior, true_source),
            })
        if (index + 1) % 29 == 0:
            print(f"completed {index + 1}/261 archives", flush=True)

    summaries = {}
    for budget in budgets:
        for mask in (0.0, .25, .5):
            selected = [row for row in rows if row["budget"] == budget
                        and float(row["provenance_missing_rate"]) == mask]
            summaries[f"budget_{budget}_mask_{mask:.2f}"] = {
                "archive_count": len(selected),
                "weighted_recall": statistics.fmean(row["weighted_recall"] for row in selected),
                "macro_recall": statistics.fmean(row["recall"] for row in selected),
                "final_source_brier": statistics.fmean(row["final_source_brier"]
                                                         for row in selected),
            }
    primary = [row for row in rows if row["budget"] == config["primary_budget"]
               and float(row["provenance_missing_rate"]) ==
               float(config["primary_provenance_missing_rate"])]
    primary_ids = {row["archive_id"] for row in primary}
    primary_diagnostics = [row for row in diagnostics if row["archive_id"] in primary_ids]
    confidence_by_id = {row["archive_id"]: row["target_max_probability"]
                        for row in primary_diagnostics}
    strata = {}
    for name, predicate in (
        ("ambiguous_lt_0.8", lambda value: value < .8),
        ("confident_ge_0.8", lambda value: value >= .8),
    ):
        selected = [row for row in primary if predicate(confidence_by_id[row["archive_id"]])]
        strata[name] = {
            "archive_count": len(selected),
            "task_count": len({row["task_key"] for row in selected}),
            "weighted_recall": (statistics.fmean(row["weighted_recall"] for row in selected)
                                if selected else None),
        }
    payload = {
        "protocol": "memory-corruption/sc-dcta/metaworld-evaluation-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method_frozen": True, "baselines_run": False,
        "baseline_compatibility": "prior test baselines predate citation-mask correction",
        "training_task_count": len(training_tasks),
        "evaluation_task_count": len(evaluation_tasks),
        "archive_count": len(evaluation_archives), "particles": particles,
        "primary_summary": summaries["budget_4_mask_0.25"],
        "primary_task_bootstrap_95": task_bootstrap_interval(
            primary, int(config["bootstrap_draws"]), int(config["bootstrap_seed"])),
        "primary_source_diagnostics": {
            "top1_accuracy": statistics.fmean(row["source_top1_correct"]
                                               for row in primary_diagnostics),
            "target_brier": statistics.fmean(row["target_source_brier"]
                                              for row in primary_diagnostics),
            "particle_brier": statistics.fmean(row["particle_source_brier"]
                                                for row in primary_diagnostics),
            "mean_target_particle_l1": statistics.fmean(row["target_particle_l1"]
                                                         for row in primary_diagnostics),
            "mean_effective_sample_fraction": statistics.fmean(
                row["effective_sample_fraction"] for row in primary_diagnostics),
            "minimum_effective_sample_fraction": min(
                row["effective_sample_fraction"] for row in diagnostics),
        },
        "primary_confidence_strata": strata, "sensitivity_summary": summaries,
        "citation_redactions": test_public["citation_redactions"],
        "fit": {
            "source_rows": len(source_rows), "cascade_rows": cascade_counts,
            "source_estimator": estimator_json(estimator),
            "cascade": {"contamination": estimator_json(cascade.contamination),
                        "emission": estimator_json(cascade.emission),
                        "latent_edge_probability": cascade.latent_edge_probability},
        },
        "elapsed_seconds": time.perf_counter() - started,
        "hashes": {**config["artifact_hashes"], "config": sha256(CONFIG),
                   "runner": sha256(Path(__file__))},
        "posterior_diagnostics": diagnostics, "rows": rows,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in {"posterior_diagnostics", "rows", "fit",
                                     "sensitivity_summary"}}, indent=2))


if __name__ == "__main__":
    main()
