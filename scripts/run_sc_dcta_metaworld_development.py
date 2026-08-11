"""Task-cross-fitted SC-DCTA study on Meta-World development."""
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
from mcx.publication_v2_oracle import hindsight_selection
from mcx.publication_v2_posterior import (
    fit_cascade_parameters, sample_importance_posterior, sample_posterior,
    stable_seed, support_proposal,
)
from mcx.publication_v2_source import fit_source_estimator, source_features


PUBLIC = Path("results/prob_dcta_metaworld_development_public_mask_consistent.json")
PRIVATE = Path("results/prob_dcta_metaworld_development_private_mask_consistent.json")
INFERENCE = Path("configs/prob_dcta_publication_v2_inference_final.json")
OUTPUT = Path("results/sc_dcta_metaworld_development.json")
METHODS = ("sc_dcta", "floored_prob_dcta", "hard_source_dcta", "sc_ens",
           "floored_ens", "sc_source_then_dcta", "known_source_dcta",
           "full_information_oracle")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def metrics(affected, replayed, weights):
    hits = set(replayed) & affected; total = sum(weights[node] for node in affected)
    return {"replayed_ids": list(replayed), "discoveries": len(hits),
            "recall": len(hits) / len(affected),
            "weighted_recall": sum(weights[node] for node in hits) / total}


def prior_brier(prior, true_source):
    return sum((float(value) - float(source == true_source)) ** 2
               for source, value in prior.items())


