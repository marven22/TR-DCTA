"""Cross-fitted confidence-aware DCTA study on Meta-World development."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

import _bootstrap

from mcx.confidence_aware_dcta import run_confidence_aware_dcta
from mcx.prob_dcta_benchmark import run_latent_policy
from mcx.publication_v2_oracle import hindsight_selection
from mcx.publication_v2_posterior import fit_cascade_parameters, sample_posterior, stable_seed
from mcx.publication_v2_source import fit_source_estimator, source_features


PUBLIC = Path("results/prob_dcta_metaworld_development_public_mask_consistent.json")
PRIVATE = Path("results/prob_dcta_metaworld_development_private_mask_consistent.json")
INFERENCE = Path("configs/prob_dcta_publication_v2_inference_final.json")
OUTPUT = Path("results/confidence_aware_dcta_metaworld_development.json")
METHODS = ("confidence_aware_dcta", "prob_dcta", "top1_dcta", "ens",
           "source_then_dcta", "known_source_dcta", "full_information_oracle")


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
    rows = []; fold_fits = []; started = time.perf_counter()
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
            prior = estimator.prior(archive, .05)
            posterior = sample_posterior(
                archive, prior, cascade, particles,
                stable_seed(str(archive["archive_id"]), particles),
            )
            truth_object = type("Truth", (), {"affected_ids": affected, "source_id": source})()
            source_probabilities = posterior.source_probabilities()
            max_source_probability = max(source_probabilities.values())
            for budget in budgets:
                ca = run_confidence_aware_dcta(
                    posterior, truth_object, budget, weights=weights,
                )
                rows.append({"archive_id": archive["archive_id"], "task_key": held_task,
                             "rotation": archive["rotation"],
                             "provenance_missing_rate": archive["provenance_missing_rate"],
                             "budget": budget, "method": "confidence_aware_dcta",
                             "selected_mode": ca.decision.mode,
                             "hard_expected_utility": ca.decision.hard_expected_utility,
                             "probabilistic_expected_utility": ca.decision.probabilistic_expected_utility,
                             "max_source_probability": max_source_probability,
                             "source_entropy": posterior.source_entropy(),
                             **metrics(affected, ca.policy_outcome.replayed_ids, weights)})
                for method in ("prob_dcta", "top1_dcta", "ens", "source_then_dcta"):
                    outcome = run_latent_policy(
                        posterior, truth_object, budget, method=method, weights=weights,
                    )
                    rows.append({"archive_id": archive["archive_id"], "task_key": held_task,
                                 "rotation": archive["rotation"],
                                 "provenance_missing_rate": archive["provenance_missing_rate"],
                                 "budget": budget, "method": method,
                                 **metrics(affected, outcome.replayed_ids, weights)})
                known = posterior.restrict_source(source)
                known_outcome = run_latent_policy(
                    known, truth_object, budget, method="prob_dcta", weights=weights,
                )
                rows.append({"archive_id": archive["archive_id"], "task_key": held_task,
                             "rotation": archive["rotation"],
                             "provenance_missing_rate": archive["provenance_missing_rate"],
                             "budget": budget, "method": "known_source_dcta",
                             **metrics(affected, known_outcome.replayed_ids, weights)})
                hindsight = hindsight_selection(
                    posterior.candidates, affected, budget, weights,
                )
                rows.append({"archive_id": archive["archive_id"], "task_key": held_task,
                             "rotation": archive["rotation"],
                             "provenance_missing_rate": archive["provenance_missing_rate"],
                             "budget": budget, "method": "full_information_oracle",
                             **metrics(affected, hindsight, weights)})
        print(f"completed fold {fold_index + 1}/10", flush=True)

    summaries = {}; modes = {}
    for budget in budgets:
        for mask in (0.0, .25, .5):
            key = f"budget_{budget}_mask_{mask:.2f}"
            selected = [row for row in rows if row["budget"] == budget
                        and float(row["provenance_missing_rate"]) == mask]
            summaries[key] = {method: statistics.fmean(row["weighted_recall"] for row in selected
                                                        if row["method"] == method)
                              for method in METHODS}
            ca_rows = [row for row in selected if row["method"] == "confidence_aware_dcta"]
            modes[key] = {mode: sum(row["selected_mode"] == mode for row in ca_rows)
                          for mode in ("hard", "probabilistic")}
    primary = [row for row in rows if row["budget"] == 4
               and float(row["provenance_missing_rate"]) == .25]
    primary_summary = summaries["budget_4_mask_0.25"]
    comparisons = {f"confidence_aware_minus_{method}": bootstrap(
        primary, "confidence_aware_dcta", method, 10000, 261000 + index)
        for index, method in enumerate(("prob_dcta", "top1_dcta", "ens", "known_source_dcta"))}
    best_constituent = max(primary_summary["prob_dcta"], primary_summary["top1_dcta"])
    sensitivity_both_losses = []
    for key, values in summaries.items():
        ca = values["confidence_aware_dcta"]
        sensitivity_both_losses.append(ca - min(values["prob_dcta"], values["top1_dcta"]))
    gates = {
        "within_001_of_best_primary_constituent": primary_summary["confidence_aware_dcta"]
                                                  >= best_constituent - .01,
        "never_over_003_below_both_constituents": min(sensitivity_both_losses) >= -.03,
    }
    payload = {
        "protocol": "memory-corruption/confidence-aware-dcta/metaworld-development-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "development_only": True,
        "task_count": 10, "archive_count": 90, "particles": particles,
        "continuation_gate_passed": all(gates.values()), "continuation_gates": gates,
        "primary_summary": primary_summary, "primary_comparisons": comparisons,
        "primary_mode_counts": modes["budget_4_mask_0.25"],
        "sensitivity_summary": summaries, "mode_counts": modes,
        "citation_redactions": public["citation_redactions"],
        "elapsed_seconds": time.perf_counter() - started,
        "hashes": {"public": sha256(PUBLIC), "private": sha256(PRIVATE),
                   "inference": sha256(INFERENCE),
                   "selector": sha256(Path("src/mcx/confidence_aware_dcta.py")),
                   "script": sha256(Path(__file__)),
                   "protocol": sha256(Path("docs/CONFIDENCE_AWARE_DCTA_DEVELOPMENT_PROTOCOL.md"))},
        "fold_fits": fold_fits, "rows": rows,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in {"fold_fits", "rows", "sensitivity_summary", "mode_counts"}}, indent=2))


if __name__ == "__main__":
    main()
