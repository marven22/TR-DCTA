"""Run the frozen paper-facing BabyAI/MiniGrid held-out evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.confidence_aware_dcta import confidence_aware_decision
from mcx.prob_dcta_benchmark import LatentSourceWorld, run_latent_policy
from run_babyai_minigrid_go_no_go_v1 import execute, make_env, target_color
from run_babyai_minigrid_partial_provenance_v1 import (
    aggregate,
    build_posterior,
    make_row,
    observed_edges,
    opaque_lineages,
    random_policy,
    stable_seed,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "babyai_minigrid_heldout_evaluation_freeze_v1.json"
PROTOCOL = ROOT / "docs" / "BABYAI_MINIGRID_HELDOUT_EVALUATION_PROTOCOL_V1.md"
OUTPUT = ROOT / "reports" / "babyai_minigrid_heldout_evaluation_v1.json"
STRUCTURED = ("sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "source_ig",
              "static_risk", "oracle_source")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mission_for(env_id: str, seed: int) -> tuple[str, str]:
    env = make_env(env_id)
    observation, _ = env.reset(seed=seed)
    mission = str(observation["mission"])
    env.close()
    return mission, target_color(mission)


def donor_seeds(env_id: str, colors: tuple[str, ...]) -> dict[str, int]:
    donors = {}
    for seed in range(1000):
        _, color = mission_for(env_id, seed)
        donors.setdefault(color, seed)
        if all(color in donors for color in colors):
            return donors
    raise RuntimeError("donor seed unavailable for at least one color")


def source_prior(config: dict[str, Any], regime: str, true: str, decoy: str) -> dict[str, float]:
    specification = config["source_priors"][regime]
    prior = {}
    for color in config["colors"]:
        role = "true" if color == true else "decoy" if color == decoy else "other"
        prior[color] = float(specification[role])
    if abs(sum(prior.values()) - 1.0) > 1e-12:
        raise ValueError("invalid held-out source prior")
    return prior


def build_archive(
    config: dict[str, Any], seed: int, donors: dict[str, int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    colors = tuple(config["colors"])
    variants = tuple(config["variants"])
    mission, target = mission_for(config["env_id"], seed)
    eligible = tuple(color for color in colors if color != target)
    true_source = eligible[(seed * 7 + 1) % len(eligible)]
    decoy = eligible[(eligible.index(true_source) + 1) % len(eligible)]
    regime = config["confidence_regimes"][seed % len(config["confidence_regimes"])]
    archive_id = f"babyai-odc-heldout-{seed:04d}"
    affected = {f"{true_source}::{variant}" for variant in variants}
    replay_map = {}
    for color in colors:
        for variant in variants:
            private_id = f"{color}::{variant}"
            behavior_color = color if color == true_source else target
            outcome = execute(
                config["env_id"], seed, behavior_color, variant, int(config["max_steps"]))
            replay_map[private_id] = {
                "family": color, "variant": variant, "behavior_color": behavior_color,
                "success": bool(outcome["success"]), "reward": float(outcome["reward"]),
                "steps": int(outcome["steps"]),
            }
    if {node for node, value in replay_map.items() if not value["success"]} != affected:
        raise RuntimeError(f"held-out executable labels invalid: {archive_id}")
    local_checks = []
    for variant in variants:
        outcome = execute(
            config["env_id"], donors[true_source], true_source, variant,
            int(config["max_steps"]))
        local_checks.append({
            "archive_id": archive_id, "source": true_source, "variant": variant,
            "donor_seed": donors[true_source], "success": bool(outcome["success"]),
        })
    if not all(row["success"] for row in local_checks):
        raise RuntimeError(f"held-out local correctness failed: {archive_id}")
    archive = {
        "archive_id": archive_id, "target_seed": seed, "mission": mission,
        "target_color": target, "regime": regime,
        "source_prior": source_prior(config, regime, true_source, decoy),
        "true_source": true_source, "decoy_source": decoy,
        "affected_ids": sorted(affected),
        "lineages": {color: [f"{color}::{variant}" for variant in variants]
                     for color in colors},
        "replay_map": replay_map,
    }
    return archive, local_checks


def archive_method_means(
    rows: list[dict[str, Any]], condition: str, budget: int, metric: str,
) -> dict[str, dict[str, float]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["condition"] == condition and row["budget"] == budget:
            grouped[(row["archive_id"], row["method"])].append(float(row[metric]))
    result: dict[str, dict[str, float]] = defaultdict(dict)
    for (archive, method), values in grouped.items():
        result[archive][method] = statistics.fmean(values)
    return dict(result)


def paired_bootstrap(
    values: dict[str, dict[str, float]], left: str, right: str,
    draws: int, seed: int, margin: float, claim: str,
) -> dict[str, Any]:
    archives = sorted(key for key, row in values.items() if left in row and right in row)
    differences = [values[key][left] - values[key][right] for key in archives]
    rng = random.Random(seed)
    samples = []
    count = len(differences)
    for _ in range(draws):
        samples.append(sum(differences[rng.randrange(count)] for _ in range(count)) / count)
    samples.sort()
    lower = samples[int(0.025 * draws)]
    upper = samples[min(int(0.975 * draws), draws - 1)]
    estimate = statistics.fmean(differences)
    passed = lower > 0.0 if claim == "superiority" else lower > -margin
    return {
        "left": left, "right": right, "claim": claim, "paired_archives": count,
        "estimate": estimate, "lower_95": lower, "upper_95": upper,
        "noninferiority_margin": margin if claim == "noninferiority" else None,
        "claim_passed": passed,
        "wins": sum(value > 0 for value in differences),
        "ties": sum(value == 0 for value in differences),
        "losses": sum(value < 0 for value in differences),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    for name in ("complete_method_report", "partial_report"):
        path = ROOT / config["development_artifacts"][name]
        expected = config["development_artifacts"][f"{name}_sha256"]
        if digest(path) != expected:
            raise ValueError(f"development artifact changed: {name}")
    start = int(config["heldout_seeds"]["start"])
    stop = int(config["heldout_seeds"]["stop_exclusive"])
    if start < int(config["development_seeds"]["stop_exclusive"]):
        raise ValueError("held-out range overlaps development")
    colors = tuple(config["colors"])
    variants = tuple(config["variants"])
    budgets = tuple(map(int, config["budgets"]))
    donors = donor_seeds(config["env_id"], colors)
    archives = []
    local_checks = []
    views = []
    rows = []
    started = time.perf_counter()

    for index, seed in enumerate(range(start, stop), start=1):
        archive, checks = build_archive(config, seed, donors)
        archives.append(archive)
        local_checks.extend(checks)
        lineages, private_to_opaque, by_depth = opaque_lineages(archive, variants)
        affected = frozenset(private_to_opaque[node] for node in archive["affected_ids"])
        labels = {private_to_opaque[node]: int(not value["success"])
                  for node, value in archive["replay_map"].items()}
        truth = LatentSourceWorld(archive["true_source"], affected, 1.0)
        for condition, specification in config["provenance_conditions"].items():
            hidden = int(specification["hidden_links_per_layer"])
            observed = observed_edges(archive["archive_id"], lineages, hidden)
            posterior, completions = build_posterior(
                colors, by_depth, observed, archive["source_prior"])
            weights = {node: 1.0 for node in posterior.candidates}
            views.append({
                "archive_id": archive["archive_id"], "condition": condition,
                "observed_edges": [list(edge) for edge in observed],
                "observed_edge_count": len(observed), "hidden_edge_count": 18 - len(observed),
                "completion_count": completions, "posterior_world_count": len(posterior.worlds),
            })
            for budget in budgets:
                for method in STRUCTURED:
                    sc_mode = None
                    if method == "sc_dcta":
                        decision = confidence_aware_decision(posterior, budget, weights)
                        sc_mode = decision.mode
                        effective = "top1_dcta" if decision.mode == "hard" else "prob_dcta"
                        outcome = run_latent_policy(
                            posterior, truth, budget, method=effective, weights=weights)
                    elif method == "hard_source_dcta":
                        outcome = run_latent_policy(
                            posterior, truth, budget, method="top1_dcta", weights=weights)
                    elif method == "oracle_source":
                        restricted = posterior.restrict_source(archive["true_source"])
                        outcome = run_latent_policy(
                            restricted, truth, budget, method="prob_dcta", weights=weights)
                    else:
                        outcome = run_latent_policy(
                            posterior, truth, budget, method=method, weights=weights)
                    rows.append(make_row(
                        archive, condition, hidden, completions, len(posterior.worlds),
                        method, budget, None, outcome.replayed_ids, outcome.final_posterior,
                        affected, labels, int(config["quarantine_capacity"]), sc_mode))
                for replicate in range(int(config["random_replicates"])):
                    replayed, final = random_policy(
                        posterior, affected, budget,
                        stable_seed(config["random_seed"], archive["archive_id"],
                                    condition, budget, replicate))
                    rows.append(make_row(
                        archive, condition, hidden, completions, len(posterior.worlds),
                        "random", budget, replicate, replayed, final, affected, labels,
                        int(config["quarantine_capacity"]), None))
        if index % 20 == 0:
            print(f"[heldout archives] {index}/{stop-start}", flush=True)

    comparisons = []
    draws = int(config["bootstrap"]["draws"])
    for condition in ("partial_33", "partial_67"):
        for metric_index, metric in enumerate(config["primary_estimands"]):
            values = archive_method_means(rows, condition, int(config["primary_budget"]), metric)
            for comparison_index, comparison in enumerate(config["confirmatory_comparisons"]):
                result = paired_bootstrap(
                    values, comparison["left"], comparison["right"], draws,
                    stable_seed(config["bootstrap"]["seed"], condition, metric,
                                comparison_index, metric_index),
                    float(config["noninferiority_margin"]), comparison["claim"])
                comparisons.append({"condition": condition, "budget": 4,
                                    "metric": metric, **result})

    expected_archives = int(config["heldout_seeds"]["count"])
    expected_views = expected_archives * len(config["provenance_conditions"])
    expected_structured = expected_views * len(budgets) * len(STRUCTURED)
    expected_random = expected_views * len(budgets) * int(config["random_replicates"])
    integrity = {
        "heldout_seed_count": len(archives) == expected_archives,
        "no_development_overlap": all(archive["target_seed"] >= 60 for archive in archives),
        "all_environment_labels_valid": all(
            {node for node, value in archive["replay_map"].items() if not value["success"]}
            == set(archive["affected_ids"]) for archive in archives),
        "all_local_memories_correct": len(local_checks) == expected_archives * 3
        and all(row["success"] for row in local_checks),
        "paired_views_complete": len(views) == expected_views,
        "structured_grid_complete": sum(row["method"] != "random" for row in rows)
        == expected_structured,
        "random_grid_complete": sum(row["method"] == "random" for row in rows)
        == expected_random,
        "budgets_exact": all(len(row["replayed_ids"]) == row["budget"] for row in rows),
        "no_repeat_replays": all(len(row["replayed_ids"]) == len(set(row["replayed_ids"]))
                                 for row in rows),
        "bootstrap_complete": len(comparisons) == 16
        and all(row["paired_archives"] == expected_archives for row in comparisons),
    }
    if not all(integrity.values()):
        raise RuntimeError(f"held-out evaluation integrity failure: {integrity}")
    report = {
        "schema_version": "babyai-minigrid-heldout-evaluation-v1",
        "protocol": config["protocol"], "phase": config["phase"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_status": "COMPLETE", "method_frozen": True,
        "artifact_hashes": {
            "config": digest(args.config), "protocol": digest(PROTOCOL),
            "runner": digest(Path(__file__)),
            "partial_runner_dependency": digest(
                ROOT / "scripts" / "run_babyai_minigrid_partial_provenance_v1.py"),
            "planner_dependency": digest(
                ROOT / "scripts" / "run_babyai_minigrid_go_no_go_v1.py"),
        },
        "integrity": integrity,
        "counts": {
            "heldout_archives": len(archives), "environment_replay_outcomes": len(archives)*18,
            "local_correctness_checks": len(local_checks), "paired_provenance_views": len(views),
            "structured_method_runs": expected_structured, "random_runs": expected_random,
            "total_method_runs": len(rows),
        },
        "regime_counts": dict(Counter(a["regime"] for a in archives)),
        "target_color_counts": dict(Counter(a["target_color"] for a in archives)),
        "source_counts": dict(Counter(a["true_source"] for a in archives)),
        "sc_mode_counts": dict(Counter(row["sc_mode"] for row in rows
                                        if row["method"] == "sc_dcta")),
        "summary": {
            "by_condition_method_budget": aggregate(rows, ("condition", "method", "budget")),
            "by_regime_condition_method_budget": aggregate(
                rows, ("regime", "condition", "method", "budget")),
        },
        "confirmatory_comparisons": comparisons,
        "donor_seeds": donors, "archives": archives, "local_checks": local_checks,
        "views": views, "rows": rows, "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    key_results = [row for row in report["summary"]["by_condition_method_budget"]
                   if row["budget"] == 4 and row["method"] in
                   {"sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "random", "oracle_source"}]
    print(json.dumps({"evaluation_status": "COMPLETE", "counts": report["counts"],
                      "integrity": integrity, "key_budget_4_results": key_results,
                      "confirmatory_comparisons": comparisons,
                      "elapsed_s": report["elapsed_s"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
