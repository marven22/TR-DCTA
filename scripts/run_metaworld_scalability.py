"""Run the frozen task-matched Meta-World archive scalability study."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
import time
import tracemalloc

import _bootstrap

from mcx.metaworld_scalability import extend_harm_weights, scale_archive
from mcx.prob_dcta_benchmark import run_latent_policy
from mcx.prob_dcta_libero_baselines import run_prior_weighted_acis_risk
from mcx.publication_v2 import stable_digest
from mcx.publication_v2_posterior import (
    CascadeParameters, estimator_from_json, sample_importance_posterior,
    sample_posterior, stable_seed, support_proposal,
)
from mcx.risk_aware_acis import LogisticCalibrator


DEFAULT_CONFIG = Path("configs/metaworld_scalability_freeze_v1.json")
METHODS = (
    "sc_dcta", "ens", "hard_source_dcta", "acis_risk",
    "floored_prob_dcta", "random",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def acis_model(value):
    coefficients = value["coefficients"]
    return LogisticCalibrator(
        coefficients["intercept"], coefficients["provenance"],
        coefficients["formation_task"], coefficients["content"],
    )


def random_path(archive_id: str, candidates, budget: int):
    return tuple(sorted(candidates, key=lambda node: (
        stable_digest("scalability-random", archive_id, node), node,
    ))[:budget])


def condition_trace(posterior, replayed, affected):
    current = posterior
    for node in replayed:
        updated = current.condition(node, int(node in affected))
        if updated is not None:
            current = updated
    return current


def summarize(rows):
    grouped = {}
    for row in rows:
        key = (row["archive_size"], row["budget"], row["provenance_missing_rate"], row["method"])
        grouped.setdefault(key, []).append(row)
    output = {}
    for key, values in grouped.items():
        size, budget, mask, method = key
        output[f"n{size}_b{budget}_m{mask:.2f}_{method}"] = {
            "archive_size": size, "budget": budget,
            "provenance_missing_rate": mask, "method": method,
            "archive_count": len(values),
            "task_count": len({row["task_key"] for row in values}),
            "weighted_recall": statistics.fmean(row["weighted_recall"] for row in values),
            "audit_yield": statistics.fmean(row["audit_yield"] for row in values),
            "distractor_replay_fraction": statistics.fmean(row["distractor_replays"] / row["budget"] for row in values),
            "mean_acquisition_seconds": statistics.fmean(row["acquisition_seconds"] for row in values),
            "median_acquisition_seconds": statistics.median(row["acquisition_seconds"] for row in values),
        }
    return output


def task_bootstrap_difference(rows, size: int, budget: int, mask: float,
                              left: str, right: str, draws: int, seed: int):
    selected = [row for row in rows if row["archive_size"] == size
                and row["budget"] == budget
                and row["provenance_missing_rate"] == mask
                and row["method"] in {left, right}]
    by_task = {}
    for row in selected:
        by_task.setdefault(row["task_key"], {}).setdefault(row["method"], []).append(
            row["weighted_recall"]
        )
    tasks = sorted(task for task, values in by_task.items()
                   if left in values and right in values)
    if not tasks:
        return {
            "estimate": None, "lower_95": None, "upper_95": None,
            "task_count": 0,
        }
    differences = [
        statistics.fmean(by_task[task][left]) - statistics.fmean(by_task[task][right])
        for task in tasks
    ]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(
        differences[rng.randrange(len(differences))] for _ in differences
    ) for _ in range(draws))
    return {
        "estimate": statistics.fmean(differences),
        "lower_95": samples[int(.025 * draws)],
        "upper_95": samples[int(.975 * draws)],
        "task_count": len(tasks),
    }


def measured(callable_):
    started = time.perf_counter()
    value = callable_()
    return value, time.perf_counter() - started


def profiled(callable_):
    tracemalloc.start()
    tracemalloc.reset_peak()
    started = time.perf_counter()
    value = callable_()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return value, elapsed, peak


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--split", choices=("development", "validation", "test"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-archives", type=int)
    parser.add_argument("--sizes", nargs="+", type=int)
    parser.add_argument("--particles", type=int)
    parser.add_argument("--skip-profiles", action="store_true")
    parser.add_argument("--profile-only", action="store_true")
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    paths = {key: Path(value) for key, value in config["paths"].items()}
    for key, expected in config.get("artifact_hashes", {}).items():
        if key in {"protocol_document", "runner", "construction_module"}:
            continue
        actual = sha256(paths[key])
        if actual != expected:
            raise ValueError(f"frozen artifact changed: {key}: {actual} != {expected}")
    public = json.loads(paths[f"{args.split}_public"].read_text(encoding="utf-8"))
    private = json.loads(paths[f"{args.split}_private"].read_text(encoding="utf-8"))
    observable = json.loads(paths[f"{args.split}_recovery_observable"].read_text(encoding="utf-8"))
    recovery_private = json.loads(paths[f"{args.split}_recovery_private"].read_text(encoding="utf-8"))
    sc_result = json.loads(paths["sc_dcta_fit"].read_text(encoding="utf-8"))
    acis = acis_model(json.loads(paths["acis_config"].read_text(encoding="utf-8")))
    fitted = sc_result["fit"]
    source_estimator = estimator_from_json(fitted["source_estimator"])
    cascade = CascadeParameters(
        estimator_from_json(fitted["cascade"]["contamination"]),
        estimator_from_json(fitted["cascade"]["emission"]),
        float(fitted["cascade"]["latent_edge_probability"]),
    )
    truth_by_id = {str(row["archive_id"]): row for row in private["archives"]}
    observable_by_task = {(str(row["task_key"]), int(row["rotation"])): row
                          for row in observable["archives"]}
    recovery_by_task = {}
    for row in recovery_private["archives"]:
        archive_id = str(row["archive_id"])
        obs = next(item for item in observable["archives"] if str(item["archive_id"]) == archive_id)
        recovery_by_task[(str(row["task_key"]), int(obs["rotation"]))] = row
    sizes = tuple(args.sizes or map(int, config["archive_sizes"]))
    budgets = tuple(map(int, config["replay_budgets"]))
    particles = int(args.particles or config["particles"])
    masks = set(map(float, config["provenance_missing_rates"]))
    archives = [row for row in public["archives"] if float(row["provenance_missing_rate"]) in masks]
    archives.sort(key=lambda row: (row["task_key"], int(row["rotation"]), float(row["provenance_missing_rate"])))
    if args.shard_count <= 0 or not 0 <= args.shard_index < args.shard_count:
        raise ValueError("invalid shard specification")
    total_base_archives = len(archives)
    archives = [archive for index, archive in enumerate(archives)
                if index % args.shard_count == args.shard_index]
    if args.max_archives:
        archives = archives[:args.max_archives]

    rows, construction_rows, profile_rows = [], [], []
    started_all = time.perf_counter()
    profiled_cells = set()
    for archive_index, base in enumerate(archives, start=1):
        truth = truth_by_id[str(base["archive_id"])]
        key = (str(base["task_key"]), int(base["rotation"]))
        clean = observable_by_task[key]
        recovery = recovery_by_task[key]
        for size in sizes:
            scaled = scale_archive(
                base, truth, clean["clean_memories"], recovery["clean_policy_by_memory"],
                recovery["corrupted_policy_by_memory"], recovery["success_by_policy"], size,
            )
            archive = scaled.archive
            affected = scaled.affected_ids
            weights = extend_harm_weights(base, scaled)
            target_prior = source_estimator.prior(archive, 0.0)
            proposal_prior = support_proposal(target_prior, float(config["proposal_floor"]))
            seed = stable_seed(str(base["archive_id"]), particles)
            true_world = type("Truth", (), {
                "affected_ids": affected,
                "source_id": str(truth["active_source_id"]),
            })()
            if args.profile_only:
                def profile_pipeline_only():
                    profiled_posterior, _ = sample_importance_posterior(
                        archive, target_prior, proposal_prior, cascade, particles, seed,
                    )
                    return run_latent_policy(
                        profiled_posterior, true_world,
                        int(config["primary_replay_budget"]),
                        method="prob_dcta", weights=weights,
                    )

                _, elapsed, peak = profiled(profile_pipeline_only)
                profile_rows.append({
                    "split": args.split, "archive_id": base["archive_id"],
                    "archive_size": size,
                    "provenance_missing_rate": float(base["provenance_missing_rate"]),
                    "method": "sc_dcta",
                    "profiled_budget": int(config["primary_replay_budget"]),
                    "profiled_seconds": elapsed,
                    "peak_traced_python_bytes": peak,
                    "profile_scope": "posterior_construction_plus_sc_dcta_acquisition",
                })
                continue
            corrected, posterior_seconds = measured(lambda: sample_importance_posterior(
                archive, target_prior, proposal_prior, cascade, particles, seed,
            ))
            corrected, diagnostics = corrected
            floored, floored_seconds = measured(lambda: sample_posterior(
                archive, proposal_prior, cascade, particles, seed,
            ))
            distractors = set(scaled.distractor_ids)
            construction_rows.append({
                "archive_id": base["archive_id"], "task_key": base["task_key"],
                "rotation": int(base["rotation"]),
                "provenance_missing_rate": float(base["provenance_missing_rate"]),
                "archive_size": size, "original_candidates": len(scaled.original_candidate_ids),
                "distractors": len(distractors),
                "observed_distractor_edges": len(scaled.distractor_observed_edges),
                "latent_distractor_edges": len(scaled.distractor_latent_edges),
                "all_distractors_verified_successful": all(
                    scaled.success_by_policy[scaled.policy_by_memory[node]] for node in distractors
                ),
                "source_prior": target_prior,
                "posterior_worlds": len(corrected.worlds),
                "effective_sample_size": diagnostics.effective_sample_size,
                "posterior_seconds": posterior_seconds,
                "floored_posterior_seconds": floored_seconds,
                "mean_distractor_marginal": (statistics.fmean(corrected.marginal(node) for node in distractors)
                                             if distractors else 0.0),
                "mean_harmful_marginal": statistics.fmean(corrected.marginal(node) for node in affected),
            })
            acis_public = {
                **archive, "formation_edges": archive["observed_formation_edges"],
                "source_prior": target_prior,
            }
            for budget in budgets:
                calls = {
                    "sc_dcta": lambda b=budget: run_latent_policy(
                        corrected, true_world, b, method="prob_dcta", weights=weights,
                    ).replayed_ids,
                    "ens": lambda b=budget: run_latent_policy(
                        corrected, true_world, b, method="ens", weights=weights,
                    ).replayed_ids,
                    "hard_source_dcta": lambda b=budget: run_latent_policy(
                        corrected, true_world, b, method="top1_dcta", weights=weights,
                    ).replayed_ids,
                    "acis_risk": lambda b=budget: run_prior_weighted_acis_risk(
                        acis_public, affected, b, acis,
                    ),
                    "floored_prob_dcta": lambda b=budget: run_latent_policy(
                        floored, true_world, b, method="prob_dcta", weights=weights,
                    ).replayed_ids,
                    "random": lambda b=budget: random_path(str(base["archive_id"]), corrected.candidates, b),
                }
                for method in METHODS:
                    replayed, elapsed = measured(calls[method])
                    replayed = tuple(map(str, replayed))
                    hits = set(replayed) & affected
                    rows.append({
                        "split": args.split, "archive_id": base["archive_id"],
                        "task_key": base["task_key"], "rotation": int(base["rotation"]),
                        "provenance_missing_rate": float(base["provenance_missing_rate"]),
                        "archive_size": size, "budget": budget, "method": method,
                        "replayed_ids": list(replayed), "discoveries": len(hits),
                        "weighted_recall": sum(weights[node] for node in hits) / sum(weights[node] for node in affected),
                        "audit_yield": len(hits) / budget,
                        "distractor_replays": len(set(replayed) & distractors),
                        "acquisition_seconds": elapsed,
                        "posterior_worlds": len(corrected.worlds),
                    })
            profile_key = (size, float(base["provenance_missing_rate"]))
            if not args.skip_profiles and profile_key not in profiled_cells:
                def profile_pipeline():
                    profiled_posterior, _ = sample_importance_posterior(
                        archive, target_prior, proposal_prior, cascade, particles, seed,
                    )
                    return run_latent_policy(
                        profiled_posterior, true_world,
                        int(config["primary_replay_budget"]),
                        method="prob_dcta", weights=weights,
                    )

                _, elapsed, peak = profiled(profile_pipeline)
                profile_rows.append({
                    "split": args.split, "archive_id": base["archive_id"],
                    "archive_size": size,
                    "provenance_missing_rate": float(base["provenance_missing_rate"]),
                    "method": "sc_dcta", "profiled_budget": int(config["primary_replay_budget"]),
                    "profiled_seconds": elapsed, "peak_traced_python_bytes": peak,
                    "profile_scope": "posterior_construction_plus_sc_dcta_acquisition",
                })
                profiled_cells.add(profile_key)
        print(f"{args.split}: archive {archive_index}/{len(archives)}", flush=True)

    primary_mask = float(config["primary_provenance_missing_rate"])
    primary_budget = int(config["primary_replay_budget"])
    comparisons = {}
    for size in sizes:
        for comparator in ("ens", "hard_source_dcta", "acis_risk", "floored_prob_dcta", "random"):
            comparisons[f"n{size}_sc_minus_{comparator}"] = task_bootstrap_difference(
                rows, size, primary_budget, primary_mask, "sc_dcta", comparator,
                int(config["bootstrap_draws"]), int(config["bootstrap_seed"]) + size,
            )
    payload = {
        "protocol": config["protocol"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "split": args.split,
        "complete": args.max_archives is None and args.shard_count == 1,
        "shard_index": args.shard_index, "shard_count": args.shard_count,
        "archive_sizes": list(sizes), "replay_budgets": list(budgets),
        "provenance_missing_rates": sorted(masks), "particles": particles,
        "base_archive_count": len(archives),
        "expected_total_base_archives": total_base_archives,
        "task_count": len({row["task_key"] for row in archives}),
        "methods": list(METHODS), "elapsed_seconds": time.perf_counter() - started_all,
        "summary": summarize(rows), "primary_comparisons": comparisons,
        "construction": construction_rows, "memory_profiles": profile_rows, "rows": rows,
        "input_hashes": {
            "config": sha256(args.config),
            f"{args.split}_public": sha256(paths[f"{args.split}_public"]),
            f"{args.split}_private": sha256(paths[f"{args.split}_private"]),
            "sc_dcta_fit": sha256(paths["sc_dcta_fit"]),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "split": args.split, "elapsed_seconds": payload["elapsed_seconds"],
        "rows": len(rows), "construction_rows": len(construction_rows),
    }, indent=2))


if __name__ == "__main__":
    main()
