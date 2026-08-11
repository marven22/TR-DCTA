"""Combine sharded Meta-World scalability runs and recompute summaries."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from run_metaworld_scalability import summarize, task_bootstrap_difference


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/metaworld_scalability_freeze_v1.json"))
    parser.add_argument("--split", choices=("development", "validation", "test"), required=True)
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in args.inputs]
    if any(value["protocol"] != config["protocol"] or value["split"] != args.split
           for value in payloads):
        raise ValueError("shard protocol or split mismatch")
    shard_counts = {int(value["shard_count"]) for value in payloads}
    if len(shard_counts) != 1 or len(payloads) != next(iter(shard_counts)):
        raise ValueError("incomplete shard set")
    if {int(value["shard_index"]) for value in payloads} != set(range(len(payloads))):
        raise ValueError("duplicate or missing shard index")
    rows = [row for value in payloads for row in value["rows"]]
    construction = [row for value in payloads for row in value["construction"]]
    profiles = [row for value in payloads for row in value["memory_profiles"]]
    row_keys = {
        (row["archive_id"], row["archive_size"], row["budget"],
         row["provenance_missing_rate"], row["method"])
        for row in rows
    }
    if len(row_keys) != len(rows):
        raise ValueError("duplicate scalability result row")
    expected_archives = int(payloads[0]["expected_total_base_archives"])
    sizes = tuple(map(int, config["archive_sizes"]))
    budgets = tuple(map(int, config["replay_budgets"]))
    methods = tuple(config["methods"])
    expected_rows = expected_archives * len(sizes) * len(budgets) * len(methods)
    if len(rows) != expected_rows:
        raise ValueError(f"incomplete result grid: {len(rows)} != {expected_rows}")
    construction_keys = {
        (row["archive_id"], row["archive_size"], row["provenance_missing_rate"])
        for row in construction
    }
    if len(construction_keys) != expected_archives * len(sizes):
        raise ValueError("incomplete or duplicate construction grid")
    primary_mask = float(config["primary_provenance_missing_rate"])
    primary_budget = int(config["primary_replay_budget"])
    comparisons = {}
    for size in sizes:
        for comparator in ("ens", "hard_source_dcta", "acis_risk", "floored_prob_dcta", "random"):
            comparisons[f"n{size}_sc_minus_{comparator}"] = task_bootstrap_difference(
                rows, size, primary_budget, primary_mask, "sc_dcta", comparator,
                int(config["bootstrap_draws"]), int(config["bootstrap_seed"]) + size,
            )
    output = {
        "protocol": config["protocol"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "split": args.split, "complete": True,
        "archive_sizes": list(sizes), "replay_budgets": list(budgets),
        "provenance_missing_rates": list(config["provenance_missing_rates"]),
        "particles": int(config["particles"]), "methods": list(methods),
        "base_archive_count": expected_archives,
        "task_count": len({row["task_key"] for row in rows}),
        "elapsed_seconds_sum": sum(float(value["elapsed_seconds"]) for value in payloads),
        "summary": summarize(rows), "primary_comparisons": comparisons,
        "construction": construction, "memory_profiles": profiles, "rows": rows,
        "input_hashes": {path.as_posix(): sha256(path) for path in args.inputs},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "split": args.split, "base_archives": expected_archives,
        "rows": len(rows), "construction_rows": len(construction),
        "profile_rows": len(profiles),
    }, indent=2))


if __name__ == "__main__":
    main()
