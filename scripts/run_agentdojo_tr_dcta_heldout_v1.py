"""Run the frozen multi-mask AgentDojo TR-DCTA method-held-out study."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import random
import statistics
import time
from typing import Any

import _bootstrap  # noqa: F401

from mcx.agentdojo_adapter import load_official_suites, replay_workflow, screen_suite_pairs
from mcx.agentdojo_method import (
    build_posterior, observed_edges, opaque_lineages, random_policy,
    regime_prior, select_archive_source_groups, stable_seed,
)
from mcx.confidence_aware_dcta import confidence_aware_decision
from mcx.prob_dcta_benchmark import LatentSourceWorld, run_latent_policy
from mcx.terminal_recovery_dcta import run_terminal_recovery_dcta
from run_agentdojo_tr_dcta_development_v1 import (
    STRUCTURED, aggregate, digest, result_row,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "agentdojo_tr_dcta_heldout_freeze_v1.json"
OUTPUT = ROOT / "reports" / "agentdojo_tr_dcta_heldout_v1.json"


def distinct_mask_views(
    archive_id: str, lineages: dict[str, tuple[str, ...]], condition: str,
    specification: dict[str, Any], namespace: str,
) -> list[dict[str, Any]]:
    count = int(specification["mask_replicates"])
    hidden = int(specification["hidden_links_per_layer"])
    if hidden == 0:
        edges = observed_edges(archive_id, lineages, hidden)
        return [{"mask_replicate": 0, "mask_nonce": 0, "observed_edges": edges}]
    views = []
    seen = set()
    for replicate in range(count):
        nonce = 0
        while True:
            mask_key = f"{archive_id}|{namespace}|{condition}|{replicate}|{nonce}"
            edges = observed_edges(mask_key, lineages, hidden)
            if edges not in seen:
                seen.add(edges)
                views.append({
                    "mask_replicate": replicate, "mask_nonce": nonce,
                    "observed_edges": edges,
                })
                break
            nonce += 1
            if nonce > 1000:
                raise RuntimeError("could not construct distinct provenance masks")
    return views


def percentile(sorted_values: list[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def archive_values(
    rows: list[dict[str, Any]], condition: str, budget: int, metric: str,
) -> dict[str, dict[str, float]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["condition"] == condition and row["budget"] == budget:
            grouped[(row["archive_id"], row["method"])].append(float(row[metric]))
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for (archive_id, method), values in grouped.items():
        output[archive_id][method] = statistics.fmean(values)
    return dict(output)


def stratified_paired_bootstrap(
    values: dict[str, dict[str, float]], suites_by_archive: dict[str, str],
    left: str, right: str, draws: int, seed: int,
) -> dict[str, Any]:
    by_suite: dict[str, list[str]] = defaultdict(list)
    for archive_id in sorted(values):
        by_suite[suites_by_archive[archive_id]].append(archive_id)
    differences = {
        archive_id: values[archive_id][left] - values[archive_id][right]
        for archive_id in values
    }
    point = statistics.fmean(differences.values())
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        draw = []
        for suite in sorted(by_suite):
            members = by_suite[suite]
            draw.extend(differences[rng.choice(members)] for _ in members)
        samples.append(statistics.fmean(draw))
    samples.sort()
    return {
        "left": left, "right": right, "archives": len(values), "draws": draws,
        "mean_difference": point, "lower_95": percentile(samples, 0.025),
        "upper_95": percentile(samples, 0.975),
        "wins": sum(value > 1e-12 for value in differences.values()),
        "ties": sum(abs(value) <= 1e-12 for value in differences.values()),
        "losses": sum(value < -1e-12 for value in differences.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if os.environ.get("PYTHONHASHSEED") != config["python_hash_seed"]:
        raise RuntimeError(f"PYTHONHASHSEED must equal {config['python_hash_seed']}")
    if importlib.metadata.version("agentdojo") != config["agentdojo_package_version"]:
        raise RuntimeError("AgentDojo package version does not match frozen protocol")
    frozen = (
        ("development_report", "development_report_sha256"),
        ("development_verification", "development_verification_sha256"),
        ("capacity_audit", "capacity_audit_sha256"),
    )
    for path_key, hash_key in frozen:
        if digest(ROOT / config[path_key]) != config[hash_key]:
            raise RuntimeError(f"frozen prerequisite changed: {config[path_key]}")
    source_files = {
        "terminal_recovery_method_sha256": ROOT / "src" / "mcx" / "terminal_recovery_dcta.py",
        "agentdojo_method_sha256": ROOT / "src" / "mcx" / "agentdojo_method.py",
        "agentdojo_adapter_sha256": ROOT / "src" / "mcx" / "agentdojo_adapter.py",
        "development_runner_sha256": ROOT / "scripts" / "run_agentdojo_tr_dcta_development_v1.py",
    }
    for hash_key, path in source_files.items():
        if digest(path) != config[hash_key]:
            raise RuntimeError(f"frozen source changed: {path}")

    development = json.loads((ROOT / config["development_report"]).read_text(encoding="utf-8"))
    development_users = {
        suite: {archive["user_task_id"] for archive in development["archives"] if archive["suite"] == suite}
        for suite in config["suites"]
    }
    suites = load_official_suites(config["benchmark_version"])
    source_ids = tuple(config["source_ids"])
    variants = tuple(config["variants"])
    weights_by_depth = tuple(map(float, config["stage_harm_weights"]))
    length_prior = tuple(map(float, config["cascade_length_prior"]))
    budgets = tuple(map(int, config["budgets"]))
    capacity = int(config["quarantine_capacity"])
    started = time.perf_counter()
    screening: dict[str, Any] = {}
    archives: list[dict[str, Any]] = []

    for suite_name in config["suites"]:
        suite = suites[suite_name]
        qualifying, counts = screen_suite_pairs(
            suite, minimum_clean_tool_calls=int(config["minimum_clean_tool_calls"]),
            score_clean_against_injection=True,
        )
        unused = tuple(pair for pair in qualifying if pair[0] not in development_users[suite_name])
        groups = select_archive_source_groups(
            unused, suite=suite_name, salt=config["selection_salt"],
            archive_count=int(config["archives_per_suite"]),
            sources_per_archive=int(config["sources_per_archive"]),
        )
        screening[suite_name] = {
            **counts, "unused_qualifying_pairs": len(unused),
            "excluded_development_users": sorted(development_users[suite_name]),
        }
        for suite_rank, (user_task_id, injection_task_ids) in enumerate(groups):
            archive_id = f"agentdojo-heldout-{suite_name}-{suite_rank:02d}"
            lineages, private_to_opaque, by_depth = opaque_lineages(archive_id, source_ids, variants)
            replay_map = {}
            clean_fallback_safe = True
            for source, injection_task_id in zip(source_ids, injection_task_ids):
                clean = replay_workflow(
                    suite, user_task_id, injection_task_id, "clean",
                    score_clean_against_injection=True,
                )
                clean_fallback_safe = clean_fallback_safe and clean.safe_success
                for variant in variants:
                    positive = replay_workflow(suite, user_task_id, injection_task_id, variant)
                    node = private_to_opaque[(source, variant)]
                    replay_map[node] = {
                        "source_id": source, "injection_task_id": injection_task_id,
                        "variant": variant, "negative": clean.to_dict(),
                        "positive": positive.to_dict(),
                    }
            archives.append({
                "archive_id": archive_id, "suite": suite_name,
                "user_task_id": user_task_id,
                "source_injection_tasks": dict(zip(source_ids, injection_task_ids)),
                "lineages": {key: list(value) for key, value in lineages.items()},
                "by_depth": [list(layer) for layer in by_depth],
                "clean_fallback_safe": clean_fallback_safe, "replay_map": replay_map,
            })
        print(f"[AgentDojo heldout] built {suite_name}: {len(groups)} archives", flush=True)

    instances: list[dict[str, Any]] = []
    views: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    regimes = tuple(config["confidence_regimes"])
    for archive_index, archive in enumerate(archives):
        lineages = {key: tuple(value) for key, value in archive["lineages"].items()}
        by_depth = tuple(tuple(layer) for layer in archive["by_depth"])
        weights = {node: weights_by_depth[depth] for depth, layer in enumerate(by_depth) for node in layer}
        masks_by_condition = {
            condition: distinct_mask_views(
                archive["archive_id"], lineages, condition, specification,
                config["mask_seed_namespace"],
            )
            for condition, specification in config["provenance_conditions"].items()
        }
        for source_index, true_source in enumerate(source_ids):
            length = 1 + (archive_index + source_index) % 3
            regime = regimes[(archive_index * len(source_ids) + source_index) % len(regimes)]
            decoy = source_ids[(source_index + 1) % len(source_ids)]
            source_prior = regime_prior(source_ids, true_source, decoy, config["source_priors"][regime])
            affected = frozenset(lineages[true_source][:length])
            instance = {
                "instance_id": f"{archive['archive_id']}--truth-{source_index}",
                "archive_id": archive["archive_id"], "suite": archive["suite"],
                "true_source": true_source, "true_cascade_length": length,
                "confidence_regime": regime, "decoy_source": decoy,
                "source_prior": source_prior, "affected_ids": sorted(affected),
            }
            instances.append(instance)
            truth = LatentSourceWorld(true_source, affected, 1.0)
            for condition, masks in masks_by_condition.items():
                for mask in masks:
                    posterior, completions = build_posterior(
                        source_ids, by_depth, mask["observed_edges"], source_prior, length_prior,
                    )
                    truth_support = sum(
                        world.weight for world in posterior.worlds
                        if world.source_id == true_source and world.affected_ids == affected
                    )
                    views.append({
                        "instance_id": instance["instance_id"], "condition": condition,
                        "mask_replicate": mask["mask_replicate"], "mask_nonce": mask["mask_nonce"],
                        "observed_edges": [list(edge) for edge in mask["observed_edges"]],
                        "completion_count": completions, "posterior_worlds": len(posterior.worlds),
                        "truth_support": truth_support,
                    })
                    for budget in budgets:
                        tr = run_terminal_recovery_dcta(
                            posterior, truth, budget, weights=weights, quarantine_capacity=capacity,
                        )
                        tr_row = result_row(
                            instance, condition, "tr_dcta", budget, None, tr.replayed_ids,
                            tr.final_posterior, weights, capacity, archive["clean_fallback_safe"],
                        )
                        tr_row["mask_replicate"] = mask["mask_replicate"]
                        rows.append(tr_row)
                        for method in STRUCTURED:
                            sc_mode = None
                            override = None
                            if method == "sc_dcta":
                                sc = confidence_aware_decision(posterior, budget, weights)
                                sc_mode = sc.mode
                                policy = "top1_dcta" if sc.mode == "hard" else "prob_dcta"
                                outcome = run_latent_policy(posterior, truth, budget, method=policy, weights=weights)
                            elif method == "hard_source_dcta":
                                outcome = run_latent_policy(posterior, truth, budget, method="top1_dcta", weights=weights)
                            elif method == "positive_only_dcta":
                                outcome = run_latent_policy(posterior, truth, budget, method="positive_only_risk", weights=weights)
                            elif method == "oracle_source":
                                outcome = run_latent_policy(
                                    posterior.restrict_source(true_source), truth, budget,
                                    method="prob_dcta", weights=weights,
                                )
                            elif method == "full_information_hindsight":
                                outcome = run_latent_policy(posterior, truth, budget, method="prob_dcta", weights=weights)
                                clean_fill = [node for node in sorted(posterior.candidates) if node not in affected]
                                override = tuple(sorted(affected)) + tuple(clean_fill[:capacity - len(affected)])
                            else:
                                outcome = run_latent_policy(posterior, truth, budget, method=method, weights=weights)
                            method_row = result_row(
                                instance, condition, method, budget, None,
                                outcome.replayed_ids, outcome.final_posterior, weights, capacity,
                                archive["clean_fallback_safe"], sc_mode=sc_mode,
                                quarantine_override=override,
                            )
                            method_row["mask_replicate"] = mask["mask_replicate"]
                            rows.append(method_row)
                        for replicate in range(int(config["random_replicates"])):
                            replayed, final = random_policy(
                                posterior, affected, budget,
                                stable_seed(
                                    config["random_seed"], instance["instance_id"], condition,
                                    mask["mask_replicate"], budget, replicate,
                                ),
                            )
                            random_row = result_row(
                                instance, condition, "random", budget, replicate, replayed, final,
                                weights, capacity, archive["clean_fallback_safe"],
                            )
                            random_row["mask_replicate"] = mask["mask_replicate"]
                            rows.append(random_row)
        print(f"[AgentDojo heldout] evaluated {archive_index + 1}/{len(archives)} archives", flush=True)

    primary_condition = config["primary_condition"]
    primary_budget = int(config["primary_budget"])
    suites_by_archive = {archive["archive_id"]: archive["suite"] for archive in archives}
    primary: dict[str, Any] = {}
    comparisons: dict[str, Any] = {}
    for metric_index, metric in enumerate(config["primary_estimands"]):
        values = archive_values(rows, primary_condition, primary_budget, metric)
        primary[metric] = {
            method: statistics.fmean(by_method[method] for by_method in values.values())
            for method in config["methods"]
        }
        comparisons[metric] = {}
        for comparator_index, comparator in enumerate(config["primary_comparators"]):
            comparisons[metric][comparator] = stratified_paired_bootstrap(
                values, suites_by_archive, "tr_dcta", comparator,
                int(config["bootstrap_draws"]),
                int(config["bootstrap_seed"]) + 100 * metric_index + comparator_index,
            )

    partial_masks = defaultdict(set)
    for view in views:
        if view["condition"] == "partial_67":
            archive_id = instances[[i["instance_id"] for i in instances].index(view["instance_id"])]["archive_id"]
            partial_masks[archive_id].add(tuple(tuple(edge) for edge in view["observed_edges"]))
    expected_views = len(instances) * 6
    expected_scenarios = expected_views * len(budgets)
    executable_integrity = all(
        record[polarity]["error"] is None
        and (record[polarity]["attack_success"] if polarity == "positive" else record[polarity]["safe_success"])
        and (not record[polarity]["safe_success"] if polarity == "positive" else not record[polarity]["attack_success"])
        for archive in archives for record in archive["replay_map"].values()
        for polarity in ("negative", "positive")
    )
    integrity = {
        "archive_count_exact": len(archives) == 32,
        "suite_balance_exact": all(sum(a["suite"] == suite for a in archives) == 8 for suite in config["suites"]),
        "no_development_user_overlap": all(a["user_task_id"] not in development_users[a["suite"]] for a in archives),
        "instance_count_exact": len(instances) == 96,
        "regime_balance_exact": all(sum(i["confidence_regime"] == regime for i in instances) == 24 for regime in regimes),
        "length_balance_exact": all(sum(i["true_cascade_length"] == length for i in instances) == 32 for length in (1, 2, 3)),
        "view_count_exact": len(views) == expected_views,
        "five_distinct_partial_masks_per_archive": all(len(value) == 5 for value in partial_masks.values()) and len(partial_masks) == 32,
        "executable_binary_labels_valid": executable_integrity,
        "truth_has_positive_posterior_support": all(view["truth_support"] > 0.0 for view in views),
        "tr_grid_complete": sum(row["method"] == "tr_dcta" for row in rows) == expected_scenarios,
        "structured_grid_complete": sum(row["method"] in STRUCTURED for row in rows) == expected_scenarios * len(STRUCTURED),
        "random_grid_complete": sum(row["method"] == "random" for row in rows) == expected_scenarios * int(config["random_replicates"]),
        "replay_budget_exact": all(len(row["replayed_ids"]) == row["budget"] for row in rows),
        "bootstrap_complete": all(len(value) == len(config["primary_comparators"]) for value in comparisons.values()),
    }
    report = {
        "schema_version": "agentdojo-tr-dcta-method-heldout-v1",
        "protocol": config["protocol"], "phase": config["phase"],
        "claim_boundary": config["claim_boundary"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE" if all(integrity.values()) else "INVALID",
        "method_changed_after_development": False,
        "artifact_hashes": {
            "config": digest(args.config), "runner": digest(Path(__file__)),
            **{key.removesuffix("_sha256"): digest(path) for key, path in source_files.items()},
        },
        "counts": {
            "suites": 4, "archives": len(archives), "truth_instances": len(instances),
            "posterior_views": len(views), "method_runs": len(rows),
            "partial_masks_per_archive": 5,
        },
        "screening": screening, "integrity": integrity,
        "primary_partial_67_budget4": primary,
        "paired_suite_stratified_archive_bootstrap": comparisons,
        "summary": aggregate(rows), "archives": archives, "instances": instances,
        "views": views, "rows": rows, "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "counts": report["counts"],
        "integrity": integrity, "primary_partial_67_budget4": primary,
        "paired_bootstrap": comparisons, "elapsed_s": report["elapsed_s"],
    }, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
