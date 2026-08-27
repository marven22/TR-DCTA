"""Run TR-DCTA and its comparators on the DDXPlus transfer domain.

The Meta-World remediation contract is reused unchanged: only replay-confirmed
harmful memories may be quarantined, after which the agent retrieves the first
surviving memory and executes the procedure it recommends.  Each harmful memory
is forced to rank first once, producing one forced-exposure episode.

Retrieval is scored by token overlap rather than the pinned sentence encoder.
The deviation is recorded in the report: DDXPlus memory text is template
generated, so a neural encoder would add a dependency without adding lexical
signal that the overlap scorer cannot already see.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.confidence_aware_dcta import confidence_aware_decision
from mcx.ddxplus import PROTOCOL
from mcx.metaworld_recovery import (
    first_survivor, forced_exposure_ranking, selected_success, task_variant_maps,
)
from mcx.metaworld_terminal_recovery_dcta import run_metaworld_terminal_recovery_dcta
from mcx.prob_dcta_benchmark import LatentSourceWorld, run_latent_policy
from mcx.publication_v2 import opaque_id
from mcx.publication_v2_posterior import (
    fit_cascade_parameters, sample_importance_posterior, stable_seed, support_proposal,
)
from mcx.publication_v2_source import fit_source_estimator, memory_text, similarity, source_features
from run_metaworld_tr_dcta_10task_bridge_v1 import task_bootstrap
from run_sc_dcta_metaworld_development import harm_weights


ROOT = Path(__file__).resolve().parents[1]
SPLITS = ("development", "validation", "test")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


LEDGER_DIR = ROOT / "results"


def load(split: str, kind: str) -> dict[str, Any]:
    path = LEDGER_DIR / f"ddxplus_{split}_{kind}_mask_consistent.json"
    return json.loads(path.read_text(encoding="utf-8"))


def quarantine_from_replays(replayed: tuple[str, ...], affected: frozenset[str]) -> tuple[str, ...]:
    """The frozen contract quarantines exactly the confirmed-harmful replays."""
    return tuple(node for node in replayed if node in affected)


def evaluate_archive(payload: tuple) -> dict[str, Any]:
    posterior, public, truth, record, budget, comparators, replicates, seed = payload
    affected = frozenset(map(str, truth["affected_ids"]))
    source = str(truth["active_source_id"])
    weights = harm_weights(public)
    ids = [str(node) for node in public["candidate_ids"]]
    memories = public["memories"]
    target = str(public["target_language"])
    scores = {node: similarity(memory_text(memories[node]), target) for node in ids}
    rankings = {node: tuple(forced_exposure_ranking(
        node, ids, scores, public["created_at"])) for node in ids}

    _, _, corrupt_policy, clean_policy = task_variant_maps(record, int(public["rotation"]))
    success = {str(key): bool(value) for key, value in record["policy_success"].items()}
    actual = LatentSourceWorld(source, affected, 1.0)

    @lru_cache(maxsize=None)
    def utility(world_affected: frozenset[str], removed: frozenset[str]) -> tuple[float, float]:
        if not world_affected:
            return 1.0, 1.0
        outcomes = []
        for anchor in world_affected:
            selected = first_survivor(rankings[anchor], removed)
            policy = (corrupt_policy[selected] if selected in world_affected
                      else clean_policy[selected])
            outcomes.append(float(success[policy]))
        return statistics.fmean(outcomes), len(world_affected & removed) / len(world_affected)

    def episodes(method: str, quarantined: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = []
        for anchor in sorted(affected):
            selected = first_survivor(rankings[anchor], quarantined)
            post_success = selected_success(selected, corrupt_policy, success)
            rows.append({
                "archive_id": public["archive_id"], "task_key": public["task_key"],
                "anchor_id": anchor, "method": method,
                "anchor_quarantined": anchor in set(quarantined),
                "post_selected_id": selected, "post_success": post_success,
                "fallback_still_harmful": anchor in set(quarantined) and not post_success,
            })
        return rows

    outcome = run_metaworld_terminal_recovery_dcta(
        posterior, actual, budget, weights=weights, utility=utility)
    rows = episodes("tr_dcta", outcome.quarantined_ids)
    replays = {"tr_dcta": list(outcome.replayed_ids)}

    for method in comparators:
        if method == "random":
            for replicate in range(replicates):
                rng = random.Random(seed + replicate)
                order = list(posterior.candidates)
                rng.shuffle(order)
                replayed = tuple(order[:budget])
                rows.extend(episodes("random", quarantine_from_replays(replayed, affected)))
            continue
        if method == "full_information_oracle":
            ordered = tuple(sorted(affected)) + tuple(
                node for node in sorted(posterior.candidates) if node not in affected)
            replayed = ordered[:budget]
        elif method == "known_source_dcta":
            replayed = run_latent_policy(
                posterior.restrict_source(source), actual, budget,
                method="prob_dcta", weights=weights).replayed_ids
        elif method == "sc_dcta":
            decision = confidence_aware_decision(posterior, budget, weights)
            replayed = run_latent_policy(
                posterior, actual, budget,
                method="top1_dcta" if decision.mode == "hard" else "prob_dcta",
                weights=weights).replayed_ids
        elif method == "hard_source_dcta":
            replayed = run_latent_policy(posterior, actual, budget,
                                         method="top1_dcta", weights=weights).replayed_ids
        else:
            replayed = run_latent_policy(posterior, actual, budget,
                                         method=method, weights=weights).replayed_ids
        replays[method] = list(replayed)
        rows.extend(episodes(method, quarantine_from_replays(replayed, affected)))

    return {
        "archive_id": public["archive_id"], "task_key": public["task_key"],
        "split": public["split"], "rotation": public["rotation"],
        "affected_count": len(affected), "replays": replays,
        "tr_quarantined": list(outcome.quarantined_ids),
        "root_rollout_recovery": outcome.root_rollout_value.recovery,
        "root_base_recovery": outcome.root_base_value.recovery,
        "episode_rows": rows,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    quarantined = [row for row in rows if row["anchor_quarantined"]]
    return {
        "episodes": len(rows),
        "anchor_quarantine_rate": statistics.fmean(
            float(row["anchor_quarantined"]) for row in rows),
        "behavioral_recovery_count": sum(bool(row["post_success"]) for row in rows),
        "behavioral_recovery_rate": statistics.fmean(
            float(row["post_success"]) for row in rows),
        "harmful_fallback_count": sum(bool(row["fallback_still_harmful"]) for row in rows),
        "successful_fallback_given_anchor_quarantined": (
            statistics.fmean(float(row["post_success"]) for row in quarantined)
            if quarantined else None),
    }


def main() -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--ledger-dir", type=Path, default=ROOT / "results",
                        help="directory holding the mask-consistent ledgers")
    parser.add_argument("--budget", type=int,
                        help="override the frozen replay budget for a sweep cell")
    parser.add_argument("--provenance-rate", type=float,
                        help="override the frozen missing-provenance rate")
    parser.add_argument("--particles", type=int,
                        help="override the frozen particle count")
    args = parser.parse_args()
    global LEDGER_DIR
    LEDGER_DIR = args.ledger_dir
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("protocol") != "ddxplus_tr_dcta_v1":
        raise ValueError("frozen DDXPlus evaluation configuration required")
    # Sweep overrides are recorded in the report so a cell is never mistaken
    # for the frozen primary condition.
    overrides = {name: value for name, value in (
        ("budget", args.budget), ("primary_provenance_missing_rate",
                                  args.provenance_rate),
        ("particles", args.particles)) if value is not None}
    config = {**config, **overrides}

    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    records = {str(record["task_id"]): record for record in generation["archives"]}
    public = {split: load(split, "public")["archives"] for split in SPLITS}
    private = {split: load(split, "private")["archives"] for split in SPLITS}
    labels = {row["archive_id"]: row for split in SPLITS for row in private[split]}
    # task_key is a pure function of task_id, so the generation record is
    # recovered by deriving the same opaque identifier.
    record_of_task = {opaque_id(task_id, prefix="task"): record
                      for task_id, record in records.items()}
    rate = float(config["primary_provenance_missing_rate"])
    fit_pool = [row for split in ("development", "validation") for row in public[split]
                if float(row["provenance_missing_rate"]) == 0.0]

    payloads, payload_splits = [], []
    for split in SPLITS:
        selected = sorted((row for row in public[split]
                           if float(row["provenance_missing_rate"]) == rate),
                          key=lambda row: (row["task_key"], row["rotation"]))
        groups = ({"__all_test__": selected} if split == "test" else
                  {task: [row for row in selected if row["task_key"] == task]
                   for task in sorted({row["task_key"] for row in selected})})
        for held_task, held in groups.items():
            training = [row for row in fit_pool if row["task_key"] != held_task] \
                if split != "test" else list(fit_pool)
            if split == "development":
                training = [row for row in training if row["split"] == "development"]
            cascade, _ = fit_cascade_parameters(training, labels, l2=float(config["l2"]))
            estimator = fit_source_estimator(
                [(source_features(row, str(item)),
                  int(str(item) == str(labels[row["archive_id"]]["active_source_id"])))
                 for row in training for item in row["source_ids"]], l2=float(config["l2"]))
            for archive in held:
                prior = estimator.prior(archive, 0.0)
                posterior, _ = sample_importance_posterior(
                    archive, prior,
                    support_proposal(prior, float(config["source_proposal_floor"])),
                    cascade, int(config["particles"]),
                    stable_seed(str(archive["archive_id"]), int(config["particles"])))
                payloads.append((
                    posterior, archive, labels[archive["archive_id"]],
                    record_of_task[str(archive["task_key"])], int(config["budget"]),
                    tuple(config["comparators"]), int(config["random_replicates"]),
                    int(config["bootstrap_seed"])))
                payload_splits.append(split)

    results, episode_rows = [], []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        for index, result in enumerate(executor.map(evaluate_archive, payloads), start=1):
            result["split"] = payload_splits[index - 1]
            for row in result["episode_rows"]:
                row["split"] = result["split"]
            episode_rows.extend(result.pop("episode_rows"))
            results.append(result)
            if index % 20 == 0 or index == len(payloads):
                print(f"[DDXPlus TR-DCTA] {index}/{len(payloads)}", flush=True)

    methods = ["tr_dcta"] + list(config["comparators"])
    scopes = {"all44": episode_rows}
    for split in SPLITS:
        scopes[split] = [row for row in episode_rows if row["split"] == split]
    summaries = {scope: {method: summarize([r for r in rows if r["method"] == method])
                         for method in methods}
                 for scope, rows in scopes.items()}
    comparisons = {}
    for scope_index, (scope, rows) in enumerate(scopes.items()):
        comparisons[scope] = [
            task_bootstrap(rows, "tr_dcta", comparator, int(config["bootstrap_draws"]),
                           int(config["bootstrap_seed"]) + 100 * scope_index + index,
                           "post_success")
            for index, comparator in enumerate(config["comparators"])]

    integrity = {
        "archives_evaluated": len(results) == 132,
        "budget_respected": all(len(value) == int(config["budget"])
                                and len(set(value)) == int(config["budget"])
                                for r in results for value in r["replays"].values()),
        "confirmed_quarantine_only": all(
            set(r["tr_quarantined"]) <= set(r["replays"]["tr_dcta"]) for r in results),
        "rollout_model_dominance": all(
            r["root_rollout_recovery"] >= r["root_base_recovery"] - 1e-12 for r in results),
    }
    report = {
        "schema_version": "ddxplus-tr-dcta-v1",
        "protocol": f"{PROTOCOL}/ddxplus-tr-dcta",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "EXECUTABLE" if all(integrity.values()) else "INVALID",
        "retrieval_deviation": "token overlap, not the pinned sentence encoder",
        "sweep_overrides": overrides,
        # Descriptive, not an integrity condition: a sweep cell is a valid run
        # that simply is not the frozen primary condition.
        "is_frozen_primary_cell": not overrides,
        "artifact_hashes": {"config": digest(args.config),
                            "generation": digest(args.generation),
                            "runner": digest(Path(__file__))},
        "counts": {"archives": len(results), "episodes": len(episode_rows)},
        "integrity": integrity, "summaries": summaries,
        "paired_bootstrap": comparisons, "archive_results": results,
        # Retained so the verifier can re-derive every episode independently.
        "episode_rows": episode_rows,
        "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "integrity": integrity, "test": summaries["test"],
                      "elapsed_s": report["elapsed_s"]}, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
