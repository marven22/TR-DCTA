"""Combine disjoint complete generation shards and verify population coverage."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.publication_v2 import PROTOCOL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = [json.loads(path.read_text(encoding="utf-8")) for path in args.input]
    if any(value.get("protocol") != f"{PROTOCOL}/generation" or not value.get("complete")
           for value in values):
        raise ValueError("all shards must be complete v2 generations")
    if len({value["prompt_version"] for value in values}) != 1 or len(
        {json.dumps(value["freeze_payload"], sort_keys=True) for value in values}
    ) != 1:
        raise ValueError("shard writer configurations differ")
    archives = [archive for value in values for archive in value["archives"]]
    if len(archives) != len({archive["task_id"] for archive in archives}):
        raise ValueError("generation shards overlap")
    population = json.loads(args.population.read_text(encoding="utf-8"))
    expected = {row["task_id"] for row in population["tasks"] if row["split"] == args.split}
    if {archive["task_id"] for archive in archives} != expected:
        raise ValueError("generation shards do not exactly cover the frozen split")
    archives.sort(key=lambda archive: archive["task_id"])
    payload = {
        "protocol": f"{PROTOCOL}/generation", "prompt_version": values[0]["prompt_version"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "combined_shards": [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                            for path in args.input],
        "population_path": str(args.population),
        "population_sha256": hashlib.sha256(args.population.read_bytes()).hexdigest(),
        "freeze_payload": values[0]["freeze_payload"], "model": values[0]["model"],
        "selection": {"split": args.split, "task_ids": sorted(expected)},
        "expected_tasks": len(expected), "complete": True, "archives": archives,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"combined {len(archives)} {args.split} archives")


if __name__ == "__main__":
    main()
