"""Run paired baselines on the corrected frozen SC-DCTA Meta-World ledger."""
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
from mcx.prob_dcta_libero_baselines import run_prior_weighted_acis_risk
from mcx.publication_v2 import stable_digest
from mcx.publication_v2_oracle import hindsight_selection
from mcx.publication_v2_posterior import (
    CascadeParameters, estimator_from_json, sample_importance_posterior,
    sample_posterior, stable_seed, support_proposal,
)
from mcx.risk_aware_acis import LogisticCalibrator


CONFIG = Path("configs/sc_dcta_metaworld_baseline_freeze.json")
OUTPUT = Path("results/sc_dcta_metaworld_baselines.json")
METHODS = (
    "sc_dcta", "random", "acis_risk", "ens", "source_ig",
    "source_then_dcta", "hard_source_dcta", "floored_prob_dcta",
    "static_risk", "positive_only_risk", "known_source_dcta",
    "full_information_oracle",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def acis_model(value):
    coefficients = value["coefficients"]
    return LogisticCalibrator(
        coefficients["intercept"], coefficients["provenance"],
        coefficients["formation_task"], coefficients["content"],
    )


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


def metrics(affected, replayed, weights, posterior, true_source):
    replayed = list(replayed)
    hits = set(replayed) & affected
    return {
        "replayed_ids": replayed, "discoveries": len(hits),
        "recall": len(hits) / len(affected),
        "audit_yield": len(hits) / len(replayed),
        "weighted_recall": sum(weights[node] for node in hits)
                           / sum(weights[node] for node in affected),
        "final_source_brier": (source_brier(posterior, true_source)
                               if posterior is not None else 0.0),
    }


def paired_bootstrap(rows, left, right, draws, seed):
    by_task = {}
    for row in rows:
        if row["method"] in {left, right}:
            by_task.setdefault(row["task_key"], {}).setdefault(
                row["method"], []).append(row["weighted_recall"])
    tasks = sorted(task for task, values in by_task.items()
                   if left in values and right in values)
    differences = [statistics.fmean(by_task[task][left])
                   - statistics.fmean(by_task[task][right]) for task in tasks]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(
        differences[rng.randrange(len(differences))] for _ in differences
    ) for _ in range(draws))
    return {
        "estimate": statistics.fmean(differences),
        "lower_95": samples[int(.025 * draws)],
        "upper_95": samples[int(.975 * draws)],
        "task_count": len(tasks), "wins": sum(value > 0 for value in differences),
        "ties": sum(value == 0 for value in differences),
        "losses": sum(value < 0 for value in differences),
    }


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    paths = {key: Path(value) for key, value in config["paths"].items()}
    for key, expected in config["artifact_hashes"].items():
        actual = sha256(paths[key])
        if actual != expected:
            raise ValueError(f"frozen artifact changed: {key}: {actual} != {expected}")

    public = json.loads(paths["evaluation_public"].read_text(encoding="utf-8"))
    private = json.loads(paths["evaluation_private"].read_text(encoding="utf-8"))
    sc_result = json.loads(paths["sc_dcta_result"].read_text(encoding="utf-8"))
    acis = acis_model(json.loads(paths["acis_config"].read_text(encoding="utf-8")))
    labels = {row["archive_id"]: row for row in private["archives"]}
    if public["task_count"] != 29 or public["archive_count"] != 261:
        raise ValueError("unexpected evaluation ledger")
    if not sc_result.get("method_frozen") or sc_result.get("evaluation_task_count") != 29:
        raise ValueError("completed frozen SC-DCTA result required")

    fitted = sc_result["fit"]
    source_estimator = estimator_from_json(fitted["source_estimator"])
    cascade = CascadeParameters(
        estimator_from_json(fitted["cascade"]["contamination"]),
        estimator_from_json(fitted["cascade"]["emission"]),
        float(fitted["cascade"]["latent_edge_probability"]),
    )
    sc_rows = {(row["archive_id"], int(row["budget"])): row
               for row in sc_result["rows"]}
    particles = int(config["particles"])
    budgets = tuple(map(int, config["budgets"]))
    rows = []
    started = time.perf_counter()
    for index, archive in enumerate(public["archives"], start=1):
        truth = labels[archive["archive_id"]]
        true_source = str(truth["active_source_id"])
        affected = frozenset(map(str, truth["affected_ids"]))
        weights = harm_weights(archive)
        target_prior = source_estimator.prior(archive, 0.0)
        proposal_prior = support_proposal(target_prior, float(config["proposal_floor"]))
        seed = stable_seed(str(archive["archive_id"]), particles)
        corrected, _ = sample_importance_posterior(
            archive, target_prior, proposal_prior, cascade, particles, seed,
        )
        floored = sample_posterior(archive, proposal_prior, cascade, particles, seed)
        truth_object = type("Truth", (), {"affected_ids": affected,
                                           "source_id": true_source})()
        acis_public = {**archive, "formation_edges": archive["observed_formation_edges"],
                       "source_prior": target_prior}
        for budget in budgets:
            stored_sc = sc_rows[(archive["archive_id"], budget)]
            sc_outcome = run_latent_policy(
                corrected, truth_object, budget, method="prob_dcta", weights=weights,
            )
            if list(sc_outcome.replayed_ids) != stored_sc["replayed_ids"]:
                raise ValueError(f"SC-DCTA replay mismatch: {archive['archive_id']} {budget}")
            sc_row = dict(stored_sc)
            sc_row["audit_yield"] = sc_row["discoveries"] / budget
            rows.append(sc_row)

            random_replayed = random_path(archive["archive_id"], corrected.candidates, budget)
            random_final = condition_trace(corrected, random_replayed, affected)
            acis_replayed = run_prior_weighted_acis_risk(
                acis_public, affected, budget, acis,
            )
            acis_final = condition_trace(corrected, acis_replayed, affected)
            for name, replayed, final in (
                ("random", random_replayed, random_final),
                ("acis_risk", acis_replayed, acis_final),
            ):
                rows.append({
                    "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                    "rotation": archive["rotation"],
                    "provenance_missing_rate": archive["provenance_missing_rate"],
                    "budget": budget, "method": name,
                    **metrics(affected, replayed, weights, final, true_source),
                })

            specifications = (
                ("ens", corrected, "ens"),
                ("source_ig", corrected, "source_ig"),
                ("source_then_dcta", corrected, "source_then_dcta"),
                ("hard_source_dcta", corrected, "top1_dcta"),
                ("floored_prob_dcta", floored, "prob_dcta"),
                ("static_risk", corrected, "static_risk"),
                ("positive_only_risk", corrected, "positive_only_risk"),
            )
            for name, posterior, policy in specifications:
                outcome = run_latent_policy(
                    posterior, truth_object, budget, method=policy, weights=weights,
                )
                rows.append({
                    "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                    "rotation": archive["rotation"],
                    "provenance_missing_rate": archive["provenance_missing_rate"],
                    "budget": budget, "method": name,
                    **metrics(affected, outcome.replayed_ids, weights,
                              outcome.final_posterior, true_source),
                })

            known = corrected.restrict_source(true_source)
            known_outcome = run_latent_policy(
                known, truth_object, budget, method="prob_dcta", weights=weights,
            )
            rows.append({
                "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                "rotation": archive["rotation"],
                "provenance_missing_rate": archive["provenance_missing_rate"],
                "budget": budget, "method": "known_source_dcta",
                **metrics(affected, known_outcome.replayed_ids, weights,
                          known_outcome.final_posterior, true_source),
            })
            hindsight = hindsight_selection(corrected.candidates, affected, budget, weights)
            rows.append({
                "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                "rotation": archive["rotation"],
                "provenance_missing_rate": archive["provenance_missing_rate"],
                "budget": budget, "method": "full_information_oracle",
                **metrics(affected, hindsight, weights, None, true_source),
            })
        if index % 29 == 0:
            print(f"completed {index}/261 archives", flush=True)

    expected = 261 * len(budgets) * len(METHODS)
    if len(rows) != expected:
        raise ValueError(f"incomplete method grid: {len(rows)} != {expected}")
    sensitivity = {}
    for budget in budgets:
        for mask in (0.0, .25, .5):
            selected = [row for row in rows if row["budget"] == budget
                        and float(row["provenance_missing_rate"]) == mask]
            sensitivity[f"budget_{budget}_mask_{mask:.2f}"] = {
                method: statistics.fmean(row["weighted_recall"] for row in selected
                                         if row["method"] == method)
                for method in METHODS
            }
    primary = [row for row in rows if row["budget"] == config["primary_budget"]
               and float(row["provenance_missing_rate"]) ==
               float(config["primary_provenance_missing_rate"])]
    primary_summary = {
        method: {
            "weighted_recall": statistics.fmean(row["weighted_recall"] for row in primary
                                                 if row["method"] == method),
            "macro_recall": statistics.fmean(row["recall"] for row in primary
                                              if row["method"] == method),
            "audit_yield": statistics.fmean(row["audit_yield"] for row in primary
                                             if row["method"] == method),
        } for method in METHODS
    }
    comparisons = {
        f"sc_minus_{method}": paired_bootstrap(
            primary, "sc_dcta", method, int(config["bootstrap_draws"]),
            int(config["bootstrap_seed"]) + offset,
        ) for offset, method in enumerate(METHODS[1:])
    }
    payload = {
        "protocol": "memory-corruption/sc-dcta/metaworld-corrected-baselines-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True, "task_count": 29, "archive_count": 261,
        "methods": list(METHODS), "particles": particles,
        "primary_summary": primary_summary, "primary_comparisons": comparisons,
        "sensitivity_summary": sensitivity,
        "elapsed_seconds": time.perf_counter() - started,
        "hashes": {**config["artifact_hashes"], "config": sha256(CONFIG),
                   "runner": sha256(Path(__file__))},
        "rows": rows,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in {"rows", "sensitivity_summary"}}, indent=2))


if __name__ == "__main__":
    main()
