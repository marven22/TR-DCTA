"""Run the frozen BabyAI/MiniGrid method-development evaluation."""

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
from mcx.prob_dcta_benchmark import (
    LatentSourcePosterior,
    LatentSourceWorld,
    run_latent_policy,
)
from run_babyai_minigrid_go_no_go_v1 import execute, make_env, target_color


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "babyai_minigrid_method_development_freeze_v1.json"
PROTOCOL = ROOT / "docs" / "BABYAI_MINIGRID_METHOD_DEVELOPMENT_PROTOCOL_V1.md"
OUTPUT = ROOT / "reports" / "babyai_minigrid_method_development_v1.json"

STRUCTURED_METHODS = (
    "sc_dcta",
    "prob_dcta",
    "hard_source_dcta",
    "ens",
    "source_ig",
    "static_risk",
    "oracle_source",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_seed(*parts: object) -> int:
    text = ":".join(map(str, parts))
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def mission_for(env_id: str, seed: int) -> tuple[str, str]:
    env = make_env(env_id)
    observation, _ = env.reset(seed=seed)
    mission = str(observation["mission"])
    env.close()
    return mission, target_color(mission)


def donor_seeds(env_id: str, colors: tuple[str, ...]) -> dict[str, int]:
    donors: dict[str, int] = {}
    for seed in range(1000):
        _, color = mission_for(env_id, seed)
        donors.setdefault(color, seed)
        if all(color in donors for color in colors):
            return donors
    raise RuntimeError("could not find a donor context for every source color")


def source_prior(
    config: dict[str, Any], regime: str, true_source: str, decoy: str,
) -> dict[str, float]:
    specification = config["source_priors"][regime]
    prior = {}
    for color in config["colors"]:
        role = "true" if color == true_source else "decoy" if color == decoy else "other"
        prior[color] = float(specification[role])
    total = sum(prior.values())
    if abs(total - 1.0) > 1e-12:
        raise ValueError(f"source prior does not sum to one: {regime}: {total}")
    return prior


def posterior_for(
    colors: tuple[str, ...], variants: tuple[str, ...], prior: dict[str, float],
) -> LatentSourcePosterior:
    candidates = tuple(f"{color}::{variant}" for color in colors for variant in variants)
    worlds = tuple(
        LatentSourceWorld(
            color,
            frozenset(f"{color}::{variant}" for variant in variants),
            prior[color],
        )
        for color in colors
        if prior[color] > 0.0
    )
    return LatentSourcePosterior(candidates, colors, worlds).normalize()


def random_policy(
    posterior: LatentSourcePosterior,
    affected: frozenset[str],
    budget: int,
    seed: int,
) -> tuple[tuple[str, ...], LatentSourcePosterior]:
    rng = random.Random(seed)
    remaining = list(posterior.candidates)
    belief = posterior
    replayed: list[str] = []
    for _ in range(min(budget, len(remaining))):
        chosen = remaining.pop(rng.randrange(len(remaining)))
        replayed.append(chosen)
        conditioned = belief.condition(chosen, int(chosen in affected))
        if conditioned is not None:
            belief = conditioned
    return tuple(replayed), belief


def predict_source(posterior: LatentSourcePosterior) -> str:
    probabilities = posterior.source_probabilities()
    return min(posterior.source_ids, key=lambda source: (-probabilities[source], source))


def result_row(
    *, archive_id: str, regime: str, true_source: str, decoy: str,
    method: str, budget: int, replicate: int | None,
    replayed: tuple[str, ...], final: LatentSourcePosterior,
    affected: frozenset[str], replay_map: dict[str, dict[str, Any]],
    sc_mode: str | None,
) -> dict[str, Any]:
    labels = tuple(int(not replay_map[node]["success"]) for node in replayed)
    if labels != tuple(int(node in affected) for node in replayed):
        raise RuntimeError("environment replay label disagrees with private lineage truth")
    hits = len(set(replayed) & affected)
    predicted = predict_source(final)
    correct = predicted == true_source
    return {
        "archive_id": archive_id,
        "regime": regime,
        "true_source": true_source,
        "decoy_source": decoy,
        "method": method,
        "budget": budget,
        "replicate": replicate,
        "replayed_ids": list(replayed),
        "labels": list(labels),
        "corrupt_discoveries": hits,
        "corrupt_descendant_recall": hits / len(affected),
        "audit_yield": hits / len(replayed),
        "predicted_source": predicted,
        "true_source_probability": final.source_probabilities()[true_source],
        "source_identification_accuracy": float(correct),
        "quarantine_precision": float(correct),
        "clean_descendants_removed": 0 if correct else len(affected),
        "corrupt_descendants_left": 0 if correct else len(affected),
        "robot_recovery_success": float(correct),
        "sc_mode": sc_mode,
    }


def aggregate(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[key] for key in keys)].append(row)
    metrics = (
        "corrupt_discoveries",
        "corrupt_descendant_recall",
        "audit_yield",
        "true_source_probability",
        "source_identification_accuracy",
        "quarantine_precision",
        "clean_descendants_removed",
        "corrupt_descendants_left",
        "robot_recovery_success",
    )
    output = []
    for key, values in sorted(grouped.items(), key=lambda item: str(item[0])):
        record = {name: value for name, value in zip(keys, key)}
        record["runs"] = len(values)
        for metric in metrics:
            record[f"mean_{metric}"] = statistics.fmean(float(row[metric]) for row in values)
        output.append(record)
    return output