def bootstrap(rows, left, right, draws, seed):
    by_task = {}
    for row in rows:
        if row["method"] not in {left, right}:
            continue
        by_task.setdefault(row["task_key"], {}).setdefault(row["method"], []).append(
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


def main():
    public = json.loads(PUBLIC.read_text(encoding="utf-8"))
    private = json.loads(PRIVATE.read_text(encoding="utf-8"))
    inference = json.loads(INFERENCE.read_text(encoding="utf-8"))
    archives = public["archives"]
    if any(row["benchmark"] != "metaworld" or row["split"] != "development"
           for row in archives):
        raise ValueError("development-only Meta-World ledger required")
    labels = {row["archive_id"]: row for row in private["archives"]}
    tasks = sorted({row["task_key"] for row in archives})
    if len(tasks) != 10:
        raise ValueError("expected 10 task folds")
    particles = int(inference["particles"]); budgets = tuple(map(int, inference["budgets"]))
    rows = []; posterior_diagnostics = []; fold_fits = []; started = time.perf_counter()
    for fold_index, held_task in enumerate(tasks):
        training = [row for row in archives if row["task_key"] != held_task
                    and float(row["provenance_missing_rate"]) == 0.0]
        held = [row for row in archives if row["task_key"] == held_task]
        cascade, counts = fit_cascade_parameters(training, labels, l2=1.0)
        source_rows = [(source_features(archive, str(source)),
                        int(str(source) == str(labels[archive["archive_id"]]["active_source_id"])))
                       for archive in training for source in archive["source_ids"]]
        estimator = fit_source_estimator(source_rows, l2=1.0)
        fold_fits.append({"held_task": held_task, "source_rows": len(source_rows),
                          "cascade_counts": counts,
                          "source_coefficients": list(estimator.coefficients)})
        for archive in held:
            truth = labels[archive["archive_id"]]
            affected = frozenset(map(str, truth["affected_ids"])); source = str(truth["active_source_id"])
            weights = harm_weights(archive)
            target_prior = estimator.prior(archive, 0.0)
            proposal_prior = support_proposal(target_prior, .05)
            seed = stable_seed(str(archive["archive_id"]), particles)
            corrected, importance = sample_importance_posterior(
                archive, target_prior, proposal_prior, cascade, particles, seed,
            )
            floored = sample_posterior(
                archive, proposal_prior, cascade, particles, seed,
            )
            corrected_source = corrected.source_probabilities()
            floored_source = floored.source_probabilities()
            posterior_diagnostics.append({
                "archive_id": archive["archive_id"], "task_key": held_task,
                "rotation": archive["rotation"],
                "provenance_missing_rate": archive["provenance_missing_rate"],
                "target_prior": target_prior, "proposal_prior": proposal_prior,
                "target_max_probability": max(target_prior.values()),
                "target_source_brier": prior_brier(target_prior, source),
                "proposal_source_brier": prior_brier(proposal_prior, source),
                "corrected_particle_source_brier": prior_brier(corrected_source, source),
                "floored_particle_source_brier": prior_brier(floored_source, source),
                "corrected_target_l1": sum(abs(corrected_source[s] - target_prior[s]) for s in target_prior),
                "effective_sample_size": importance.effective_sample_size,
                "effective_sample_fraction": importance.effective_sample_size / particles,
                "maximum_importance_weight": importance.maximum_importance_weight,
                "minimum_importance_weight": importance.minimum_importance_weight,
                "sampled_source_counts": dict(importance.sampled_source_counts),
            })
            truth_object = type("Truth", (), {"affected_ids": affected, "source_id": source})()
            for budget in budgets:
                specifications = (
                    ("sc_dcta", corrected, "prob_dcta"),
                    ("floored_prob_dcta", floored, "prob_dcta"),
                    ("hard_source_dcta", corrected, "top1_dcta"),
                    ("sc_ens", corrected, "ens"),
                    ("floored_ens", floored, "ens"),
                    ("sc_source_then_dcta", corrected, "source_then_dcta"),
                )
                for name, posterior, method in specifications:
                    outcome = run_latent_policy(
                        posterior, truth_object, budget, method=method, weights=weights,
                    )
                    rows.append({"archive_id": archive["archive_id"], "task_key": held_task,
                                 "rotation": archive["rotation"],
                                 "provenance_missing_rate": archive["provenance_missing_rate"],
                                 "budget": budget, "method": name,
                                 "final_source_brier": source_brier(outcome.final_posterior, source),
                                 **metrics(affected, outcome.replayed_ids, weights)})
                known = corrected.restrict_source(source)
                known_outcome = run_latent_policy(
                    known, truth_object, budget, method="prob_dcta", weights=weights,
                )
                rows.append({"archive_id": archive["archive_id"], "task_key": held_task,
                             "rotation": archive["rotation"],
                             "provenance_missing_rate": archive["provenance_missing_rate"],
                             "budget": budget, "method": "known_source_dcta",
                             "final_source_brier": 0.0,
                             **metrics(affected, known_outcome.replayed_ids, weights)})
                hindsight = hindsight_selection(corrected.candidates, affected, budget, weights)
                rows.append({"archive_id": archive["archive_id"], "task_key": held_task,
                             "rotation": archive["rotation"],
                             "provenance_missing_rate": archive["provenance_missing_rate"],
                             "budget": budget, "method": "full_information_oracle",
                             "final_source_brier": 0.0, **metrics(affected, hindsight, weights)})
        print(f"completed fold {fold_index + 1}/10", flush=True)

    summaries = {}
    for budget in budgets:
        for mask in (0.0, .25, .5):
            key = f"budget_{budget}_mask_{mask:.2f}"
            selected = [row for row in rows if row["budget"] == budget
                        and float(row["provenance_missing_rate"]) == mask]
            summaries[key] = {method: {
                "weighted_recall": statistics.fmean(row["weighted_recall"] for row in selected
                                                      if row["method"] == method),
                "final_source_brier": statistics.fmean(row["final_source_brier"] for row in selected
                                                        if row["method"] == method),
            } for method in METHODS}
    primary_rows = [row for row in rows if row["budget"] == 4
                    and float(row["provenance_missing_rate"]) == .25]
    primary = summaries["budget_4_mask_0.25"]
    comparisons = {f"sc_minus_{method}": bootstrap(
        primary_rows, "sc_dcta", method, 10000, 262000 + index)
        for index, method in enumerate(("floored_prob_dcta", "hard_source_dcta",
                                        "sc_ens", "known_source_dcta"))}
    primary_diagnostics = [row for row in posterior_diagnostics
                           if float(row["provenance_missing_rate"]) == .25]
    calibration = {metric: statistics.fmean(row[metric] for row in primary_diagnostics)
                   for metric in ("target_max_probability", "target_source_brier",
                                  "proposal_source_brier", "corrected_particle_source_brier",
                                  "floored_particle_source_brier", "corrected_target_l1",
                                  "effective_sample_size", "effective_sample_fraction")}
    ambiguous = [row for row in primary_diagnostics if row["target_max_probability"] < .8]
    best_constituent = max(primary["floored_prob_dcta"]["weighted_recall"],
                           primary["hard_source_dcta"]["weighted_recall"])
    cell_both_gaps = []
    for values in summaries.values():
        sc = values["sc_dcta"]["weighted_recall"]
        lower = min(values["floored_prob_dcta"]["weighted_recall"],
                    values["hard_source_dcta"]["weighted_recall"])
        cell_both_gaps.append(sc - lower)
    gates = {
        "within_001_of_best_primary_constituent": primary["sc_dcta"]["weighted_recall"]
                                                  >= best_constituent - .01,
        "initial_source_brier_improves": calibration["corrected_particle_source_brier"]
                                         < calibration["floored_particle_source_brier"],
        "within_003_of_sc_ens": primary["sc_dcta"]["weighted_recall"]
                                >= primary["sc_ens"]["weighted_recall"] - .03,
        "retains_085_known_source": primary["sc_dcta"]["weighted_recall"]
                                    >= .85 * primary["known_source_dcta"]["weighted_recall"],
        "never_over_003_below_both_constituents": min(cell_both_gaps) >= -.03,
        "all_effective_sample_fractions_at_least_050": min(
            row["effective_sample_fraction"] for row in posterior_diagnostics
        ) >= .50,
    }
    payload = {
        "protocol": "memory-corruption/sc-dcta/metaworld-development-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "development_only": True,
        "task_count": 10, "archive_count": 90, "particles": particles,
        "continuation_gate_passed": all(gates.values()), "continuation_gates": gates,
        "primary_summary": primary, "primary_comparisons": comparisons,
        "primary_calibration": calibration,
        "primary_ambiguous_archive_count": len(ambiguous),
        "minimum_effective_sample_fraction": min(row["effective_sample_fraction"]
                                                  for row in posterior_diagnostics),
        "sensitivity_summary": summaries, "citation_redactions": public["citation_redactions"],
        "elapsed_seconds": time.perf_counter() - started,
        "hashes": {"public": sha256(PUBLIC), "private": sha256(PRIVATE),
                   "inference": sha256(INFERENCE),
                   "posterior": sha256(Path("src/mcx/publication_v2_posterior.py")),
                   "script": sha256(Path(__file__)),
                   "protocol": sha256(Path("docs/SC_DCTA_DEVELOPMENT_PROTOCOL.md"))},
        "fold_fits": fold_fits, "posterior_diagnostics": posterior_diagnostics, "rows": rows,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in {"fold_fits", "posterior_diagnostics", "rows", "sensitivity_summary"}}, indent=2))


if __name__ == "__main__":
    main()
