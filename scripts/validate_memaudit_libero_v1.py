"""Independent structural audit of frozen MemAudit observable/evaluation ledgers."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    events = json.loads(args.events.read_text(encoding="utf-8"))
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    harmful = set(events["harmful_archive_ids"])
    originals = {row["archive_id"]: row for row in events["original_events"]}
    counterfactuals = {}
    for row in events["counterfactual_events"]:
        counterfactuals.setdefault(row["archive_id"], []).append(row)
    post = {}
    for row in events["post_removal_events"]:
        post.setdefault(row["archive_id"], []).append(row)
    labels = {row["archive_id"]: set(row["affected_ids"])
              for row in private["archives"]}
    row_grid = {(row["archive_id"], row["budget"], row["method"])
                for row in evaluation["rows"]}
    expected_grid = {
        (archive_id, budget, method)
        for archive_id in harmful
        for budget in evaluation["budgets"]
        for method in (
            "memaudit_full", "memaudit_cmis_only", "memaudit_cas_only",
            "retrieval_frequency", "random_deletion",
            "dcta_risk_local_v1", "acis_risk",
        )
    }
    selected_harmful = sum(
        originals[archive_id]["selected_id"] in labels[archive_id]
        for archive_id in harmful
    )
    checks = {
        "complete_67_archive_observable_run": (
            events.get("complete") is True and events.get("archive_count") == 67
        ),
        "twenty_observed_harmful_archives": len(harmful) == 20,
        "original_event_count": len(originals) == 67,
        "harm_flags_match_subset": all(
            (float(row["harm"]) == 1.0) == (archive_id in harmful)
            for archive_id, row in originals.items()
        ),
        "five_counterfactuals_per_harmful_event": all(
            len(counterfactuals.get(archive_id, ())) == 5 for archive_id in harmful
        ),
        "counterfactual_removes_originally_retrieved_memory": all(
            row["removed_id"] in originals[archive_id]["retrieved_ids"]
            for archive_id, rows in counterfactuals.items() for row in rows
        ),
        "four_post_removal_budgets_per_harmful_event": all(
            sorted(row["budget"] for row in post.get(archive_id, ())) == [2, 4, 6, 9]
            for archive_id in harmful
        ),
        "ranking_complete_and_unique": all(
            len({row["memory_id"] for row in events["rankings"][archive_id]["scores"]}) == 18
            for archive_id in harmful
        ),
        "selected_harmful_memory_consistency": selected_harmful == len(harmful),
        "complete_evaluation_grid": row_grid == expected_grid,
        "events_hash_matches_evaluation": evaluation["events_sha256"] == sha256(args.events),
        "private_hash_matches_evaluation": evaluation["private_sha256"] == sha256(args.private),
        "freeze_hash_matches_evaluation": evaluation["freeze_sha256"] == sha256(args.freeze),
        "frozen_runner_used": events["runner_sha256"] == freeze["sha256"]["runner"],
        "finite_unit_metrics": all(
            0.0 <= float(row["recall"]) <= 1.0 and int(row["discoveries"]) >= 0
            for row in evaluation["rows"]
        ),
    }
    payload = {
        "protocol": "memaudit-libero-v1/integrity-audit",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": all(checks.values()), "checks": checks,
        "counts": {
            "archives": events["archive_count"], "harmful_archives": len(harmful),
            "counterfactual_events": len(events["counterfactual_events"]),
            "post_removal_events": len(events["post_removal_events"]),
            "evaluation_rows": len(evaluation["rows"]),
            "selected_harmful_memories": selected_harmful,
        },
        "primary": evaluation["summary"]["4"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
