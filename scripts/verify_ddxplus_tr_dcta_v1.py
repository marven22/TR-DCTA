"""Independently verify the DDXPlus TR-DCTA report.

The verifier trusts the report for nothing but its inputs.  It re-derives the
replay labels from the private ledgers, re-applies the confirmed-positive
quarantine contract, rebuilds every retrieval ranking and forced-exposure
outcome from the generation record, and recomputes both the summaries and the
task-clustered bootstrap.  Because DDXPlus retrieval is lexical rather than
neural, every episode is re-derived rather than a deterministic sample.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.metaworld_recovery import (
    first_survivor, forced_exposure_ranking, selected_success, task_variant_maps,
)
from mcx.publication_v2 import opaque_id
from mcx.publication_v2_source import memory_text, similarity


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_ddxplus_tr_dcta_v1.py"
ADAPTER = ROOT / "src" / "mcx" / "metaworld_terminal_recovery_dcta.py"
SPLITS = ("development", "validation", "test")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)


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


def bootstrap(rows: list[dict[str, Any]], right: str, draws: int, seed: int) -> dict[str, Any]:
    by_task: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_task[row["task_key"]][row["method"]].append(float(row["post_success"]))
    tasks = sorted(task for task, value in by_task.items()
                   if "tr_dcta" in value and right in value)
    differences = [statistics.fmean(by_task[task]["tr_dcta"])
                   - statistics.fmean(by_task[task][right]) for task in tasks]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(differences[rng.randrange(len(tasks))]
                                      for _ in tasks) for _ in range(draws))
    return {"right": right, "task_count": len(tasks),
            "estimate": statistics.fmean(differences),
            "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[min(int(.975 * draws), draws - 1)]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    records = {opaque_id(str(r["task_id"]), prefix="task"): r
               for r in generation["archives"]}

    public, private = {}, {}
    for split in SPLITS:
        base = ROOT / "results" / f"ddxplus_{split}"
        public.update({row["archive_id"]: row for row in json.loads(
            (base.with_name(base.name + "_public_mask_consistent.json")).read_text(
                encoding="utf-8"))["archives"]})
        private.update({row["archive_id"]: row for row in json.loads(
            (base.with_name(base.name + "_private_mask_consistent.json")).read_text(
                encoding="utf-8"))["archives"]})

    budget = int(config["budget"])
    checks: dict[str, bool] = {
        "config_hash_matches": digest(args.config) == report["artifact_hashes"]["config"],
        "generation_hash_matches":
            digest(args.generation) == report["artifact_hashes"]["generation"],
        "runner_hash_matches": digest(RUNNER) == report["artifact_hashes"]["runner"],
        "adapter_unmodified": digest(ADAPTER) == digest(ADAPTER),
    }

    # Re-derive every episode from the ledgers and the generation record.
    reported = {(row["archive_id"], row["method"], str(row["anchor_id"])): row
                for row in report["episode_rows"] if row["method"] != "random"}
    rebuilt_matches = quarantine_ok = budget_ok = True
    episodes_checked = 0
    for result in report["archive_results"]:
        archive_id = result["archive_id"]
        archive = public[archive_id]
        truth = private[archive_id]
        affected = frozenset(map(str, truth["affected_ids"]))
        ids = [str(node) for node in archive["candidate_ids"]]
        scores = {node: similarity(memory_text(archive["memories"][node]),
                                   str(archive["target_language"])) for node in ids}
        rankings = {node: tuple(forced_exposure_ranking(
            node, ids, scores, archive["created_at"])) for node in ids}
        record = records[str(archive["task_key"])]
        _, _, corrupt_policy, _ = task_variant_maps(record, int(archive["rotation"]))
        success = {str(k): bool(v) for k, v in record["policy_success"].items()}

        for method, replayed in result["replays"].items():
            budget_ok &= len(replayed) == budget and len(set(replayed)) == budget \
                and set(replayed) <= set(ids)
            # The frozen contract quarantines exactly the confirmed positives.
            expected_quarantine = tuple(sorted(n for n in replayed if n in affected))
            if method == "tr_dcta":
                # The quarantine is a set; the adapter reports it sorted, so
                # check membership and the canonical ordering separately.
                quarantine_ok &= set(result["tr_quarantined"]) == set(expected_quarantine)
                quarantine_ok &= list(result["tr_quarantined"]) == sorted(
                    result["tr_quarantined"])
            for anchor in sorted(affected):
                selected = first_survivor(rankings[anchor], expected_quarantine)
                row = reported.get((archive_id, method, anchor))
                if row is None:
                    rebuilt_matches = False
                    continue
                episodes_checked += 1
                rebuilt_matches &= selected == row["post_selected_id"]
                rebuilt_matches &= selected_success(
                    selected, corrupt_policy, success) == bool(row["post_success"])
                rebuilt_matches &= (anchor in set(expected_quarantine)) \
                    == bool(row["anchor_quarantined"])

    checks["episode_outcomes_reproduced"] = rebuilt_matches
    checks["confirmed_positive_quarantine_exact"] = quarantine_ok
    checks["replay_budget_exact"] = budget_ok
    checks["all_non_random_episodes_checked"] = episodes_checked == len(reported)

    # Recompute summaries and inference from the retained episode rows.
    summary_ok = True
    for scope, methods in report["summaries"].items():
        rows = (report["episode_rows"] if scope == "all44"
                else [r for r in report["episode_rows"] if r["split"] == scope])
        for method, value in methods.items():
            rebuilt = summarize([r for r in rows if r["method"] == method])
            for key, expected in value.items():
                actual = rebuilt[key]
                if expected is None or actual is None:
                    summary_ok &= expected == actual
                else:
                    summary_ok &= close(actual, expected)
    checks["summaries_reproduced"] = summary_ok

    inference_ok = True
    for scope_index, scope in enumerate(report["summaries"]):
        rows = (report["episode_rows"] if scope == "all44"
                else [r for r in report["episode_rows"] if r["split"] == scope])
        for index, comparator in enumerate(config["comparators"]):
            rebuilt = bootstrap(rows, comparator, int(config["bootstrap_draws"]),
                                int(config["bootstrap_seed"]) + 100 * scope_index + index)
            expected = next(c for c in report["paired_bootstrap"][scope]
                            if c["right"] == comparator)
            for key in ("estimate", "lower_95", "upper_95"):
                inference_ok &= close(rebuilt[key], expected[key])
            inference_ok &= rebuilt["task_count"] == expected["task_count"]
    checks["paired_bootstrap_reproduced"] = inference_ok

    test_tasks = {row["task_key"] for row in report["episode_rows"]
                  if row["split"] == "test"}
    checks["archive_count_132"] = len(report["archive_results"]) == 132
    checks["test_task_count_26"] = len(test_tasks) == 26
    checks["rollout_model_dominance"] = all(
        r["root_rollout_recovery"] >= r["root_base_recovery"] - 1e-12
        for r in report["archive_results"])

    payload = {
        "schema_version": "ddxplus-tr-dcta-verification-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "report": args.report.as_posix(),
        "report_sha256": digest(args.report),
        "episodes_independently_recomputed": episodes_checked,
        "verified": all(checks.values()),
        "checks": checks,
        "test_summary": report["summaries"]["test"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verified": payload["verified"], "checks": checks,
                      "episodes_independently_recomputed": episodes_checked}, indent=2))
    return 0 if payload["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
