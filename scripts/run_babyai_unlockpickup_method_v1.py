"""Run frozen stochastic-cascade UnlockPickup method studies."""

from __future__ import annotations

import argparse
import hashlib
import itertools
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
from mcx.prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld, run_latent_policy
from run_babyai_minigrid_partial_provenance_v1 import (
    layer_options, observed_edges, opaque_lineages, random_policy, stable_seed,
)
from run_babyai_unlockpickup_go_no_go_v1 import execute


ROOT = Path(__file__).resolve().parents[1]
STRUCTURED = ("sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "source_ig",
              "source_then_dcta", "positive_only_dcta", "static_risk",
              "oracle_source", "full_information_hindsight")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_prior(config: dict[str, Any], regime: str, true: str, decoy: str) -> dict[str, float]:
    specification = config["source_priors"][regime]
    values = {}
    for color in config["colors"]:
        role = "true" if color == true else "decoy" if color == decoy else "other"
        values[color] = float(specification[role])
    if abs(sum(values.values()) - 1.0) > 1e-12:
        raise ValueError("source prior does not sum to one")
    return values


def build_stochastic_posterior(
    colors: tuple[str, ...], by_depth: tuple[tuple[str, ...], ...],
    observed: tuple[tuple[str, str], ...], source_values: dict[str, float],
    length_prior: tuple[float, ...],
) -> tuple[LatentSourcePosterior, int]:
    options = (
        layer_options(colors, by_depth[0], observed),
        layer_options(by_depth[0], by_depth[1], observed),
        layer_options(by_depth[1], by_depth[2], observed),
    )
    completion_count = len(options[0]) * len(options[1]) * len(options[2])
    counts: Counter[tuple[str, int, frozenset[str]]] = Counter()
    for first, second, third in itertools.product(*options):
        maps = (dict(first), dict(second), dict(third))
        for source in colors:
            chain = (maps[0][source],)
            chain += (maps[1][chain[0]],)
            chain += (maps[2][chain[1]],)
            for length in (1, 2, 3):
                counts[(source, length, frozenset(chain[:length]))] += 1
    worlds = []
    for (source, length, affected), count in sorted(
        counts.items(), key=lambda item: (item[0][0], item[0][1], sorted(item[0][2]))
    ):
        weight = source_values[source] * length_prior[length - 1] * count / completion_count
        if weight > 0.0:
            worlds.append(LatentSourceWorld(source, affected, weight))
    candidates = tuple(node for depth in by_depth for node in depth)
    return LatentSourcePosterior(candidates, colors, tuple(worlds)).normalize(), completion_count


def predict_source(posterior: LatentSourcePosterior) -> str:
    values = posterior.source_probabilities()
    return min(posterior.source_ids, key=lambda source: (-values[source], source))


def quarantine(
    posterior: LatentSourcePosterior, weights: dict[str, float], capacity: int,
) -> tuple[str, ...]:
    return tuple(sorted(posterior.candidates,
                        key=lambda node: (-(posterior.marginal(node) * weights[node]), node))[:capacity])


def condition_trace(
    posterior: LatentSourcePosterior, replayed: tuple[str, ...], affected: frozenset[str],
) -> LatentSourcePosterior:
    belief = posterior
    for node in replayed:
        updated = belief.condition(node, int(node in affected))
        if updated is not None:
            belief = updated
    return belief


