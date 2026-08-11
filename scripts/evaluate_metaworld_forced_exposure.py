"""Evaluate recovery when each harmful descendant is forced to retrieval rank 1."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.memaudit_libero import memory_text
from mcx.metaworld_recovery import (
    first_survivor, forced_exposure_ranking, selected_success,
)


PROTOCOL = "sc-dcta/metaworld-forced-exposure-v1"
OBS_PROTOCOL = "sc-dcta/metaworld-recovery-observable-v1"
PRIVATE_PROTOCOL = "sc-dcta/metaworld-recovery-private-v1"
MODEL = "sentence-transformers/all-mpnet-base-v2"
REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def average(values):
    return statistics.fmean(values) if values else None


def paired_bootstrap(rows, left, right, draws=10_000, seed=61277):
    by_task = {}
    for row in rows:
        by_task.setdefault(row["task_key"], {}).setdefault(row["method"], []).append(
            float(row["post_success"])
        )
    tasks = sorted(task for task, values in by_task.items()
                   if left in values and right in values)
    differences = [average(by_task[t][left]) - average(by_task[t][right]) for t in tasks]
    rng = random.Random(seed)
    samples = sorted(average([differences[rng.randrange(len(differences))]
                              for _ in differences]) for _ in range(draws))
    return {"estimate": average(differences),
            "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[int(.975 * draws)], "task_count": len(tasks),
            "wins": sum(x > 0 for x in differences),
            "ties": sum(x == 0 for x in differences),
            "losses": sum(x < 0 for x in differences)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observable", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observable = json.loads(args.observable.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    if observable.get("protocol") != OBS_PROTOCOL or private.get("protocol") != PRIVATE_PROTOCOL:
        raise ValueError("recovery manifests required")
    truth_by_id = {row["archive_id"]: row for row in private["archives"]}

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL, revision=REVISION, device="cuda")
    rows = []
    for index, archive in enumerate(observable["archives"], start=1):
        truth = truth_by_id[archive["archive_id"]]
        ids = list(map(str, archive["candidate_ids"]))
        memories = archive["corrupted_memories"]
        vectors = model.encode(
            [archive["target_language"]] + [memory_text(memories[node]) for node in ids],
            batch_size=32, convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        )
        scores = {node: float(vectors[0] @ vectors[offset + 1])
                  for offset, node in enumerate(ids)}
        for anchor in truth["affected_ids"]:
            ranking = forced_exposure_ranking(anchor, ids, scores, archive["created_at"])
            # By construction, the exposed corrupted memory recommends a policy
            # previously verified to fail on this target task.
            if selected_success(anchor, truth["corrupted_policy_by_memory"],
                                truth["success_by_policy"]):
                raise ValueError(f"affected anchor unexpectedly succeeds: {anchor}")
            for method in observable["methods"]:
                removed = archive["quarantined_ids"][method]
                selected = first_survivor(ranking, removed)
                post_success = selected_success(
                    selected, truth["corrupted_policy_by_memory"], truth["success_by_policy"]
                )
                rows.append({
                    "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                    "anchor_id": anchor, "method": method,
                    "anchor_quarantined": anchor in set(removed),
                    "post_selected_id": selected, "post_success": post_success,
                    "fallback_still_harmful": anchor in set(removed) and not post_success,
                })
        print(f"archive {index}/{len(observable['archives'])} {archive['archive_id']}", flush=True)

    summaries = {}
    for method in observable["methods"]:
        chosen = [row for row in rows if row["method"] == method]
        quarantined = [row for row in chosen if row["anchor_quarantined"]]
        summaries[method] = {
            "exposure_episode_count": len(chosen),
            "anchor_quarantine_rate": average([float(row["anchor_quarantined"])
                                                for row in chosen]),
            "behavioral_recovery_rate": average([float(row["post_success"])
                                                  for row in chosen]),
            "successful_fallback_given_anchor_quarantined": average([
                float(row["post_success"]) for row in quarantined
            ]),
            "harmful_fallback_count": sum(row["fallback_still_harmful"] for row in chosen),
        }
    comparisons = {method: paired_bootstrap(rows, "sc_dcta", method)
                   for method in observable["methods"] if method != "sc_dcta"}
    payload = {
        "protocol": PROTOCOL, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "design": "each affected descendant is forced to rank 1 for every method; after common quarantine, execute the first surviving memory in the shared semantic ranking",
        "split": observable["split"], "task_count": observable["task_count"],
        "archive_count": observable["archive_count"],
        "exposure_episode_count": len(rows) // len(observable["methods"]),
        "semantic_model": f"{MODEL}@{REVISION}", "summaries": summaries,
        "sc_dcta_paired_comparisons": comparisons, "rows": rows,
        "hashes": {"observable": sha256(args.observable), "private": sha256(args.private)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"exposure_episode_count": payload["exposure_episode_count"],
                      "summaries": summaries, "comparisons": comparisons}, indent=2))


if __name__ == "__main__":
    main()
