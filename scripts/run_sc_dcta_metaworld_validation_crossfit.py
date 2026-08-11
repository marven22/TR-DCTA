"""Run final SC-DCTA-family policies on validation with task-held-out fits."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import _bootstrap

from mcx.prob_dcta_benchmark import run_latent_policy, source_brier
from mcx.publication_v2_oracle import hindsight_selection
from mcx.publication_v2_posterior import (
    fit_cascade_parameters, sample_importance_posterior, sample_posterior,
    stable_seed, support_proposal,
)
from mcx.publication_v2_source import fit_source_estimator, source_features


DEV_PUBLIC = Path("results/prob_dcta_metaworld_development_public_mask_consistent.json")
DEV_PRIVATE = Path("results/prob_dcta_metaworld_development_private_mask_consistent.json")
VAL_PUBLIC = Path("results/prob_dcta_metaworld_validation_public_mask_consistent.json")
VAL_PRIVATE = Path("results/prob_dcta_metaworld_validation_private_mask_consistent.json")
OUTPUT = Path("results/sc_dcta_metaworld_validation_crossfit.json")
METHODS = ("sc_dcta", "ens", "hard_source_dcta", "source_then_dcta",
           "floored_prob_dcta", "known_source_dcta", "full_information_oracle")
BUDGETS = (2, 4, 8)
PARTICLES = 2048


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
    times = [int(created[node]) for node in candidates]
    minimum, maximum = min(times), max(times); max_reach = max(reach.values()) or 1
    return {node: 1.0 + .25 * (int(created[node]) - minimum) / max(maximum - minimum, 1)
            + .25 * reach[node] / max_reach for node in candidates}


def metrics(affected, replayed, weights, posterior, true_source):
    hits = set(replayed) & affected
    return {"replayed_ids": list(replayed), "discoveries": len(hits),
            "recall": len(hits) / len(affected),
            "weighted_recall": sum(weights[node] for node in hits)
                               / sum(weights[node] for node in affected),
            "audit_yield": len(hits) / len(replayed),
            "final_source_brier": (source_brier(posterior, true_source)
                                   if posterior is not None else 0.0)}


def main() -> None:
    dev_public = json.loads(DEV_PUBLIC.read_text(encoding="utf-8"))
    dev_private = json.loads(DEV_PRIVATE.read_text(encoding="utf-8"))
    val_public = json.loads(VAL_PUBLIC.read_text(encoding="utf-8"))
    val_private = json.loads(VAL_PRIVATE.read_text(encoding="utf-8"))
    all_archives = dev_public["archives"] + val_public["archives"]
    all_labels = {row["archive_id"]: row for row in
                  dev_private["archives"] + val_private["archives"]}
    validation_tasks = sorted({row["task_key"] for row in val_public["archives"]})
    if len(validation_tasks) != 10:
        raise ValueError("expected ten validation tasks")

    rows = []; fold_records = []; started = time.perf_counter()
    for fold_index, held_task in enumerate(validation_tasks, start=1):
        training = [row for row in all_archives
                    if row["task_key"] != held_task
                    and float(row["provenance_missing_rate"]) == 0.0]
        held = [row for row in val_public["archives"] if row["task_key"] == held_task]
        if len({row["task_key"] for row in training}) != 19:
            raise ValueError("validation fold must train on 19 other tasks")
        cascade, counts = fit_cascade_parameters(training, all_labels, l2=1.0)
        source_rows = [
            (source_features(archive, str(source)),
             int(str(source) == str(all_labels[archive["archive_id"]]["active_source_id"])))
            for archive in training for source in archive["source_ids"]
        ]
        estimator = fit_source_estimator(source_rows, l2=1.0)
        fold_records.append({"held_task": held_task, "training_task_count": 19,
                             "source_row_count": len(source_rows),
                             "cascade_counts": counts})
        for archive in held:
            truth = all_labels[archive["archive_id"]]
            affected = frozenset(map(str, truth["affected_ids"]))
            source = str(truth["active_source_id"]); weights = harm_weights(archive)
            target_prior = estimator.prior(archive, 0.0)
            proposal_prior = support_proposal(target_prior, .05)
            seed = stable_seed(str(archive["archive_id"]), PARTICLES)
            corrected, _ = sample_importance_posterior(
                archive, target_prior, proposal_prior, cascade, PARTICLES, seed,
            )
            floored = sample_posterior(
                archive, proposal_prior, cascade, PARTICLES, seed,
            )
            truth_object = type("Truth", (), {"affected_ids": affected,
                                                "source_id": source})()
            for budget in BUDGETS:
                specs = (
                    ("sc_dcta", corrected, "prob_dcta"),
                    ("ens", corrected, "ens"),
                    ("hard_source_dcta", corrected, "top1_dcta"),
                    ("source_then_dcta", corrected, "source_then_dcta"),
                    ("floored_prob_dcta", floored, "prob_dcta"),
                )
                for name, posterior, policy in specs:
                    outcome = run_latent_policy(
                        posterior, truth_object, budget, method=policy, weights=weights,
                    )
                    rows.append({"archive_id": archive["archive_id"],
                                 "task_key": archive["task_key"],
                                 "rotation": archive["rotation"],
                                 "provenance_missing_rate": archive["provenance_missing_rate"],
                                 "budget": budget, "method": name,
                                 **metrics(affected, outcome.replayed_ids, weights,
                                           outcome.final_posterior, source)})
                known = corrected.restrict_source(source)
                outcome = run_latent_policy(
                    known, truth_object, budget, method="prob_dcta", weights=weights,
                )
                rows.append({"archive_id": archive["archive_id"],
                             "task_key": archive["task_key"], "rotation": archive["rotation"],
                             "provenance_missing_rate": archive["provenance_missing_rate"],
                             "budget": budget, "method": "known_source_dcta",
                             **metrics(affected, outcome.replayed_ids, weights,
                                       outcome.final_posterior, source)})
                replayed = hindsight_selection(corrected.candidates, affected, budget, weights)
                rows.append({"archive_id": archive["archive_id"],
                             "task_key": archive["task_key"], "rotation": archive["rotation"],
                             "provenance_missing_rate": archive["provenance_missing_rate"],
                             "budget": budget, "method": "full_information_oracle",
                             **metrics(affected, replayed, weights, None, source)})
        print(f"completed validation fold {fold_index}/10", flush=True)

    expected = 90 * len(BUDGETS) * len(METHODS)
    if len(rows) != expected:
        raise ValueError(f"incomplete result: {len(rows)} != {expected}")
    payload = {
        "protocol": "memory-corruption/sc-dcta/metaworld-validation-crossfit-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True, "crossfit": "held validation task excluded; other 19 fit tasks used",
        "task_count": 10, "archive_count": 90, "particles": PARTICLES,
        "budgets": list(BUDGETS), "methods": list(METHODS),
        "folds": fold_records, "rows": rows,
        "elapsed_seconds": time.perf_counter() - started,
        "hashes": {"development_public": sha256(DEV_PUBLIC),
                   "development_private": sha256(DEV_PRIVATE),
                   "validation_public": sha256(VAL_PUBLIC),
                   "validation_private": sha256(VAL_PRIVATE)},
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