def make_row(
    archive: dict[str, Any], condition: str, method: str, budget: int,
    replicate: int | None, replayed: tuple[str, ...], final: LatentSourcePosterior,
    affected: frozenset[str], weights: dict[str, float], capacity: int,
    sc_mode: str | None,
) -> dict[str, Any]:
    hits = set(replayed) & affected
    removed = quarantine(final, weights, capacity)
    removed_hits = set(removed) & affected
    total_weight = sum(weights[node] for node in affected)
    predicted = predict_source(final)
    return {
        "archive_id": archive["archive_id"], "seed": archive["seed"],
        "regime": archive["regime"], "true_cascade_length": archive["true_cascade_length"],
        "condition": condition, "method": method, "budget": budget, "replicate": replicate,
        "replayed_ids": list(replayed), "labels": [int(node in affected) for node in replayed],
        "corrupt_discoveries": len(hits), "corrupt_descendant_recall": len(hits)/len(affected),
        "weighted_corrupt_recall": sum(weights[node] for node in hits)/total_weight,
        "audit_yield": len(hits)/budget, "predicted_source": predicted,
        "source_identification_accuracy": float(predicted == archive["true_source"]),
        "true_source_probability": final.source_probabilities()[archive["true_source"]],
        "quarantined_ids": list(removed),
        "quarantine_recall": len(removed_hits)/len(affected),
        "weighted_quarantine_recall": sum(weights[node] for node in removed_hits)/total_weight,
        "clean_descendants_removed": capacity-len(removed_hits),
        "corrupt_descendants_left": len(affected)-len(removed_hits),
        "robot_recovery_success": float(affected.issubset(removed)), "sc_mode": sc_mode,
    }


