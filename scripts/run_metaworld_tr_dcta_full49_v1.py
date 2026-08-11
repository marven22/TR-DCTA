"""Run frozen TR-DCTA on the complete 49-task MetaWorld matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.memaudit_libero import memory_text
from mcx.metaworld_recovery import first_survivor, forced_exposure_ranking, selected_success
from mcx.publication_v2_posterior import (
    fit_cascade_parameters, sample_importance_posterior, stable_seed, support_proposal,
)
from mcx.publication_v2_source import fit_source_estimator, source_features
from run_metaworld_tr_dcta_10task_bridge_v1 import evaluate_archive, task_bootstrap


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "METAWORLD_TR_DCTA_FULL49_PROTOCOL_V1.md"
ADAPTER = ROOT / "src" / "mcx" / "metaworld_terminal_recovery_dcta.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_method(name: str) -> str:
    return {"ens": "sc_ens", "source_then_dcta": "sc_source_then_dcta"}.get(name, name)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    quarantined = [row for row in rows if row["anchor_quarantined"]]
    return {
        "episodes": len(rows),
        "anchor_quarantine_count": sum(bool(row["anchor_quarantined"]) for row in rows),
        "anchor_quarantine_rate": statistics.fmean(
            float(row["anchor_quarantined"]) for row in rows),
        "behavioral_recovery_count": sum(bool(row["post_success"]) for row in rows),
        "behavioral_recovery_rate": statistics.fmean(float(row["post_success"]) for row in rows),
        "successful_fallback_given_anchor_quarantined": (
            statistics.fmean(float(row["post_success"]) for row in quarantined)
            if quarantined else None),
        "harmful_fallback_count": sum(bool(row["fallback_still_harmful"]) for row in rows),
    }


def main() -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    paths = {name: ROOT / value for name, value in config["paths"].items()}
    for name, path in paths.items():
        actual = digest(path)
        if actual != config["hashes"][name]:
            raise ValueError(f"frozen input changed: {name}: {actual}")
    if digest(ADAPTER) != config["hashes"]["adapter"]:
        raise ValueError("frozen MetaWorld TR-DCTA adapter changed")

    splits: dict[str, dict[str, Any]] = {}
    for split in ("development", "validation", "test"):
        splits[split] = {
            "public": json.loads(paths[f"{split}_public"].read_text(encoding="utf-8")),
            "private": json.loads(paths[f"{split}_private"].read_text(encoding="utf-8")),
            "observable": json.loads(paths[f"{split}_observable"].read_text(encoding="utf-8")),
            "recovery": json.loads(paths[f"{split}_recovery_private"].read_text(encoding="utf-8")),
            "forced": json.loads(paths[f"{split}_forced"].read_text(encoding="utf-8")),
        }

    # Construct split-local ledgers and select the already frozen primary cell.
    selected: dict[str, list[dict[str, Any]]] = {}
    task_to_split: dict[str, str] = {}
    for split, ledgers in splits.items():
        selected[split] = sorted(
            [a for a in ledgers["public"]["archives"]
             if float(a["provenance_missing_rate"]) == float(config["provenance_missing_rate"])],
            key=lambda a: (a["task_key"], a["rotation"]),
        )
        tasks = sorted({a["task_key"] for a in selected[split]})
        expected_tasks = int(config["task_counts"][split])
        if len(tasks) != expected_tasks or len(selected[split]) != 3 * expected_tasks:
            raise ValueError(f"unexpected {split} primary matrix")
        for task in tasks:
            if task in task_to_split:
                raise ValueError("task identity overlaps splits")
            task_to_split[task] = split

    # Reconstruct frozen semantic rankings once using the pinned embedding model.
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config["semantic_model"],
                                revision=config["semantic_model_revision"], device="cuda")
    rankings_by_id: dict[str, dict[str, tuple[str, ...]]] = {}
    ranking_exact = True
    baseline_rows: list[dict[str, Any]] = []
    for split, ledgers in splits.items():
        observable_by_id = {a["archive_id"]: a for a in ledgers["observable"]["archives"]}
        recovery_by_id = {a["archive_id"]: a for a in ledgers["recovery"]["archives"]}
        forced_by_key = {(r["archive_id"], str(r["anchor_id"]), r["method"]): r
                         for r in ledgers["forced"]["rows"]}
        for archive in selected[split]:
            archive_id = archive["archive_id"]
            obs = observable_by_id[archive_id]
            truth = recovery_by_id[archive_id]
            ids = list(map(str, obs["candidate_ids"]))
            vectors = model.encode(
                [obs["target_language"]]
                + [memory_text(obs["corrupted_memories"][node]) for node in ids],
                batch_size=32, convert_to_numpy=True, normalize_embeddings=True,
                show_progress_bar=False,
            )
            scores = {node: float(vectors[0] @ vectors[index + 1])
                      for index, node in enumerate(ids)}
            rankings = {node: tuple(forced_exposure_ranking(
                node, ids, scores, obs["created_at"])) for node in ids}
            rankings_by_id[archive_id] = rankings
            for anchor in map(str, truth["affected_ids"]):
                for method in ledgers["observable"]["methods"]:
                    removed = obs["quarantined_ids"][method]
                    selected_id = first_survivor(rankings[anchor], removed)
                    expected = forced_by_key[(archive_id, anchor, method)]
                    ranking_exact &= selected_id == expected["post_selected_id"]
                    ranking_exact &= selected_success(
                        selected_id, truth["corrupted_policy_by_memory"],
                        truth["success_by_policy"]) == bool(expected["post_success"])

        for row in ledgers["forced"]["rows"]:
            method = normalized_method(str(row["method"]))
            if method not in config["comparators"]:
                continue
            copied = dict(row)
            copied["method"] = method
            copied["split"] = split
            baseline_rows.append(copied)

    dev_archives = splits["development"]["public"]["archives"]
    val_archives = splits["validation"]["public"]["archives"]
    dev_labels = {a["archive_id"]: a for a in splits["development"]["private"]["archives"]}
    val_labels = {a["archive_id"]: a for a in splits["validation"]["private"]["archives"]}
    all_fit_archives = dev_archives + val_archives
    all_fit_labels = {**dev_labels, **val_labels}

    payloads: list[tuple[Any, dict, dict, dict, dict, dict]] = []
    payload_splits: list[str] = []
    fit_records: list[dict[str, Any]] = []
    for split in ("development", "validation", "test"):
        public_by_task: dict[str, list[dict[str, Any]]] = {}
        for archive in selected[split]:
            public_by_task.setdefault(str(archive["task_key"]), []).append(archive)
        private_by_id = {a["archive_id"]: a for a in splits[split]["private"]["archives"]}
        observable_by_id = {a["archive_id"]: a for a in splits[split]["observable"]["archives"]}
        recovery_by_id = {a["archive_id"]: a for a in splits[split]["recovery"]["archives"]}

        # Test has one frozen 20-task fit. Development and validation retain
        # their original held-task-out contracts.
        fit_groups = [("__all_test__", [a for group in public_by_task.values() for a in group])]
        if split != "test":
            fit_groups = sorted(public_by_task.items())
        for held_task, held_archives in fit_groups:
            if split == "development":
                training = [a for a in dev_archives
                            if a["task_key"] != held_task
                            and float(a["provenance_missing_rate"]) == 0.0]
                labels = dev_labels
            elif split == "validation":
                training = [a for a in all_fit_archives
                            if a["task_key"] != held_task
                            and float(a["provenance_missing_rate"]) == 0.0]
                labels = all_fit_labels
            else:
                training = [a for a in all_fit_archives
                            if float(a["provenance_missing_rate"]) == 0.0]
                labels = all_fit_labels
            cascade, counts = fit_cascade_parameters(training, labels, l2=float(config["l2"]))
            source_rows = [
                (source_features(a, str(source)),
                 int(str(source) == str(labels[a["archive_id"]]["active_source_id"])))
                for a in training for source in a["source_ids"]
            ]
            estimator = fit_source_estimator(source_rows, l2=float(config["l2"]))
            fit_records.append({"split": split, "held_task": held_task,
                                "training_task_count": len({a["task_key"] for a in training}),
                                "source_row_count": len(source_rows), "cascade_counts": counts})
            for archive in held_archives:
                target_prior = estimator.prior(archive, 0.0)
                posterior, _ = sample_importance_posterior(
                    archive, target_prior,
                    support_proposal(target_prior, float(config["source_proposal_floor"])),
                    cascade, int(config["particles"]),
                    stable_seed(str(archive["archive_id"]), int(config["particles"])),
                )
                archive_id = archive["archive_id"]
                payloads.append((posterior, archive, private_by_id[archive_id],
                                 observable_by_id[archive_id], recovery_by_id[archive_id],
                                 rankings_by_id[archive_id]))
                payload_splits.append(split)

    planner_started = time.perf_counter()
    archive_results: list[dict[str, Any]] = []
    tr_rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        for index, result in enumerate(executor.map(evaluate_archive, payloads), start=1):
            split = payload_splits[index - 1]
            result["split"] = split
            episodes = result.pop("episode_rows")
            for row in episodes:
                row["split"] = split
            tr_rows.extend(episodes)
            archive_results.append(result)
            if index % 10 == 0 or index == len(payloads):
                print(f"[MetaWorld TR-DCTA full49] {index}/{len(payloads)}", flush=True)

    bridge = json.loads(paths["bridge"].read_text(encoding="utf-8"))
    old_by_id = {r["archive_id"]: r for r in bridge["archive_results"]}
    bridge_exact = True
    for row in [r for r in archive_results if r["split"] == "development"]:
        old = old_by_id[row["archive_id"]]
        for key in ("replayed_ids", "labels", "quarantined_ids", "discoveries",
                    "weighted_discovery_recall", "behavioral_recovery",
                    "anchor_quarantine_rate"):
            bridge_exact &= row[key] == old[key]

    all_rows = baseline_rows + tr_rows
    methods = ["tr_dcta"] + list(config["comparators"])
    scopes = {"all49": all_rows}
    for split in ("development", "validation", "test"):
        scopes[split] = [row for row in all_rows if row["split"] == split]
    summaries: dict[str, Any] = {}
    comparisons: dict[str, Any] = {}
    for scope, rows in scopes.items():
        summaries[scope] = {method: summarize([r for r in rows if r["method"] == method])
                            for method in methods}
        expected_tasks = 49 if scope == "all49" else int(config["task_counts"][scope])
        comparisons[scope] = []
        for metric_index, metric in enumerate(("post_success", "anchor_quarantined")):
            for comparator_index, comparator in enumerate(config["comparators"]):
                comparison = task_bootstrap(
                    rows, "tr_dcta", comparator, int(config["bootstrap_draws"]),
                    int(config["bootstrap_seed"]) + 1000 * list(scopes).index(scope)
                    + 10 * metric_index + comparator_index, metric)
                if comparison["task_count"] != expected_tasks:
                    raise ValueError(f"incomplete comparison: {scope} {comparator}")
                comparisons[scope].append(comparison)

    integrity = {
        "task_count_49": len(task_to_split) == 49,
        "archive_count_147": len(archive_results) == 147,
        "episode_count_919": len(tr_rows) == 919,
        "semantic_ranking_reconstruction_exact": ranking_exact,
        "four_unique_replays": all(len(r["replayed_ids"]) == 4
                                   and len(set(r["replayed_ids"])) == 4
                                   for r in archive_results),
        "confirmed_quarantine_only": all(
            set(r["quarantined_ids"]) <= {node for node, label in zip(r["replayed_ids"], r["labels"])
                                           if int(label) == 1}
            for r in archive_results),
        "rollout_model_dominance": all(
            r["root_rollout_recovery"] >= r["root_base_recovery"] - 1e-12
            for r in archive_results),
        "bridge_development_exact": bridge_exact,
        "comparison_matrix_complete": all(len(value) == 14 for value in comparisons.values()),
    }
    report = {
        "schema_version": "metaworld-tr-dcta-full49-v1",
        "protocol": config["protocol"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "EXECUTABLE" if all(integrity.values()) else "INVALID",
        "method_tuned_on_metaworld": False,
        "claim_boundary": {"test": "locked 29-task transfer evaluation",
                           "all49": "descriptive; development and validation were previously observed"},
        "artifact_hashes": {"config": digest(args.config), "protocol": digest(PROTOCOL),
                            "runner": digest(Path(__file__)), "adapter": digest(ADAPTER),
                            **{name: digest(path) for name, path in paths.items()}},
        "counts": {"tasks": 49, "archives": 147, "exposure_episodes": 919,
                   "split_tasks": config["task_counts"]},
        "integrity": integrity,
        "summaries": summaries,
        "paired_bootstrap": comparisons,
        "fit_records": fit_records,
        "archive_results": archive_results,
        "tr_episode_rows": tr_rows,
        "elapsed_s_planner": time.perf_counter() - planner_started,
        "elapsed_s_total": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "integrity": integrity, "test": summaries["test"],
                      "all49": summaries["all49"],
                      "elapsed_s_total": report["elapsed_s_total"]}, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
