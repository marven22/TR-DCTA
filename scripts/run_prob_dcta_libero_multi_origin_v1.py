"""Frozen evaluator for the full Memory-LIBERO multi-origin study."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

import _bootstrap

from mcx.causal_regime_benchmark import exact_weighted_policy_value
from mcx.directional_transition import LocalTransitionParameters
from mcx.prob_dcta_benchmark import LatentSourceWorld, run_latent_policy, source_brier
from mcx.prob_dcta_libero import (
    PROTOCOL, build_joint_posterior, canonical_hash, truth_in_support,
)


METHODS = (
    "random", "static_risk", "positive_only_risk", "top1_dcta", "source_ig",
    "source_then_dcta", "ens", "prob_dcta", "known_source_dcta",
)
PRIMARY_CONDITIONS = {"high", "medium", "uniform"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dcta(path: Path) -> LocalTransitionParameters:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("protocol") != "dcta-risk-local-v1/final-transition-freeze":
        raise ValueError("frozen DCTA-Risk-Local v1 parameters required")
    return LocalTransitionParameters(**value["parameters"])


def _condition_trace(posterior, replayed, affected):
    current = posterior
    for node in replayed:
        conditioned = current.condition(node, int(node in affected))
        if conditioned is not None:
            current = conditioned
    return current


def _random_path(archive_id, candidates, budget):
    return tuple(sorted(
        candidates,
        key=lambda node: hashlib.sha256(
            f"{PROTOCOL}|random|{archive_id}|{node}".encode()
        ).hexdigest(),
    )[:budget])


def _metrics(public, private, posterior, replayed, final_posterior):
    affected = frozenset(str(node) for node in private["affected_ids"])
    hits = set(replayed) & affected
    candidates = tuple(str(node) for node in public["candidate_ids"])
    depth_weight = {node: float(index % 3 + 1) for index, node in enumerate(candidates)}
    total_weight = sum(depth_weight[node] for node in affected)
    hit_weight = sum(depth_weight[node] for node in hits)
    probabilities = final_posterior.source_probabilities()
    predicted = min(final_posterior.source_ids,
                    key=lambda source: (-probabilities[source], source))
    return {
        "replayed_ids": list(replayed),
        "discoveries": len(hits),
        "recall": len(hits) / len(affected) if affected else 1.0,
        "audit_yield": len(hits) / len(replayed) if replayed else 0.0,
        "depth_weighted_recall": hit_weight / total_weight if total_weight else 1.0,
        "source_top1_correct": int(predicted == private["active_source_id"]),
        "source_brier": source_brier(final_posterior, str(private["active_source_id"])),
        "source_entropy": final_posterior.source_entropy(),
    }


def _cluster_bootstrap(rows, left, right, draws, seed):
    by_cluster = {}
    for row in rows:
        by_cluster.setdefault(row["base_archive_key"], {}).setdefault(
            row["method"], []
        ).append(row["recall"])
    clusters = sorted(
        cluster for cluster, values in by_cluster.items() if left in values and right in values
    )
    differences = [
        statistics.fmean(by_cluster[cluster][left])
        - statistics.fmean(by_cluster[cluster][right])
        for cluster in clusters
    ]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(
        differences[rng.randrange(len(differences))] for _ in differences
    ) for _ in range(draws))
    return {
        "estimate": statistics.fmean(differences),
        "lower_95": samples[int(.025 * draws)],
        "upper_95": samples[int(.975 * draws)],
        "cluster_count": len(clusters),
        "wins": sum(value > 0 for value in differences),
        "ties": sum(value == 0 for value in differences),
        "losses": sum(value < 0 for value in differences),
    }


def _summarize(rows, budgets):
    output = {}
    for split in ("development", "validation", "test"):
        output[split] = {}
        for condition in ("known", "high", "medium", "uniform", "wrong60"):
            output[split][condition] = {}
            for budget in budgets:
                selected = [row for row in rows if row["split"] == split
                            and row["condition"] == condition and row["budget"] == budget]
                output[split][condition][str(budget)] = {
                    method: {
                        "macro_recall_positive": statistics.fmean(
                            row["recall"] for row in selected
                            if row["method"] == method and row["affected_count"] > 0
                        ) if any(row["method"] == method and row["affected_count"] > 0
                                 for row in selected) else None,
                        "mean_discoveries": statistics.fmean(
                            row["discoveries"] for row in selected if row["method"] == method
                        ),
                        "mean_source_brier": statistics.fmean(
                            row["source_brier"] for row in selected if row["method"] == method
                        ),
                    }
                    for method in METHODS
                }
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dcta-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if public.get("protocol") != f"{PROTOCOL}/public" or private.get("protocol") != f"{PROTOCOL}/private":
        raise ValueError("multi-origin v1 ledgers required")
    if config.get("protocol") != f"{PROTOCOL}/freeze":
        raise ValueError("frozen multi-origin configuration required")
    if private.get("public_payload_sha256") != canonical_hash(public):
        raise ValueError("public/private multi-origin ledgers do not match")
    evaluator_hash = sha256(Path(__file__))
    if public.get("evaluator_sha256_before_label_join") != evaluator_hash:
        raise ValueError("evaluator changed after label construction")
    implementation_paths = {
        "prob_dcta_benchmark": Path("src/mcx/prob_dcta_benchmark.py"),
        "prob_dcta_libero": Path("src/mcx/prob_dcta_libero.py"),
        "active_search_baselines": Path("src/mcx/active_search_baselines.py"),
        "directional_transition": Path("src/mcx/directional_transition.py"),
    }
    implementation_hashes = {key: sha256(path) for key, path in implementation_paths.items()}
    if public.get("implementation_sha256_before_label_join") != implementation_hashes:
        raise ValueError("method implementation changed after label construction")
    labels = {row["archive_id"]: row for row in private["archives"]}
    parameters = load_dcta(args.dcta_config)
    budgets = tuple(int(value) for value in config["budgets"])
    unit_weights = {}
    rows, diagnostics = [], []
    started_all = time.perf_counter()
    for index, public_row in enumerate(public["archives"], start=1):
        private_row = labels[public_row["archive_id"]]
        posterior = build_joint_posterior(public_row, parameters)
        affected = frozenset(str(node) for node in private_row["affected_ids"])
        active = str(private_row["active_source_id"])
        if not truth_in_support(posterior, active, affected):
            raise ValueError(f"private truth outside posterior support: {public_row['archive_id']}")
        truth = LatentSourceWorld(active, affected, 1.0)
        weights = {node: 1.0 for node in posterior.candidates}
        initial_brier = source_brier(posterior, active)
        model_oracles = {}
        for budget in budgets:
            model_oracles[str(budget)] = exact_weighted_policy_value(posterior, budget, weights)
            for method in METHODS:
                if method == "random":
                    replayed = _random_path(str(public_row["archive_id"]), posterior.candidates, budget)
                    final = _condition_trace(posterior, replayed, affected)
                else:
                    belief = posterior.restrict_source(active) if method == "known_source_dcta" else posterior
                    policy_method = "prob_dcta" if method == "known_source_dcta" else method
                    outcome = run_latent_policy(
                        belief, truth, budget, method=policy_method, weights=weights
                    )
                    replayed, final = outcome.replayed_ids, outcome.final_posterior
                rows.append({
                    "archive_id": public_row["archive_id"],
                    "base_archive_key": public_row["base_archive_key"],
                    "split": public_row["split"],
                    "condition": public_row["condition"],
                    "budget": budget,
                    "method": method,
                    "affected_count": len(affected),
                    "initial_source_brier": initial_brier,
                    **_metrics(public_row, private_row, posterior, replayed, final),
                })
        diagnostics.append({
            "archive_id": public_row["archive_id"],
            "base_archive_key": public_row["base_archive_key"],
            "split": public_row["split"],
            "condition": public_row["condition"],
            "affected_count": len(affected),
            "posterior_world_count": len(posterior.worlds),
            "truth_support": True,
            "signal_correct": private_row["signal_correct"],
            "initial_source_brier": initial_brier,
            "model_oracle": model_oracles,
        })
        if index % 100 == 0 or index == len(public["archives"]):
            print(f"evaluated {index}/{len(public['archives'])}", flush=True)
    summary = _summarize(rows, budgets)
    primary = [row for row in rows if row["split"] == "test"
               and row["condition"] in PRIMARY_CONDITIONS
               and row["budget"] == config["primary_budget"]
               and row["affected_count"] > 0]
    primary_summary = {
        method: {
            "macro_recall": statistics.fmean(
                row["recall"] for row in primary if row["method"] == method
            ),
            "mean_discoveries": statistics.fmean(
                row["discoveries"] for row in primary if row["method"] == method
            ),
            "mean_audit_yield": statistics.fmean(
                row["audit_yield"] for row in primary if row["method"] == method
            ),
            "mean_source_brier": statistics.fmean(
                row["source_brier"] for row in primary if row["method"] == method
            ),
        }
        for method in METHODS
    }
    comparisons = {
        "prob_minus_top1": _cluster_bootstrap(
            primary, "prob_dcta", "top1_dcta", config["bootstrap_draws"],
            config["bootstrap_seed"],
        ),
        "prob_minus_positive_only": _cluster_bootstrap(
            primary, "prob_dcta", "positive_only_risk", config["bootstrap_draws"],
            config["bootstrap_seed"] + 1,
        ),
        "prob_minus_ens": _cluster_bootstrap(
            primary, "prob_dcta", "ens", config["bootstrap_draws"],
            config["bootstrap_seed"] + 2,
        ),
        "hybrid_minus_prob": _cluster_bootstrap(
            primary, "source_then_dcta", "prob_dcta", config["bootstrap_draws"],
            config["bootstrap_seed"] + 3,
        ),
    }
    prob = primary_summary["prob_dcta"]["macro_recall"]
    top1 = primary_summary["top1_dcta"]["macro_recall"]
    positive = primary_summary["positive_only_risk"]["macro_recall"]
    ens = primary_summary["ens"]["macro_recall"]
    known = primary_summary["known_source_dcta"]["macro_recall"]
    hybrid = primary_summary["source_then_dcta"]["macro_recall"]
    initial_brier = statistics.fmean(
        row["initial_source_brier"] for row in primary if row["method"] == "prob_dcta"
    )
    final_brier = primary_summary["prob_dcta"]["mean_source_brier"]
    positive_clusters = len({row["base_archive_key"] for row in primary})
    positive_rows = len([row for row in primary if row["method"] == "prob_dcta"])
    checks = {
        "prob_beats_top1_with_ci_excluding_zero": (
            prob > top1 and comparisons["prob_minus_top1"]["lower_95"] > 0.0
        ),
        "prob_beats_positive_only": prob > positive,
        "prob_within_003_of_ens": prob >= ens - .03,
        "joint_retains_90_percent_known_source": max(prob, hybrid) >= .90 * known,
        "prob_improves_source_brier": final_brier < initial_brier,
        "sample_gate": (
            len({row["base_archive_key"] for row in rows if row["split"] == "test"}) == 47
            and positive_clusters >= 10 and positive_rows >= 30
        ),
    }
    signal_accuracy = {}
    for condition in ("known", "high", "medium", "wrong60"):
        selected = [row for row in diagnostics if row["condition"] == condition]
        signal_accuracy[condition] = statistics.fmean(
            float(row["signal_correct"]) for row in selected
        )
    payload = {
        "protocol": f"{PROTOCOL}/evaluation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True,
        "derived_composite_study": True,
        "evaluator_sha256": evaluator_hash,
        "implementation_sha256": implementation_hashes,
        "public_sha256": sha256(args.public),
        "private_sha256": sha256(args.private),
        "config_sha256": sha256(args.config),
        "dcta_config_sha256": sha256(args.dcta_config),
        "base_archive_count": public["base_archive_count"],
        "composite_archive_count": public["archive_count"],
        "budgets": list(budgets),
        "primary_budget": config["primary_budget"],
        "primary_positive_row_count": positive_rows,
        "primary_positive_cluster_count": positive_clusters,
        "realized_signal_accuracy": signal_accuracy,
        "primary_summary": primary_summary,
        "comparisons": comparisons,
        "initial_prob_source_brier": initial_brier,
        "final_prob_source_brier": final_brier,
        "success_gate": {"passed": all(checks.values()), "checks": checks},
        "elapsed_seconds": time.perf_counter() - started_all,
        "summary": summary,
        "rows": rows,
        "diagnostics": diagnostics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in {"summary", "rows", "diagnostics"}}, indent=2))


if __name__ == "__main__":
    main()
