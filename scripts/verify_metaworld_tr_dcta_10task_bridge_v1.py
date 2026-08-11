"""Independently verify the 10-task Meta-World TR-DCTA bridge."""

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

import _bootstrap  # noqa: F401

from mcx.memaudit_libero import memory_text
from mcx.metaworld_recovery import first_survivor, forced_exposure_ranking, selected_success


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "METAWORLD_TR_DCTA_10TASK_BRIDGE_PROTOCOL_V1.md"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bootstrap(rows: list[dict], right: str, metric: str,
              draws: int, seed: int) -> dict:
    by_task: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_task[row["task_key"]][row["method"]].append(float(row[metric]))
    tasks = sorted(t for t, values in by_task.items() if "tr_dcta" in values and right in values)
    differences = [statistics.fmean(by_task[t]["tr_dcta"])
                   - statistics.fmean(by_task[t][right]) for t in tasks]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(differences[rng.randrange(len(tasks))] for _ in tasks)
                     for _ in range(draws))
    return {"left": "tr_dcta", "right": right, "metric": metric, "task_count": len(tasks),
            "estimate": statistics.fmean(differences),
            "lower_95": samples[int(.025*draws)],
            "upper_95": samples[min(int(.975*draws), draws-1)],
            "wins": sum(x > 0 for x in differences), "ties": sum(x == 0 for x in differences),
            "losses": sum(x < 0 for x in differences)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    paths = {name: ROOT / path for name, path in config["paths"].items()}
    observable = json.loads(paths["observable"].read_text(encoding="utf-8"))
    recovery_private = json.loads(paths["recovery_private"].read_text(encoding="utf-8"))
    forced = json.loads(paths["forced_evaluation"].read_text(encoding="utf-8"))
    obs_by_id = {a["archive_id"]: a for a in observable["archives"]}
    truth_by_id = {a["archive_id"]: a for a in recovery_private["archives"]}
    result_by_id = {a["archive_id"]: a for a in report["archive_results"]}
    tr_rows = report["tr_episode_rows"]
    tr_by_key = {(r["archive_id"], r["anchor_id"]): r for r in tr_rows}

    labels_exact = all(
        r["labels"] == [int(node in set(truth_by_id[r["archive_id"]]["affected_ids"]))
                        for node in r["replayed_ids"]] for r in report["archive_results"])
    quarantine_exact = all(
        set(r["quarantined_ids"]) == {node for node, label in zip(r["replayed_ids"], r["labels"])
                                      if label} for r in report["archive_results"])

    # Independently regenerate frozen rankings and TR outcomes for three tasks/rotations.
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config["semantic_model"],
                                revision=config["semantic_model_revision"], device="cuda")
    sample_checks = []
    sample_ids = sorted(result_by_id)[::10]
    for archive_id in sample_ids:
        obs = obs_by_id[archive_id]
        truth = truth_by_id[archive_id]
        result = result_by_id[archive_id]
        ids = list(map(str, obs["candidate_ids"]))
        vectors = model.encode(
            [obs["target_language"]] + [memory_text(obs["corrupted_memories"][node]) for node in ids],
            batch_size=32, convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False)
        scores = {node: float(vectors[0] @ vectors[index+1]) for index, node in enumerate(ids)}
        for anchor in truth["affected_ids"]:
            ranking = forced_exposure_ranking(str(anchor), ids, scores, obs["created_at"])
            selected = first_survivor(ranking, result["quarantined_ids"])
            expected = tr_by_key[(archive_id, str(anchor))]
            sample_checks.append({
                "archive_id": archive_id, "anchor_id": anchor,
                "selected_match": selected == expected["post_selected_id"],
                "success_match": selected_success(
                    selected, truth["corrupted_policy_by_memory"], truth["success_by_policy"]
                ) == bool(expected["post_success"]),
                "quarantine_match": (str(anchor) in set(result["quarantined_ids"]))
                == bool(expected["anchor_quarantined"]),
            })

    combined = list(forced["rows"]) + tr_rows
    summaries = {}
    for method in ["tr_dcta"] + list(config["comparators"]):
        chosen = [r for r in combined if r["method"] == method]
        quarantined = [r for r in chosen if r["anchor_quarantined"]]
        summaries[method] = {
            "episodes": len(chosen),
            "anchor_quarantine_rate": statistics.fmean(float(r["anchor_quarantined"])
                                                         for r in chosen),
            "behavioral_recovery_rate": statistics.fmean(float(r["post_success"])
                                                           for r in chosen),
            "successful_fallback_given_anchor_quarantined": statistics.fmean(
                float(r["post_success"]) for r in quarantined) if quarantined else None,
            "harmful_fallback_count": sum(bool(r["fallback_still_harmful"]) for r in chosen),
        }
    comparisons = []
    for mi, metric in enumerate(("post_success", "anchor_quarantined")):
        for ci, comparator in enumerate(config["comparators"]):
            comparisons.append(bootstrap(
                combined, comparator, metric, int(config["bootstrap_draws"]),
                int(config["bootstrap_seed"]) + 10*mi + ci))
    adapter = ROOT / "src" / "mcx" / "metaworld_terminal_recovery_dcta.py"
    checks = {
        "schema_status_valid": report["schema_version"] == "metaworld-tr-dcta-10task-bridge-v1"
        and report["status"] == "EXECUTABLE" and report["development_only"],
        "input_hashes_pinned": all(digest(path) == config["hashes"][name]
                                   for name, path in paths.items())
        and digest(adapter) == config["hashes"]["adapter"],
        "artifact_hashes_match": report["artifact_hashes"] == {
            "config": digest(args.config), "protocol": digest(PROTOCOL),
            "runner": digest(ROOT / "scripts" / "run_metaworld_tr_dcta_10task_bridge_v1.py"),
            "adapter": digest(adapter), **{name: digest(path) for name, path in paths.items()}},
        "archive_task_counts": len(report["archive_results"]) == 30
        and len({r["task_key"] for r in report["archive_results"]}) == 10,
        "episode_count": len(tr_rows) == 182 and len(tr_by_key) == 182,
        "labels_exact": labels_exact, "confirmed_quarantine_exact": quarantine_exact,
        "four_unique_replays": all(len(r["replayed_ids"]) == 4
                                   and len(set(r["replayed_ids"])) == 4
                                   for r in report["archive_results"]),
        "rollout_dominance": all(r["root_rollout_recovery"] >= r["root_base_recovery"] - 1e-12
                                 for r in report["archive_results"]),
        "sample_behavior_exact": bool(sample_checks) and all(
            c["selected_match"] and c["success_match"] and c["quarantine_match"]
            for c in sample_checks),
        "summaries_exact": summaries == report["summaries"],
        "bootstrap_exact": comparisons == report["paired_bootstrap"],
        "reported_integrity_all_true": all(report["integrity"].values()),
    }
    output = {"schema_version": "metaworld-tr-dcta-10task-bridge-verification-v1",
              "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "verified": all(checks.values()), "report_sha256": digest(args.report),
              "checks": checks, "sample_checks": sample_checks,
              "summaries": summaries}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if output["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
