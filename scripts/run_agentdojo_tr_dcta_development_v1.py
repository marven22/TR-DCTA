"""Run the frozen executable AgentDojo TR-DCTA development matrix."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import time
from typing import Any

import _bootstrap  # noqa: F401

from mcx.agentdojo_adapter import load_official_suites, replay_workflow, screen_suite_pairs
from mcx.agentdojo_method import (
    build_posterior, condition_trace, observed_edges, opaque_lineages,
    random_policy, regime_prior, select_archive_source_groups, stable_seed,
)
from mcx.confidence_aware_dcta import confidence_aware_decision
from mcx.prob_dcta_benchmark import LatentSourceWorld, run_latent_policy
from mcx.terminal_recovery_dcta import (
    run_terminal_recovery_dcta, terminal_quarantine_decision,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "agentdojo_tr_dcta_development_freeze_v1.json"
OUTPUT = ROOT / "reports" / "agentdojo_tr_dcta_development_v1.json"
STRUCTURED = (
    "sc_dcta", "prob_dcta", "hard_source_dcta", "ens", "source_ig",
    "source_then_dcta", "positive_only_dcta", "static_risk", "oracle_source",
    "full_information_hindsight",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def result_row(
    instance: dict[str, Any], condition: str, method: str, budget: int,
    replicate: int | None, replayed: tuple[str, ...], final: Any,
    weights: dict[str, float], capacity: int, clean_fallback_safe: bool,
    *, sc_mode: str | None = None,
    quarantine_override: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    affected = frozenset(instance["affected_ids"])
    decision = terminal_quarantine_decision(final, weights, capacity)
    quarantined = decision.quarantined_ids if quarantine_override is None else quarantine_override
    discoveries = set(replayed) & affected
    captured = set(quarantined) & affected
    total_harm = sum(weights[node] for node in affected)
    source_probabilities = final.source_probabilities()
    predicted = min(final.source_ids, key=lambda source: (-source_probabilities[source], source))
    return {
        "archive_id": instance["archive_id"],
        "instance_id": instance["instance_id"],
        "suite": instance["suite"],
        "confidence_regime": instance["confidence_regime"],
        "true_source": instance["true_source"],
        "true_cascade_length": instance["true_cascade_length"],
        "condition": condition,
        "method": method,
        "budget": budget,
        "replicate": replicate,
        "replayed_ids": list(replayed),
        "labels": [int(node in affected) for node in replayed],
        "corrupt_discoveries": len(discoveries),
        "weighted_discovery_recall": sum(weights[node] for node in discoveries) / total_harm,
        "predicted_source": predicted,
        "source_identification_accuracy": float(predicted == instance["true_source"]),
        "quarantined_ids": list(quarantined),
        "posterior_expected_recovery": decision.value.recovery_probability,
        "posterior_expected_captured_harm": decision.value.expected_captured_harm,
        "quarantine_recall": len(captured) / len(affected),
        "weighted_quarantine_recall": sum(weights[node] for node in captured) / total_harm,
        "clean_descendants_removed": len(set(quarantined) - affected),
        "corrupt_descendants_left": len(affected - set(quarantined)),
        "safe_recovery_success": float(affected.issubset(quarantined) and clean_fallback_safe),
        "sc_mode": sc_mode,
    }


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["condition"], row["method"], row["budget"])].append(row)
    metrics = (
        "corrupt_discoveries", "weighted_discovery_recall",
        "source_identification_accuracy", "quarantine_recall",
        "weighted_quarantine_recall", "clean_descendants_removed",
        "corrupt_descendants_left", "safe_recovery_success",
    )
    output = []
    for key, values in sorted(groups.items(), key=lambda pair: str(pair[0])):
        record = {"condition": key[0], "method": key[1], "budget": key[2], "runs": len(values)}
        for metric in metrics:
            record[f"mean_{metric}"] = statistics.fmean(float(row[metric]) for row in values)
        output.append(record)
    return output


def primary_mean(rows: list[dict[str, Any]], method: str, metric: str, budget: int) -> float:
    selected = [
        float(row[metric]) for row in rows
        if row["condition"] == "partial_67" and row["method"] == method
        and row["budget"] == budget
    ]
    return statistics.fmean(selected)


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
    for path_key, hash_key in (
        ("structural_report", "structural_report_sha256"),
        ("structural_verification", "structural_verification_sha256"),
    ):
        path = ROOT / config[path_key]
        if digest(path) != config[hash_key]:
            raise RuntimeError(f"frozen prerequisite changed: {path}")
        prerequisite = json.loads(path.read_text(encoding="utf-8"))
        passed = (
            prerequisite.get("decision") == "GO"
            if path_key == "structural_report"
            else prerequisite.get("verified") is True
        )
        if not passed:
            raise RuntimeError(f"frozen prerequisite did not pass: {path}")

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
            suite,
            minimum_clean_tool_calls=int(config["minimum_clean_tool_calls"]),
            score_clean_against_injection=True,
        )
        groups = select_archive_source_groups(
            qualifying, suite=suite_name, salt=config["selection_salt"],
            archive_count=int(config["archives_per_suite"]),
            sources_per_archive=int(config["sources_per_archive"]),
        )
        screening[suite_name] = {
            **counts,
            "qualifying_pair_digest": hashlib.sha256(
                json.dumps(sorted(qualifying), separators=(",", ":")).encode()
            ).hexdigest(),
        }
        for suite_rank, (user_task_id, injection_task_ids) in enumerate(groups):
            archive_id = f"agentdojo-dev-{suite_name}-{suite_rank:02d}"
            lineages, private_to_opaque, by_depth = opaque_lineages(archive_id, source_ids, variants)
            replay_map: dict[str, Any] = {}
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
                        "source_id": source,
                        "injection_task_id": injection_task_id,
                        "variant": variant,
                        "negative": clean.to_dict(),
                        "positive": positive.to_dict(),
                    }
            archives.append({
                "archive_id": archive_id,
                "suite": suite_name,
                "user_task_id": user_task_id,
                "source_injection_tasks": dict(zip(source_ids, injection_task_ids)),
                "lineages": {key: list(value) for key, value in lineages.items()},
                "by_depth": [list(layer) for layer in by_depth],
                "clean_fallback_safe": clean_fallback_safe,
                "replay_map": replay_map,
            })
        print(f"[AgentDojo] screened and built {suite_name}: {len(groups)} archives", flush=True)

    instances: list[dict[str, Any]] = []
    views: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    regimes = tuple(config["confidence_regimes"])
    for archive_index, archive in enumerate(archives):
        lineages = {key: tuple(value) for key, value in archive["lineages"].items()}
        by_depth = tuple(tuple(layer) for layer in archive["by_depth"])
        weights = {
            node: weights_by_depth[depth]
            for depth, layer in enumerate(by_depth) for node in layer
        }
        for source_index, true_source in enumerate(source_ids):
            length = 1 + (archive_index + source_index) % 3
            regime = regimes[(archive_index * len(source_ids) + source_index) % len(regimes)]
            decoy_source = source_ids[(source_index + 1) % len(source_ids)]
            source_prior = regime_prior(
                source_ids, true_source, decoy_source, config["source_priors"][regime],
            )
            affected = frozenset(lineages[true_source][:length])
            instance = {
                "instance_id": f"{archive['archive_id']}--truth-{source_index}",
                "archive_id": archive["archive_id"], "suite": archive["suite"],
                "true_source": true_source, "true_cascade_length": length,
                "confidence_regime": regime, "decoy_source": decoy_source,
                "source_prior": source_prior, "affected_ids": sorted(affected),
            }
            instances.append(instance)
            truth = LatentSourceWorld(true_source, affected, 1.0)
            for condition, specification in config["provenance_conditions"].items():
                edges = observed_edges(
                    archive["archive_id"], lineages,
                    int(specification["hidden_links_per_layer"]),
                )
                posterior, completions = build_posterior(
                    source_ids, by_depth, edges, source_prior, length_prior,
                )
                truth_support = sum(
                    world.weight for world in posterior.worlds
                    if world.source_id == true_source and world.affected_ids == affected
                )
                views.append({
                    "instance_id": instance["instance_id"], "condition": condition,
                    "observed_edges": [list(edge) for edge in edges],
                    "completion_count": completions, "posterior_worlds": len(posterior.worlds),
                    "truth_support": truth_support,
                })
                for budget in budgets:
                    tr = run_terminal_recovery_dcta(
                        posterior, truth, budget, weights=weights, quarantine_capacity=capacity,
                    )
                    rows.append(result_row(
                        instance, condition, "tr_dcta", budget, None, tr.replayed_ids,
                        tr.final_posterior, weights, capacity, archive["clean_fallback_safe"],
                    ))
                    for method in STRUCTURED:
                        sc_mode = None
                        override = None
                        if method == "sc_dcta":
                            sc = confidence_aware_decision(posterior, budget, weights)
                            sc_mode = sc.mode
                            policy = "top1_dcta" if sc.mode == "hard" else "prob_dcta"
                            outcome = run_latent_policy(
                                posterior, truth, budget, method=policy, weights=weights,
                            )
                        elif method == "hard_source_dcta":
                            outcome = run_latent_policy(
                                posterior, truth, budget, method="top1_dcta", weights=weights,
                            )
                        elif method == "positive_only_dcta":
                            outcome = run_latent_policy(
                                posterior, truth, budget, method="positive_only_risk", weights=weights,
                            )
                        elif method == "oracle_source":
                            outcome = run_latent_policy(
                                posterior.restrict_source(true_source), truth, budget,
                                method="prob_dcta", weights=weights,
                            )
                        elif method == "full_information_hindsight":
                            outcome = run_latent_policy(
                                posterior, truth, budget, method="prob_dcta", weights=weights,
                            )
                            clean_fill = [node for node in sorted(posterior.candidates) if node not in affected]
                            override = tuple(sorted(affected)) + tuple(clean_fill[:capacity - len(affected)])
                        else:
                            policy = {
                                "positive_only_dcta": "positive_only_risk",
                            }.get(method, method)
                            outcome = run_latent_policy(
                                posterior, truth, budget, method=policy, weights=weights,
                            )
                        rows.append(result_row(
                            instance, condition, method, budget, None,
                            outcome.replayed_ids, outcome.final_posterior, weights, capacity,
                            archive["clean_fallback_safe"], sc_mode=sc_mode,
                            quarantine_override=override,
                        ))
                    for replicate in range(int(config["random_replicates"])):
                        replayed, final = random_policy(
                            posterior, affected, budget,
                            stable_seed(config["random_seed"], instance["instance_id"], condition, budget, replicate),
                        )
                        rows.append(result_row(
                            instance, condition, "random", budget, replicate, replayed, final,
                            weights, capacity, archive["clean_fallback_safe"],
                        ))
        print(f"[AgentDojo] evaluated {archive_index + 1}/{len(archives)} archives", flush=True)

    primary = int(config["primary_budget"])
    gate_methods = ("tr_dcta", "sc_dcta", "ens", "random")
    primary_metrics = {
        method: {
            "recovery": primary_mean(rows, method, "safe_recovery_success", primary),
            "weighted_quarantine_recall": primary_mean(
                rows, method, "weighted_quarantine_recall", primary,
            ),
            "weighted_discovery_recall": primary_mean(
                rows, method, "weighted_discovery_recall", primary,
            ),
        }
        for method in gate_methods
    }
    margin = float(config["noninferiority_margin"])
    gates = {
        "tr_recovery_at_least_sc": primary_metrics["tr_dcta"]["recovery"] >= primary_metrics["sc_dcta"]["recovery"],
        "tr_recovery_noninferior_to_ens": primary_metrics["tr_dcta"]["recovery"] >= primary_metrics["ens"]["recovery"] - margin,
        "tr_weighted_quarantine_noninferior_to_ens": primary_metrics["tr_dcta"]["weighted_quarantine_recall"] >= primary_metrics["ens"]["weighted_quarantine_recall"] - margin,
        "tr_recovery_better_than_random": primary_metrics["tr_dcta"]["recovery"] > primary_metrics["random"]["recovery"],
    }
    executable_integrity = all(
        record[polarity]["error"] is None
        and (record[polarity]["attack_success"] if polarity == "positive" else record[polarity]["safe_success"])
        and (not record[polarity]["safe_success"] if polarity == "positive" else not record[polarity]["attack_success"])
        for archive in archives for record in archive["replay_map"].values()
        for polarity in ("negative", "positive")
    )
    scenario_count = len(instances) * len(config["provenance_conditions"]) * len(budgets)
    integrity = {
        "archive_count_exact": len(archives) == 16,
        "suite_balance_exact": all(sum(a["suite"] == suite for a in archives) == 4 for suite in config["suites"]),
        "instance_count_exact": len(instances) == 48,
        "regime_balance_exact": all(sum(i["confidence_regime"] == regime for i in instances) == 12 for regime in regimes),
        "length_balance_exact": all(sum(i["true_cascade_length"] == length for i in instances) == 16 for length in (1, 2, 3)),
        "executable_binary_labels_valid": executable_integrity,
        "truth_has_positive_posterior_support": all(view["truth_support"] > 0.0 for view in views),
        "tr_grid_complete": sum(row["method"] == "tr_dcta" for row in rows) == scenario_count,
        "structured_grid_complete": sum(row["method"] in STRUCTURED for row in rows) == scenario_count * len(STRUCTURED),
        "random_grid_complete": sum(row["method"] == "random" for row in rows) == scenario_count * int(config["random_replicates"]),
        "replay_budget_exact": all(len(row["replayed_ids"]) == row["budget"] for row in rows),
    }
    decision = "GO" if all(integrity.values()) and all(gates.values()) else "NO_GO"
    report = {
        "schema_version": "agentdojo-tr-dcta-development-v1",
        "protocol": config["protocol"], "phase": config["phase"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "decision": decision,
        "development_data_not_held_out": True,
        "artifact_hashes": {
            "config": digest(args.config), "runner": digest(Path(__file__)),
            "agentdojo_adapter": digest(ROOT / "src" / "mcx" / "agentdojo_adapter.py"),
            "agentdojo_method": digest(ROOT / "src" / "mcx" / "agentdojo_method.py"),
            "tr_dcta": digest(ROOT / "src" / "mcx" / "terminal_recovery_dcta.py"),
        },
        "counts": {
            "suites": len(config["suites"]), "archives": len(archives),
            "truth_instances": len(instances), "posterior_views": len(views),
            "method_runs": len(rows),
        },
        "screening": screening, "integrity": integrity,
        "development_gate": gates, "primary_partial_67_budget4": primary_metrics,
        "summary": aggregate(rows), "archives": archives, "instances": instances,
        "views": views, "rows": rows, "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": decision, "counts": report["counts"], "integrity": integrity,
        "development_gate": gates, "primary_partial_67_budget4": primary_metrics,
        "elapsed_s": report["elapsed_s"],
    }, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
