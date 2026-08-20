"""Compose DDXPlus memory archives with the deterministic template writer.

Every generated record is immediately pushed through the frozen
``materialize_task`` used by the existing benchmarks.  That is the real
acceptance test: if the public/private ledgers materialize, the record shape,
the citation/provenance consistency, and the contaminated/affected labelling
all satisfy the shared pipeline's contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.ddxplus import PROTOCOL
from mcx.ddxplus_writer import (
    build_generation_record, plan_record, silent_corrupted_memories,
)
from mcx.publication_v2_archive import MASK_RATES, materialize_task


ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "src" / "mcx" / "ddxplus_writer.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("protocol") != "ddxplus_generation_v1":
        raise ValueError("frozen DDXPlus generation configuration required")
    if tuple(config["mask_rates"]) != MASK_RATES:
        raise ValueError("DDXPlus must reuse the frozen provenance mask rates")

    population = json.loads(
        (ROOT / config["population_ledger"]).read_text(encoding="utf-8"))
    pinned = config.get("population_identity_sha256")
    actual = population["population_identity_sha256"]
    if pinned and pinned != actual:
        raise ValueError(f"task population drifted: {actual}")
    tasks = population["tasks"]
    if len(tasks) != int(config["expected_task_count"]):
        raise ValueError("unexpected task count")

    records, public_rows, private_rows, silent = [], [], [], []
    for task in tasks:
        record = build_generation_record(task)
        # A pure function of public metadata must regenerate identically.
        if canonical(record) != canonical(build_generation_record(task)):
            raise ValueError(f"writer is not deterministic: {task['task_id']}")
        public, private = materialize_task(record)
        silent.extend({"task_id": str(task["task_id"]), "node": node}
                      for node in silent_corrupted_memories(plan_record(task), record))
        records.append(record)
        public_rows.extend(public)
        private_rows.extend(private)

    rotations = int(config["rotations"])
    expected_rows = len(tasks) * rotations * len(MASK_RATES)
    primary = float(config["primary_provenance_missing_rate"])
    primary_rows = [row for row in public_rows
                    if float(row["provenance_missing_rate"]) == primary]
    affected = [len(row["affected_ids"]) for row in private_rows]
    contaminated = [len(row["contaminated_ids"]) for row in private_rows]
    candidates = len(records[0]["graph"]["candidate_ids"])

    integrity = {
        "public_row_count_exact": len(public_rows) == expected_rows,
        "private_row_count_exact": len(private_rows) == expected_rows,
        "primary_cell_archive_count": len(primary_rows) == len(tasks) * rotations,
        "every_archive_has_harm": all(count > 0 for count in affected),
        "harm_is_subset_of_contamination": all(
            set(row["affected_ids"]) <= set(row["contaminated_ids"])
            for row in private_rows),
        "harm_is_strictly_smaller_somewhere": any(
            len(row["affected_ids"]) < len(row["contaminated_ids"])
            for row in private_rows),
        "no_archive_is_fully_harmful": all(count < candidates for count in affected),
        "corrupted_text_is_visibly_different": not silent,
        "archive_ids_unique": len({row["archive_id"] for row in public_rows})
        == len(public_rows),
        "policy_success_covers_recommendations": all(
            set(record["policy_success"]) >= {
                str(memory["parsed"]["recommended_policy_id"])
                for group in (record["roots"],
                              *[branch["memories"] for branch in record["branches"]])
                for item in group
                for memory in (item["factual"], item["counterfactual"])
            } for record in records),
    }

    payload = {
        "protocol": f"{PROTOCOL}/ddxplus-generation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_payload": config,
        "artifact_hashes": {"config": digest(args.config),
                            "builder": digest(Path(__file__)),
                            "writer": digest(WRITER)},
        "counts": {
            "tasks": len(tasks), "candidates_per_archive": candidates,
            "public_rows": len(public_rows), "private_rows": len(private_rows),
            "primary_cell_archives": len(primary_rows),
        },
        "label_summary": {
            "mean_affected": statistics.fmean(affected),
            "min_affected": min(affected), "max_affected": max(affected),
            "mean_contaminated": statistics.fmean(contaminated),
            "contaminated_but_not_harmful": statistics.fmean(
                c - a for c, a in zip(contaminated, affected)),
        },
        "integrity": integrity,
        "silent_corrupted_memories": silent[:50],
        "archives": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": payload["counts"],
                      "label_summary": payload["label_summary"],
                      "integrity": integrity}, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