def archive_means(
    rows: list[dict[str, Any]], method: str, budget: int, metric: str,
) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["method"] == method and row["budget"] == budget:
            grouped[row["archive_id"]].append(float(row[metric]))
    return {archive: statistics.fmean(values) for archive, values in grouped.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    colors = tuple(config["colors"])
    variants = tuple(config["variants"])
    budgets = tuple(map(int, config["budgets"]))
    env_id = str(config["env_id"])
    donors = donor_seeds(env_id, colors)
    started = time.perf_counter()

    archives = []
    rows: list[dict[str, Any]] = []
    local_checks = []
    execution_errors = []
    regimes = tuple(config["confidence_regimes"])
    first_seed = int(config["context_seeds"]["start"])
    context_count = int(config["context_seeds"]["count"])

    for offset, seed in enumerate(range(first_seed, first_seed + context_count)):
        mission, target = mission_for(env_id, seed)
        eligible = tuple(color for color in colors if color != target)
        true_source = eligible[(offset * 7 + 1) % len(eligible)]
        decoy = eligible[(eligible.index(true_source) + 1) % len(eligible)]
        regime = regimes[offset % len(regimes)]
        prior = source_prior(config, regime, true_source, decoy)
        archive_id = f"babyai-odc-seed-{seed:04d}"
        affected = frozenset(f"{true_source}::{variant}" for variant in variants)
        replay_map: dict[str, dict[str, Any]] = {}

        for color in colors:
            for variant in variants:
                node = f"{color}::{variant}"
                behavior_color = color if color == true_source else target
                try:
                    outcome = execute(
                        env_id, seed, behavior_color, variant, int(config["max_steps"])
                    )
                except Exception as exc:  # pragma: no cover - recorded for protocol failure
                    execution_errors.append({
                        "archive_id": archive_id,
                        "node_id": node,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    continue
                replay_map[node] = {
                    "family": color,
                    "variant": variant,
                    "behavior_color": behavior_color,
                    "success": bool(outcome["success"]),
                    "reward": float(outcome["reward"]),
                    "steps": int(outcome["steps"]),
                }

        for variant in variants:
            local = execute(
                env_id,
                donors[true_source],
                true_source,
                variant,
                int(config["max_steps"]),
            )
            local_checks.append({
                "archive_id": archive_id,
                "source": true_source,
                "variant": variant,
                "donor_seed": donors[true_source],
                "success": bool(local["success"]),
            })

        if len(replay_map) != len(colors) * len(variants):
            continue
        if any(replay_map[node]["success"] for node in affected):
            execution_errors.append({"archive_id": archive_id, "error": "corrupt memory succeeded"})
            continue
        if any(not value["success"] for node, value in replay_map.items() if node not in affected):
            execution_errors.append({"archive_id": archive_id, "error": "clean memory failed"})
            continue

        archive = {
            "archive_id": archive_id,
            "target_seed": seed,
            "mission": mission,
            "target_color": target,
            "regime": regime,
            "source_prior": prior,
            "true_source": true_source,
            "decoy_source": decoy,
            "affected_ids": sorted(affected),
            "lineages": {
                color: [f"{color}::{variant}" for variant in variants] for color in colors
            },
            "replay_map": replay_map,
        }
        archives.append(archive)
        posterior = posterior_for(colors, variants, prior)
        truth = LatentSourceWorld(true_source, affected, 1.0)
        weights = {node: 1.0 for node in posterior.candidates}

        for budget in budgets:
            for method in STRUCTURED_METHODS:
                sc_mode = None
                belief = posterior
                if method == "sc_dcta":
                    decision = confidence_aware_decision(posterior, budget, weights)
                    sc_mode = decision.mode
                    effective = "top1_dcta" if decision.mode == "hard" else "prob_dcta"
                    outcome = run_latent_policy(
                        posterior, truth, budget, method=effective, weights=weights
                    )
                elif method == "hard_source_dcta":
                    outcome = run_latent_policy(
                        posterior, truth, budget, method="top1_dcta", weights=weights
                    )
                elif method == "oracle_source":
                    belief = posterior.restrict_source(true_source)
                    outcome = run_latent_policy(
                        belief, truth, budget, method="prob_dcta", weights=weights
                    )
                else:
                    outcome = run_latent_policy(
                        posterior, truth, budget, method=method, weights=weights
                    )
                rows.append(result_row(
                    archive_id=archive_id,
                    regime=regime,
                    true_source=true_source,
                    decoy=decoy,
                    method=method,
                    budget=budget,
                    replicate=None,
                    replayed=outcome.replayed_ids,
                    final=outcome.final_posterior,
                    affected=affected,
                    replay_map=replay_map,
                    sc_mode=sc_mode,
                ))

            for replicate in range(int(config["random_replicates"])):
                replayed, final = random_policy(
                    posterior,
                    affected,
                    budget,
                    stable_seed(config["random_seed"], archive_id, budget, replicate),
                )
                rows.append(result_row(
                    archive_id=archive_id,
                    regime=regime,
                    true_source=true_source,
                    decoy=decoy,
                    method="random",
                    budget=budget,
                    replicate=replicate,
                    replayed=replayed,
                    final=final,
                    affected=affected,
                    replay_map=replay_map,
                    sc_mode=None,
                ))

        if (offset + 1) % 15 == 0:
            print(f"[archives] {offset + 1}/{context_count}", flush=True)

    expected_archives = context_count
    expected_structured = expected_archives * len(budgets) * len(STRUCTURED_METHODS)
    expected_random = expected_archives * len(budgets) * int(config["random_replicates"])
    sc4 = archive_means(rows, "sc_dcta", 4, config["primary_metric"])
    ens4 = archive_means(rows, "ens", 4, config["primary_metric"])
    random4 = archive_means(rows, "random", 4, config["primary_metric"])
    common = sorted(set(sc4) & set(ens4) & set(random4))
    sc_mean = statistics.fmean(sc4[key] for key in common) if common else 0.0
    ens_mean = statistics.fmean(ens4[key] for key in common) if common else 0.0
    random_mean = statistics.fmean(random4[key] for key in common) if common else 0.0

    criteria = {
        "all_archives_executable": len(archives) == expected_archives and not execution_errors,
        "all_replay_labels_environment_verified": all(
            (node in set(archive["affected_ids"])) == (not value["success"])
            for archive in archives for node, value in archive["replay_map"].items()
        ),
        "all_local_source_memories_correct": len(local_checks) == expected_archives * len(variants)
        and all(row["success"] for row in local_checks),
        "structured_runs_complete": sum(row["method"] != "random" for row in rows)
        == expected_structured,
        "random_runs_complete": sum(row["method"] == "random" for row in rows)
        == expected_random,
        "all_budgets_respected": all(len(row["replayed_ids"]) == row["budget"] for row in rows),
        "no_repeat_replays": all(
            len(row["replayed_ids"]) == len(set(row["replayed_ids"])) for row in rows
        ),
        "sc_dcta_not_worse_than_ens_at_budget_4": sc_mean >= ens_mean - 1e-12,
        "sc_dcta_better_than_random_at_budget_4": sc_mean > random_mean + 1e-12,
    }
    execution_valid = all(value for key, value in criteria.items() if not key.startswith("sc_dcta_"))
    method_go = criteria["sc_dcta_not_worse_than_ens_at_budget_4"] and criteria[
        "sc_dcta_better_than_random_at_budget_4"
    ]
    decision = "GO" if execution_valid and method_go else "NO_GO"
    report = {
        "schema_version": "babyai-minigrid-method-development-v1",
        "protocol": config["protocol"],
        "phase": config["phase"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "decision_interpretation": (
            "advance_to_held_out_evaluation" if decision == "GO"
            else "do_not_advance_without_redesign"
        ),
        "artifact_hashes": {
            "config": digest(args.config),
            "protocol": digest(PROTOCOL),
            "runner": digest(Path(__file__)),
        },
        "counts": {
            "archives": len(archives),
            "memories_per_archive": len(colors) * len(variants),
            "environment_replay_outcomes": sum(len(a["replay_map"]) for a in archives),
            "local_correctness_checks": len(local_checks),
            "structured_method_runs": sum(row["method"] != "random" for row in rows),
            "random_runs": sum(row["method"] == "random" for row in rows),
            "total_method_runs": len(rows),
            "execution_errors": len(execution_errors),
        },
        "regime_counts": dict(Counter(archive["regime"] for archive in archives)),
        "source_counts": dict(Counter(archive["true_source"] for archive in archives)),
        "sc_mode_counts": dict(Counter(
            row["sc_mode"] for row in rows
            if row["method"] == "sc_dcta" and row["sc_mode"] is not None
        )),
        "primary_budget_4_comparison": {
            "metric": config["primary_metric"],
            "sc_dcta": sc_mean,
            "ens": ens_mean,
            "random": random_mean,
            "sc_minus_ens": sc_mean - ens_mean,
            "sc_minus_random": sc_mean - random_mean,
            "paired_archives": len(common),
        },
        "criteria": criteria,
        "summary": {
            "overall_by_method_budget": aggregate(rows, ("method", "budget")),
            "by_regime_method_budget": aggregate(rows, ("regime", "method", "budget")),
        },
        "donor_seeds": donors,
        "archives": archives,
        "local_checks": local_checks,
        "execution_errors": execution_errors,
        "rows": rows,
        "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": decision,
        "counts": report["counts"],
        "regime_counts": report["regime_counts"],
        "sc_mode_counts": report["sc_mode_counts"],
        "primary_budget_4_comparison": report["primary_budget_4_comparison"],
        "criteria": criteria,
        "elapsed_s": report["elapsed_s"],
    }, indent=2))
    return 0 if execution_valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