def aggregate(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    metrics = ("corrupt_discoveries", "corrupt_descendant_recall", "weighted_corrupt_recall",
               "audit_yield", "source_identification_accuracy", "true_source_probability",
               "quarantine_recall", "weighted_quarantine_recall", "clean_descendants_removed",
               "corrupt_descendants_left", "robot_recovery_success")
    output = []
    for key, values in sorted(groups.items(), key=lambda item: str(item[0])):
        record = {name: value for name, value in zip(keys, key)}
        record["runs"] = len(values)
        for metric in metrics:
            record[f"mean_{metric}"] = statistics.fmean(float(row[metric]) for row in values)
        output.append(record)
    return output


def partial_mean(rows: list[dict[str, Any]], method: str, metric: str, budget: int) -> float:
    values = [float(row[metric]) for row in rows if row["method"] == method
              and row["condition"] != "complete" and row["budget"] == budget]
    return statistics.fmean(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    go_path = ROOT / config["go_no_go_report"]
    if digest(go_path) != config["go_no_go_report_sha256"]:
        raise ValueError("frozen UnlockPickup structural report changed")
    colors = tuple(config["colors"])
    variants = tuple(config["variants"])
    length_prior = tuple(map(float, config["cascade_length_prior"]))
    stage_weights = tuple(map(float, config["stage_harm_weights"]))
    budgets = tuple(map(int, config["budgets"]))
    archives = []
    views = []
    rows = []
    errors = []
    started = time.perf_counter()

    for offset, seed in enumerate(range(int(config["seed_start"]),
                                        int(config["seed_stop_exclusive"]))):
        # Obtain the target from one mission-conditioned execution.
        probe = execute(config["env_id"], seed, colors[0], variants[0])
        target = probe["target_color"]
        eligible = tuple(color for color in colors if color != target)
        true_source = eligible[(seed * 7 + 1) % len(eligible)]
        decoy = eligible[(eligible.index(true_source) + 1) % len(eligible)]
        regime = config["confidence_regimes"][seed % len(config["confidence_regimes"])]
        true_length = 1 + seed % 3
        archive_id = f"babyai-unlockpickup-{config['phase']}-{seed:04d}"
        lineages_private = {color: [f"{color}::{variant}" for variant in variants]
                            for color in colors}
        archive = {
            "archive_id": archive_id, "seed": seed, "mission": probe["mission"],
            "target_color": target, "regime": regime, "true_source": true_source,
            "decoy_source": decoy, "true_cascade_length": true_length,
            "source_prior": source_prior(config, regime, true_source, decoy),
            "lineages": lineages_private, "replay_map": {},
        }
        lineages, private_to_opaque, by_depth = opaque_lineages(archive, variants)
        affected_private = {f"{true_source}::{variants[depth]}" for depth in range(true_length)}
        affected = frozenset(private_to_opaque[node] for node in affected_private)
        weights = {private_to_opaque[f"{color}::{variants[depth]}"]: stage_weights[depth]
                   for color in colors for depth in range(3)}
        for color in colors:
            for depth, variant in enumerate(variants):
                private = f"{color}::{variant}"
                active = private in affected_private
                behavior_source = true_source if active else target
                try:
                    outcome = execute(config["env_id"], seed, behavior_source, variant)
                except Exception as exc:
                    errors.append({"archive_id": archive_id, "memory": private,
                                   "error": f"{type(exc).__name__}: {exc}"})
                    continue
                archive["replay_map"][private_to_opaque[private]] = {
                    "private_family": color, "variant": variant, "active_corruption": active,
                    "behavior_source": behavior_source, "success": outcome["success"],
                    "steps": outcome["steps"], "milestones": outcome["milestones"],
                }
        labels = {node for node, value in archive["replay_map"].items() if not value["success"]}
        if labels != set(affected):
            errors.append({"archive_id": archive_id, "error": "executable label mismatch"})
            continue
        archive["affected_ids"] = sorted(affected)
        archives.append(archive)
        truth = LatentSourceWorld(true_source, affected, 1.0)

        for condition, specification in config["provenance_conditions"].items():
            hidden = int(specification["hidden_links_per_layer"])
            observed = observed_edges(archive_id, lineages, hidden)
            posterior, completions = build_stochastic_posterior(
                colors, by_depth, observed, archive["source_prior"], length_prior)
            views.append({"archive_id": archive_id, "condition": condition,
                          "observed_edges": [list(edge) for edge in observed],
                          "completion_count": completions, "posterior_worlds": len(posterior.worlds)})
            for budget in budgets:
                for method in STRUCTURED:
                    sc_mode = None
                    if method == "sc_dcta":
                        decision = confidence_aware_decision(posterior, budget, weights)
                        sc_mode = decision.mode
                        policy = "top1_dcta" if decision.mode == "hard" else "prob_dcta"
                        outcome = run_latent_policy(posterior, truth, budget,
                                                    method=policy, weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    elif method == "hard_source_dcta":
                        outcome = run_latent_policy(posterior, truth, budget,
                                                    method="top1_dcta", weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    elif method == "positive_only_dcta":
                        outcome = run_latent_policy(posterior, truth, budget,
                                                    method="positive_only_risk", weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    elif method == "oracle_source":
                        restricted = posterior.restrict_source(true_source)
                        outcome = run_latent_policy(restricted, truth, budget,
                                                    method="prob_dcta", weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    elif method == "full_information_hindsight":
                        ordered = sorted(affected, key=lambda node: (-weights[node], node))
                        ordered += [node for node in sorted(posterior.candidates)
                                    if node not in affected]
                        replayed = tuple(ordered[:budget])
                        final = condition_trace(posterior, replayed, affected)
                    else:
                        policy = "source_then_dcta" if method == "source_then_dcta" else method
                        outcome = run_latent_policy(posterior, truth, budget,
                                                    method=policy, weights=weights)
                        replayed, final = outcome.replayed_ids, outcome.final_posterior
                    rows.append(make_row(archive, condition, method, budget, None, replayed,
                                         final, affected, weights,
                                         int(config["quarantine_capacity"]), sc_mode))
                for replicate in range(int(config["random_replicates"])):
                    replayed, final = random_policy(
                        posterior, affected, budget,
                        stable_seed(config["random_seed"], archive_id, condition, budget, replicate))
                    rows.append(make_row(archive, condition, "random", budget, replicate,
                                         replayed, final, affected, weights,
                                         int(config["quarantine_capacity"]), None))
        if (offset + 1) % 10 == 0:
            print(f"[archives] {offset+1}/{int(config['seed_stop_exclusive'])-int(config['seed_start'])}",
                  flush=True)

    archive_count = int(config["seed_stop_exclusive"])-int(config["seed_start"])
    expected_structured = archive_count*3*len(budgets)*len(STRUCTURED)
    expected_random = archive_count*3*len(budgets)*int(config["random_replicates"])
    primary = int(config["primary_budget"])
    margin = float(config.get("development_gate", {}).get("noninferiority_margin", 0.05))
    decision_metrics = {
        method: {
            "weighted_recall": partial_mean(rows, method, "weighted_corrupt_recall", primary),
            "recovery": partial_mean(rows, method, "robot_recovery_success", primary),
        } for method in ("sc_dcta", "ens", "hard_source_dcta", "prob_dcta", "random",
                         "oracle_source", "full_information_hindsight")
    }
    integrity = {
        "archive_count": len(archives) == archive_count, "zero_errors": not errors,
        "cascade_lengths_balanced": Counter(a["true_cascade_length"] for a in archives)
        == Counter({1: archive_count//3, 2: archive_count//3, 3: archive_count//3}),
        "views_complete": len(views) == archive_count*3,
        "structured_grid_complete": sum(row["method"] != "random" for row in rows)
        == expected_structured,
        "random_grid_complete": sum(row["method"] == "random" for row in rows)
        == expected_random,
        "budgets_exact": all(len(row["replayed_ids"]) == row["budget"] for row in rows),
        "labels_executable": all(
            {node for node, value in a["replay_map"].items() if not value["success"]}
            == set(a["affected_ids"]) for a in archives),
    }
    gate = {
        "sc_weighted_recall_noninferior_to_ens_partial_budget4":
            decision_metrics["sc_dcta"]["weighted_recall"]
            >= decision_metrics["ens"]["weighted_recall"]-margin,
        "sc_recovery_noninferior_to_ens_partial_budget4":
            decision_metrics["sc_dcta"]["recovery"] >= decision_metrics["ens"]["recovery"]-margin,
        "sc_weighted_recall_better_than_random_partial_budget4":
            decision_metrics["sc_dcta"]["weighted_recall"]
            > decision_metrics["random"]["weighted_recall"],
    }
    decision = "GO" if all(integrity.values()) and all(gate.values()) else "NO_GO"
    report = {
        "schema_version": "babyai-unlockpickup-method-v1", "protocol": config["protocol"],
        "phase": config["phase"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision, "method_frozen": True,
        "artifact_hashes": {"config": digest(args.config), "runner": digest(Path(__file__)),
                            "go_no_go_report": digest(go_path)},
        "counts": {"archives": len(archives), "views": len(views),
                   "environment_memory_outcomes": len(archives)*18,
                   "structured_runs": expected_structured, "random_runs": expected_random,
                   "total_method_runs": len(rows)},
        "integrity": integrity, "development_gate": gate,
        "decision_metrics_partial_budget4": decision_metrics,
        "regime_counts": dict(Counter(a["regime"] for a in archives)),
        "cascade_length_counts": dict(Counter(a["true_cascade_length"] for a in archives)),
        "sc_mode_counts": dict(Counter(row["sc_mode"] for row in rows
                                        if row["method"] == "sc_dcta")),
        "summary": {"by_condition_method_budget": aggregate(
            rows, ("condition", "method", "budget")),
            "by_length_condition_method_budget": aggregate(
                rows, ("true_cascade_length", "condition", "method", "budget"))},
        "archives": archives, "views": views, "errors": errors, "rows": rows,
        "elapsed_s": time.perf_counter()-started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"decision": decision, "counts": report["counts"],
                      "integrity": integrity, "development_gate": gate,
                      "decision_metrics_partial_budget4": decision_metrics,
                      "sc_mode_counts": report["sc_mode_counts"],
                      "elapsed_s": report["elapsed_s"]}, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
