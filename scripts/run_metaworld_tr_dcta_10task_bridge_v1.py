"""Run the locked 10-task Meta-World TR-DCTA behavioral-recovery bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.memaudit_libero import memory_text
from mcx.metaworld_recovery import first_survivor, forced_exposure_ranking, selected_success
from mcx.metaworld_terminal_recovery_dcta import run_metaworld_terminal_recovery_dcta
from mcx.prob_dcta_benchmark import LatentSourceWorld
from mcx.publication_v2_posterior import (
    fit_cascade_parameters, sample_importance_posterior, stable_seed, support_proposal,
)
from mcx.publication_v2_source import fit_source_estimator, source_features
from run_sc_dcta_metaworld_development import harm_weights


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "METAWORLD_TR_DCTA_10TASK_BRIDGE_PROTOCOL_V1.md"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_archive(payload: tuple[Any, dict, dict, dict, dict, dict]) -> dict[str, Any]:
    posterior, public, truth, observable, recovery_truth, rankings = payload
    affected = frozenset(map(str, truth["affected_ids"]))
    source = str(truth["active_source_id"])
    weights = harm_weights(public)
    candidates = tuple(map(str, public["candidate_ids"]))
    corrupt_policy = {str(k): str(v) for k, v in recovery_truth["corrupted_policy_by_memory"].items()}
    clean_policy = {str(k): str(v) for k, v in recovery_truth["clean_policy_by_memory"].items()}
    success = {str(k): bool(v) for k, v in recovery_truth["success_by_policy"].items()}

    from functools import lru_cache

    @lru_cache(maxsize=None)
    def utility(world_affected: frozenset[str], removed: frozenset[str]) -> tuple[float, float]:
        if not world_affected:
            return 1.0, 1.0
        outcomes = []
        for anchor in world_affected:
            selected = first_survivor(rankings[anchor], removed)
            policy = corrupt_policy[selected] if selected in world_affected else clean_policy[selected]
            outcomes.append(float(success[policy]))
        return statistics.fmean(outcomes), len(world_affected & removed) / len(world_affected)

    actual = LatentSourceWorld(source, affected, 1.0)
    outcome = run_metaworld_terminal_recovery_dcta(
        posterior, actual, 4, weights=weights, utility=utility)
    actual_recovery, actual_anchor_rate = utility(affected, frozenset(outcome.quarantined_ids))
    episode_rows = []
    for anchor in sorted(affected):
        selected = first_survivor(rankings[anchor], outcome.quarantined_ids)
        post_success = selected_success(selected, corrupt_policy, success)
        episode_rows.append({
            "archive_id": public["archive_id"], "task_key": public["task_key"],
            "anchor_id": anchor, "method": "tr_dcta", "anchor_quarantined":
            anchor in set(outcome.quarantined_ids), "post_selected_id": selected,
            "post_success": post_success,
            "fallback_still_harmful": anchor in set(outcome.quarantined_ids) and not post_success,
        })
    hits = set(outcome.replayed_ids) & affected
    weighted_total = sum(weights[node] for node in affected)
    return {
        "archive_id": public["archive_id"], "task_key": public["task_key"],
        "rotation": public["rotation"], "replayed_ids": list(outcome.replayed_ids),
        "labels": [int(node in affected) for node in outcome.replayed_ids],
        "quarantined_ids": list(outcome.quarantined_ids),
        "discoveries": len(hits),
        "weighted_discovery_recall": sum(weights[node] for node in hits) / weighted_total,
        "behavioral_recovery": actual_recovery, "anchor_quarantine_rate": actual_anchor_rate,
        "root_rollout_recovery": outcome.root_rollout_value.recovery,
        "root_base_recovery": outcome.root_base_value.recovery,
        "root_rollout_anchor_quarantine": outcome.root_rollout_value.anchor_quarantine,
        "root_base_anchor_quarantine": outcome.root_base_value.anchor_quarantine,
        "episode_rows": episode_rows,
    }


def task_bootstrap(rows: list[dict], left: str, right: str,
                   draws: int, seed: int, metric: str) -> dict[str, Any]:
    by_task: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_task[row["task_key"]][row["method"]].append(float(row[metric]))
    tasks = sorted(task for task, values in by_task.items() if left in values and right in values)
    differences = [statistics.fmean(by_task[t][left]) - statistics.fmean(by_task[t][right])
                   for t in tasks]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(differences[rng.randrange(len(tasks))]
                                      for _ in tasks) for _ in range(draws))
    return {"left": left, "right": right, "metric": metric, "task_count": len(tasks),
            "estimate": statistics.fmean(differences),
            "lower_95": samples[int(.025*draws)],
            "upper_95": samples[min(int(.975*draws), draws-1)],
            "wins": sum(x > 0 for x in differences), "ties": sum(x == 0 for x in differences),
            "losses": sum(x < 0 for x in differences)}


def main() -> int:
    total_started = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    paths = {name: ROOT / path for name, path in config["paths"].items()}
    for name, path in paths.items():
        if digest(path) != config["hashes"][name]:
            raise ValueError(f"frozen input changed: {name}")
    adapter = ROOT / "src" / "mcx" / "metaworld_terminal_recovery_dcta.py"
    if digest(adapter) != config["hashes"]["adapter"]:
        raise ValueError("frozen Meta-World TR-DCTA adapter changed")
    public = json.loads(paths["public"].read_text(encoding="utf-8"))
    private = json.loads(paths["private"].read_text(encoding="utf-8"))
    observable = json.loads(paths["observable"].read_text(encoding="utf-8"))
    recovery_private = json.loads(paths["recovery_private"].read_text(encoding="utf-8"))
    forced = json.loads(paths["forced_evaluation"].read_text(encoding="utf-8"))
    public_by_id = {a["archive_id"]: a for a in public["archives"]}
    private_by_id = {a["archive_id"]: a for a in private["archives"]}
    observable_by_id = {a["archive_id"]: a for a in observable["archives"]}
    recovery_by_id = {a["archive_id"]: a for a in recovery_private["archives"]}
    selected = [a for a in public["archives"]
                if float(a["provenance_missing_rate"]) == float(config["provenance_missing_rate"])]
    selected.sort(key=lambda a: (a["task_key"], a["rotation"]))
    tasks = sorted({a["task_key"] for a in selected})
    if len(selected) != 30 or len(tasks) != 10:
        raise ValueError("expected 30 primary archives across 10 tasks")

    # Reconstruct the frozen semantic rankings once on the GPU.
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config["semantic_model"],
                                revision=config["semantic_model_revision"], device="cuda")
    rankings_by_id = {}
    ranking_reconstruction_exact = True
    forced_rows = {(r["archive_id"], r["anchor_id"], r["method"]): r
                   for r in forced["rows"]}
    for archive in selected:
        obs = observable_by_id[archive["archive_id"]]
        truth = recovery_by_id[archive["archive_id"]]
        ids = list(map(str, obs["candidate_ids"]))
        vectors = model.encode(
            [obs["target_language"]] + [memory_text(obs["corrupted_memories"][node]) for node in ids],
            batch_size=32, convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False)
        scores = {node: float(vectors[0] @ vectors[index+1]) for index, node in enumerate(ids)}
        rankings = {node: tuple(forced_exposure_ranking(node, ids, scores, obs["created_at"]))
                    for node in ids}
        rankings_by_id[archive["archive_id"]] = rankings
        for anchor in truth["affected_ids"]:
            for method in observable["methods"]:
                removed = obs["quarantined_ids"][method]
                selected_id = first_survivor(rankings[str(anchor)], removed)
                expected = forced_rows[(archive["archive_id"], str(anchor), method)]
                ranking_reconstruction_exact &= selected_id == expected["post_selected_id"]
                ranking_reconstruction_exact &= selected_success(
                    selected_id, truth["corrupted_policy_by_memory"], truth["success_by_policy"]
                ) == bool(expected["post_success"])

    # Refit each task fold exactly as in the frozen cross-fitted SC-DCTA study.
    payloads = []
    labels = private_by_id
    all_public = public["archives"]
    for held_task in tasks:
        training = [a for a in all_public if a["task_key"] != held_task
                    and float(a["provenance_missing_rate"]) == 0.0]
        cascade, _ = fit_cascade_parameters(training, labels, l2=1.0)
        source_rows = [(source_features(a, str(source)),
                        int(str(source) == str(labels[a["archive_id"]]["active_source_id"])))
                       for a in training for source in a["source_ids"]]
        estimator = fit_source_estimator(source_rows, l2=1.0)
        for archive in [a for a in selected if a["task_key"] == held_task]:
            target_prior = estimator.prior(archive, 0.0)
            posterior, _ = sample_importance_posterior(
                archive, target_prior,
                support_proposal(target_prior, float(config["source_proposal_floor"])),
                cascade, int(config["particles"]),
                stable_seed(str(archive["archive_id"]), int(config["particles"])))
            archive_id = archive["archive_id"]
            payloads.append((posterior, archive, private_by_id[archive_id],
                             observable_by_id[archive_id], recovery_by_id[archive_id],
                             rankings_by_id[archive_id]))

    planner_started = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        for index, result in enumerate(executor.map(evaluate_archive, payloads), start=1):
            results.append(result)
            print(f"[Meta-World TR-DCTA] {index}/30", flush=True)
    tr_episodes = [row for result in results for row in result.pop("episode_rows")]
    combined_episodes = list(forced["rows"]) + tr_episodes
    methods = ["tr_dcta"] + list(config["comparators"])
    summaries = {}
    for method in methods:
        rows = [r for r in combined_episodes if r["method"] == method]
        quarantined = [r for r in rows if r["anchor_quarantined"]]
        summaries[method] = {
            "episodes": len(rows),
            "anchor_quarantine_rate": statistics.fmean(float(r["anchor_quarantined"]) for r in rows),
            "behavioral_recovery_rate": statistics.fmean(float(r["post_success"]) for r in rows),
            "successful_fallback_given_anchor_quarantined": (
                statistics.fmean(float(r["post_success"]) for r in quarantined)
                if quarantined else None),
            "harmful_fallback_count": sum(bool(r["fallback_still_harmful"]) for r in rows),
        }
    comparisons = []
    for metric_index, metric in enumerate(("post_success", "anchor_quarantined")):
        for comparator_index, comparator in enumerate(config["comparators"]):
            comparisons.append(task_bootstrap(
                combined_episodes, "tr_dcta", comparator,
                int(config["bootstrap_draws"]),
                int(config["bootstrap_seed"]) + 10*metric_index + comparator_index, metric))
    integrity = {
        "task_count_10": len(tasks) == 10, "archive_count_30": len(results) == 30,
        "episode_count_182": len(tr_episodes) == 182,
        "semantic_ranking_reconstruction_exact": ranking_reconstruction_exact,
        "four_unique_replays": all(len(r["replayed_ids"]) == 4
                                   and len(set(r["replayed_ids"])) == 4 for r in results),
        "confirmed_quarantine_only": all(set(r["quarantined_ids"]) <= set(r["replayed_ids"])
                                         for r in results),
        "rollout_model_dominance": all(
            r["root_rollout_recovery"] >= r["root_base_recovery"] - 1e-12 for r in results),
        "comparisons_complete": len(comparisons) == 14
        and all(c["task_count"] == 10 for c in comparisons),
    }
    report = {
        "schema_version": "metaworld-tr-dcta-10task-bridge-v1",
        "protocol": config["protocol"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "EXECUTABLE" if all(integrity.values()) else "INVALID",
        "development_only": True, "method_tuned_on_metaworld": False,
        "artifact_hashes": {"config": digest(args.config), "protocol": digest(PROTOCOL),
                            "runner": digest(Path(__file__)), "adapter": digest(adapter),
                            **{name: digest(path) for name, path in paths.items()}},
        "counts": {"tasks": 10, "archives": 30, "exposure_episodes": 182},
        "integrity": integrity, "summaries": summaries, "paired_bootstrap": comparisons,
        "archive_results": results, "tr_episode_rows": tr_episodes,
        "elapsed_s_planner": time.perf_counter() - planner_started,
        "elapsed_s_total": time.perf_counter() - total_started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "integrity": integrity, "summaries": summaries,
                      "elapsed_s_planner": report["elapsed_s_planner"],
                      "elapsed_s_total": report["elapsed_s_total"]}, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
