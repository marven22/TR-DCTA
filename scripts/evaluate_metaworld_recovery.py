"""Privately score observable Meta-World recovery selections."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.metaworld_recovery import aggregate_recovery, selected_success


PROTOCOL = "sc-dcta/metaworld-recovery-evaluation-v1"
OBS_PROTOCOL = "sc-dcta/metaworld-recovery-observable-v1"
PRIVATE_PROTOCOL = "sc-dcta/metaworld-recovery-private-v1"
EVENT_PROTOCOL = "sc-dcta/metaworld-recovery-events-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean(values):
    return statistics.fmean(values) if values else None


def clustered_bootstrap(rows, left, right, draws=10_000, seed=94731):
    per_task = {}
    for row in rows:
        if not row["eligible"]:
            continue
        task = row["task_key"]
        per_task.setdefault(task, {}).setdefault(row["method"], []).append(
            float(row["post_success"])
        )
    tasks = sorted(task for task, values in per_task.items()
                   if left in values and right in values)
    differences = [mean(per_task[task][left]) - mean(per_task[task][right])
                   for task in tasks]
    if not differences:
        return {"estimate": None, "lower_95": None, "upper_95": None,
                "task_count": 0, "wins": 0, "ties": 0, "losses": 0}
    rng = random.Random(seed)
    samples = sorted(mean([differences[rng.randrange(len(differences))]
                           for _ in differences]) for _ in range(draws))
    return {
        "estimate": mean(differences), "lower_95": samples[int(.025 * draws)],
        "upper_95": samples[int(.975 * draws)], "task_count": len(tasks),
        "wins": sum(value > 0 for value in differences),
        "ties": sum(value == 0 for value in differences),
        "losses": sum(value < 0 for value in differences),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observable", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observable = json.loads(args.observable.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    events = json.loads(args.events.read_text(encoding="utf-8"))
    if observable.get("protocol") != OBS_PROTOCOL:
        raise ValueError("wrong observable manifest")
    if private.get("protocol") != PRIVATE_PROTOCOL:
        raise ValueError("wrong private manifest")
    if events.get("protocol") != EVENT_PROTOCOL:
        raise ValueError("wrong event ledger")
    if events.get("observable_sha256") != sha256(args.observable):
        raise ValueError("events do not match observable manifest")

    obs_by_id = {row["archive_id"]: row for row in observable["archives"]}
    truth_by_id = {row["archive_id"]: row for row in private["archives"]}
    base = {}
    posts = {}
    for event in events["events"]:
        archive_id = event["archive_id"]
        selected = event["selected_id"]
        if selected is None:
            raise ValueError("cannot score invalid selection")
        truth = truth_by_id[archive_id]
        clean = event["condition"] == "clean"
        success = selected_success(
            selected,
            truth["clean_policy_by_memory"] if clean else truth["corrupted_policy_by_memory"],
            truth["success_by_policy"],
        )
        if event["condition"] in ("clean", "corrupted"):
            base.setdefault(archive_id, {})[event["condition"]] = success
        else:
            for method in event["methods"]:
                posts[archive_id, method] = success

    rows = []
    for archive_id, archive in obs_by_id.items():
        corrupt_success = base[archive_id]["corrupted"]
        clean_success = base[archive_id]["clean"]
        eligible = not corrupt_success and clean_success
        affected = set(truth_by_id[archive_id]["affected_ids"])
        benign_count = len(set(archive["candidate_ids"]) - affected)
        for method in observable["methods"]:
            removed = set(archive["quarantined_ids"][method])
            replayed = set(archive["replayed_ids"][method])
            rows.append({
                "archive_id": archive_id, "task_key": archive["task_key"],
                "method": method, "corrupted_success": corrupt_success,
                "clean_success": clean_success,
                "post_success": posts[archive_id, method], "eligible": eligible,
                "harmful_quarantined": len(removed & affected),
                "false_quarantines": len(removed - affected),
                "benign_memories_retained": benign_count - len(removed - affected),
                "benign_memory_count": benign_count,
                "benign_replays": len(replayed - affected),
            })

    methods = observable["methods"]
    summaries = {}
    for method in methods:
        chosen = [row for row in rows if row["method"] == method]
        eligible_rows = [row for row in chosen if row["eligible"]]
        before = mean([float(row["corrupted_success"]) for row in chosen])
        after = mean([float(row["post_success"]) for row in chosen])
        clean = mean([float(row["clean_success"]) for row in chosen])
        summaries[method] = {
            "archive_count": len(chosen), "eligible_archive_count": len(eligible_rows),
            "corrupted_success_rate": before, "post_success_rate": after,
            "clean_success_rate": clean,
            "eligible_recovery_rate": mean([float(row["post_success"])
                                             for row in eligible_rows]),
            "aggregate_clean_deficit_recovered": aggregate_recovery(before, after, clean),
            "mean_harmful_quarantined": mean([row["harmful_quarantined"] for row in chosen]),
            "mean_benign_replays": mean([row["benign_replays"] for row in chosen]),
            "false_quarantines": sum(row["false_quarantines"] for row in chosen),
        }
    primary = "sc_dcta"
    comparisons = {method: clustered_bootstrap(rows, primary, method)
                   for method in methods if method != primary}
    payload = {
        "protocol": PROTOCOL, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "split": observable["split"], "task_count": observable["task_count"],
        "archive_count": observable["archive_count"],
        "eligible_archive_count": sum(1 for values in base.values()
                                      if not values["corrupted"] and values["clean"]),
        "summaries": summaries, "sc_dcta_paired_comparisons": comparisons,
        "rows": rows,
        "hashes": {"observable": sha256(args.observable), "private": sha256(args.private),
                   "events": sha256(args.events)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"eligible_archive_count": payload["eligible_archive_count"],
                      "summaries": summaries, "comparisons": comparisons}, indent=2))


if __name__ == "__main__":
    main()
