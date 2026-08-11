"""Run the frozen 240-context confirmatory UnlockPickup TR-DCTA evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.confidence_aware_dcta import confidence_aware_decision
from mcx.prob_dcta_benchmark import LatentSourceWorld, run_latent_policy
from mcx.terminal_recovery_dcta import run_terminal_recovery_dcta
from run_babyai_minigrid_partial_provenance_v1 import (
    observed_edges, opaque_lineages, random_policy, stable_seed,
)
from run_babyai_unlockpickup_go_no_go_v1 import execute
from run_babyai_unlockpickup_method_v1 import (
    build_stochastic_posterior, condition_trace, source_prior,
)
from run_babyai_unlockpickup_terminal_recovery_development_v1 import aggregate, row


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "BABYAI_UNLOCKPICKUP_TERMINAL_RECOVERY_HELDOUT_PROTOCOL_V1.md"
BASELINES = ("sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "source_ig",
             "source_then_dcta", "positive_only_dcta", "static_risk", "oracle_source")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_and_evaluate(payload: tuple[int, dict]) -> dict[str, Any]:
    seed, config = payload
    colors = tuple(config["colors"])
    variants = tuple(config["variants"])
    stage_weights = tuple(map(float, config["stage_harm_weights"]))
    length_prior = tuple(map(float, config["cascade_length_prior"]))
    budgets = tuple(map(int, config["budgets"]))
    capacity = int(config["quarantine_capacity"])
    probe = execute(config["env_id"], seed, colors[0], variants[0])
    target = probe["target_color"]
    eligible = tuple(color for color in colors if color != target)
    true_source = eligible[(seed * 7 + 1) % len(eligible)]
    decoy = eligible[(eligible.index(true_source) + 1) % len(eligible)]
    regime = config["confidence_regimes"][seed % len(config["confidence_regimes"])]
    true_length = 1 + seed % 3
    phase = "heldout" if seed >= int(config["seed_start"]) else "development_smoke"
    archive_id = f"babyai-unlockpickup-{phase}-{seed:04d}"
    archive = {
        "archive_id": archive_id, "seed": seed, "mission": probe["mission"],
        "target_color": target, "regime": regime, "true_source": true_source,
        "decoy_source": decoy, "true_cascade_length": true_length,
        "source_prior": source_prior(config, regime, true_source, decoy),
        "lineages": {color: [f"{color}::{variant}" for variant in variants]
                     for color in colors}, "replay_map": {},
    }
    lineages, private_to_opaque, by_depth = opaque_lineages(archive, variants)
    affected_private = {f"{true_source}::{variants[depth]}" for depth in range(true_length)}
    affected = frozenset(private_to_opaque[node] for node in affected_private)
    weights = {private_to_opaque[f"{color}::{variant}"]: stage_weights[depth]
               for color in colors for depth, variant in enumerate(variants)}
    for color in colors:
        for depth, variant in enumerate(variants):
            private = f"{color}::{variant}"
            active = private in affected_private
            behavior_source = true_source if active else target
            outcome = execute(config["env_id"], seed, behavior_source, variant)
            archive["replay_map"][private_to_opaque[private]] = {
                "private_family": color, "variant": variant,
                "active_corruption": active, "behavior_source": behavior_source,
                "success": outcome["success"], "steps": outcome["steps"],
                "milestones": outcome["milestones"],
            }
    executable_affected = {node for node, value in archive["replay_map"].items()
                           if not value["success"]}
    if executable_affected != set(affected):
        raise RuntimeError(f"executable label mismatch: {archive_id}")
    archive["affected_ids"] = sorted(affected)
    truth = LatentSourceWorld(true_source, affected, 1.0)
    rows = []
    views = []
    for condition, specification in config["provenance_conditions"].items():
        observed = observed_edges(
            archive_id, lineages, int(specification["hidden_links_per_layer"]))
        posterior, completions = build_stochastic_posterior(
            colors, by_depth, observed, archive["source_prior"], length_prior)
        views.append({"archive_id": archive_id, "condition": condition,
                      "observed_edges": [list(edge) for edge in observed],
                      "completion_count": completions,
                      "posterior_worlds": len(posterior.worlds)})
        for budget in budgets:
            tr = run_terminal_recovery_dcta(
                posterior, truth, budget, weights=weights, quarantine_capacity=capacity)
            rows.append(row(archive, condition, "tr_dcta", budget, None,
                            tr.replayed_ids, tr.final_posterior, affected, weights,
                            capacity, None))
            for method in BASELINES:
                sc_mode = None
                if method == "sc_dcta":
                    decision = confidence_aware_decision(posterior, budget, weights)
                    sc_mode = decision.mode
                    policy = "top1_dcta" if decision.mode == "hard" else "prob_dcta"
                    outcome = run_latent_policy(
                        posterior, truth, budget, method=policy, weights=weights)
                elif method == "hard_source_dcta":
                    outcome = run_latent_policy(
                        posterior, truth, budget, method="top1_dcta", weights=weights)
                elif method == "positive_only_dcta":
                    outcome = run_latent_policy(
                        posterior, truth, budget, method="positive_only_risk", weights=weights)
                elif method == "oracle_source":
                    outcome = run_latent_policy(
                        posterior.restrict_source(true_source), truth, budget,
                        method="prob_dcta", weights=weights)
                else:
                    policy = "source_then_dcta" if method == "source_then_dcta" else method
                    outcome = run_latent_policy(
                        posterior, truth, budget, method=policy, weights=weights)
                rows.append(row(archive, condition, method, budget, None,
                                outcome.replayed_ids, outcome.final_posterior, affected,
                                weights, capacity, sc_mode))
            ordered = tuple(sorted(affected)) + tuple(
                node for node in sorted(posterior.candidates) if node not in affected)
            hindsight_replayed = ordered[:budget]
            hindsight_final = condition_trace(posterior, hindsight_replayed, affected)
            hindsight_quarantine = tuple(sorted(affected)) + tuple(
                node for node in sorted(posterior.candidates) if node not in affected
            )[:capacity-len(affected)]
            rows.append(row(
                archive, condition, "full_information_hindsight", budget, None,
                hindsight_replayed, hindsight_final, affected, weights, capacity, None,
                hindsight_quarantine))
            for replicate in range(int(config["random_replicates"])):
                replayed, final = random_policy(
                    posterior, affected, budget,
                    stable_seed(config["random_seed"], archive_id, condition, budget, replicate))
                rows.append(row(archive, condition, "random", budget, replicate,
                                replayed, final, affected, weights, capacity, None))
    labels_exact = all(value["labels"] == [int(node in affected)
                                           for node in value["replayed_ids"]] for value in rows)
    accounting_exact = all(
        bool(value["robot_recovery_success"])
        == affected.issubset(set(value["quarantined_ids"]))
        and int(value["corrupt_descendants_left"])
        == len(affected - set(value["quarantined_ids"])) for value in rows)
    return {"archive": archive, "views": views, "rows": rows,
            "labels_exact": labels_exact, "accounting_exact": accounting_exact}


def cluster_values(rows: list[dict], metric: str, condition: str | None = None) -> dict[str, dict[str, float]]:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for value in rows:
        if value["budget"] != 4 or value["condition"] == "complete":
            continue
        if condition is not None and value["condition"] != condition:
            continue
        groups[(value["archive_id"], value["method"])].append(float(value[metric]))
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for (archive, method), values in groups.items():
        output[archive][method] = statistics.fmean(values)
    return dict(output)


def paired_bootstrap(values: dict[str, dict[str, float]], right: str,
                     draws: int, seed: int) -> dict[str, Any]:
    ids = sorted(values)
    differences = [values[key]["tr_dcta"] - values[key][right] for key in ids]
    rng = random.Random(seed)
    samples = sorted(sum(differences[rng.randrange(len(ids))] for _ in ids) / len(ids)
                     for _ in range(draws))
    lower, upper = samples[int(.025*draws)], samples[min(int(.975*draws), draws-1)]
    return {"left": "tr_dcta", "right": right, "paired_archives": len(ids),
            "estimate": statistics.fmean(differences), "lower_95": lower,
            "upper_95": upper, "superiority_supported": lower > 0.0,
            "wins": sum(x > 0 for x in differences),
            "ties": sum(x == 0 for x in differences),
            "losses": sum(x < 0 for x in differences)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--development-smoke", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    frozen_paths = {
        "method": ROOT / "src" / "mcx" / "terminal_recovery_dcta.py",
        "development_report": ROOT / config["development_report"],
        "opendoor_transfer_report": ROOT / config["opendoor_transfer_report"],
        "go_no_go_report": ROOT / config["go_no_go_report"],
    }
    expected_hashes = {
        "method": config["terminal_recovery_method_sha256"],
        "development_report": config["development_report_sha256"],
        "opendoor_transfer_report": config["opendoor_transfer_report_sha256"],
        "go_no_go_report": config["go_no_go_report_sha256"],
    }
    for name, path in frozen_paths.items():
        if digest(path) != expected_hashes[name]:
            raise ValueError(f"frozen artifact changed: {name}")
    if args.development_smoke:
        start, stop = (int(config["development_smoke_start"]),
                       int(config["development_smoke_stop_exclusive"]))
    else:
        start, stop = int(config["seed_start"]), int(config["seed_stop_exclusive"])
    seeds = list(range(start, stop))
    started = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        for index, result in enumerate(
                executor.map(build_and_evaluate, [(seed, config) for seed in seeds]), start=1):
            results.append(result)
            if index % 20 == 0 or index == len(seeds):
                print(f"[unlockpickup archives] {index}/{len(seeds)}", flush=True)
    archives = [result["archive"] for result in results]
    views = [view for result in results for view in result["views"]]
    rows = [value for result in results for value in result["rows"]]
    comparisons = []
    if not args.development_smoke:
        labels = [("pooled_partial", None), ("partial_33", "partial_33"),
                  ("partial_67", "partial_67")]
        for stratum_index, (stratum, condition) in enumerate(labels):
            for metric_index, metric in enumerate(config["primary_estimands"]):
                values = cluster_values(rows, metric, condition)
                for comparator_index, right in enumerate(config["primary_comparators"]):
                    comparisons.append({"stratum": stratum, "metric": metric, "budget": 4,
                                        **paired_bootstrap(
                                            values, right, int(config["bootstrap_draws"]),
                                            int(config["bootstrap_seed"]) + 100*stratum_index
                                            + 10*metric_index + comparator_index)})
    archive_count = len(seeds)
    grid = archive_count * 3 * 3
    structured = len([method for method in config["methods"] if method != "random"])
    integrity = {
        "archive_count_exact": len(archives) == archive_count,
        "seed_set_exact": {a["seed"] for a in archives} == set(seeds),
        "cascade_lengths_balanced": Counter(a["true_cascade_length"] for a in archives)
        == Counter({length: archive_count // 3 for length in (1, 2, 3)})
        if archive_count % 3 == 0 else True,
        "regimes_balanced": Counter(a["regime"] for a in archives)
        == Counter({regime: archive_count // 4 for regime in config["confidence_regimes"]})
        if archive_count % 4 == 0 else True,
        "environment_labels_exact": all(
            {node for node, value in a["replay_map"].items() if not value["success"]}
            == set(a["affected_ids"]) for a in archives),
        "views_complete": len(views) == archive_count * 3,
        "structured_grid_complete": sum(value["method"] != "random" for value in rows)
        == grid * structured,
        "random_grid_complete": sum(value["method"] == "random" for value in rows)
        == grid * int(config["random_replicates"]),
        "budgets_exact": all(len(value["replayed_ids"]) == value["budget"] for value in rows),
        "labels_exact": all(result["labels_exact"] for result in results),
        "outcome_accounting_exact": all(result["accounting_exact"] for result in results),
        "bootstrap_complete": len(comparisons) == (0 if args.development_smoke else 30),
    }
    report = {
        "schema_version": "babyai-unlockpickup-terminal-recovery-heldout-v1",
        "protocol": config["protocol"], "phase": ("development_smoke"
                                                      if args.development_smoke else config["phase"]),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_status": "SMOKE" if args.development_smoke else "COMPLETE",
        "method_frozen": True,
        "artifact_hashes": {"config": digest(args.config), "protocol": digest(PROTOCOL),
                            "runner": digest(Path(__file__)),
                            **{name: digest(path) for name, path in frozen_paths.items()}},
        "counts": {"archives": archive_count, "environment_memory_outcomes": archive_count*18,
                   "provenance_views": len(views), "method_runs": len(rows)},
        "integrity": integrity, "summary": aggregate(rows),
        "paired_bootstrap": comparisons, "archives": archives, "views": views,
        "rows": rows, "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    primary = [item for item in report["summary"] if item["condition"] != "complete"
               and item["budget"] == 4 and item["method"] in
               {"tr_dcta", "sc_dcta", "ens", "random", "full_information_hindsight"}]
    print(json.dumps({"status": report["evaluation_status"], "counts": report["counts"],
                      "integrity": integrity, "primary": primary,
                      "elapsed_s": report["elapsed_s"]}, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
