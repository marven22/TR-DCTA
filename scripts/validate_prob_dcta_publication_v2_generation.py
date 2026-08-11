"""Validate paired v2 generation and summarize its private functional labels."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from typing import Any, Mapping

import _bootstrap

from mcx.publication_v2 import PROTOCOL


def parsed(record: Mapping[str, object]) -> Mapping[str, object]:
    value = record.get("parsed")
    if not isinstance(value, dict):
        raise ValueError("generation record has no valid parsed output")
    return value


def validate_generated(record: Mapping[str, object], policy_success: Mapping[str, bool]) -> None:
    value = parsed(record)
    policy = str(value["recommended_policy_id"])
    if policy not in policy_success:
        raise ValueError(f"unknown recommended policy: {policy}")
    attempts = record.get("attempts")
    if not isinstance(attempts, list) or not 1 <= len(attempts) <= 2:
        raise ValueError("invalid attempt count")
    if not attempts[-1]["valid"] and not record.get("privacy_sanitization"):
        raise ValueError("last writer attempt is invalid")


def outcome(value: Mapping[str, object], success: Mapping[str, bool]) -> bool:
    return bool(success[str(value["recommended_policy_id"])])


def changed(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return any(left[key] != right[key] for key in (
        "recommended_policy_id", "lesson", "expected_outcome"
    ))


def analyze_archive(archive: Mapping[str, object]) -> list[dict[str, object]]:
    success = {str(key): bool(value) for key, value in archive["policy_success"].items()}
    graph = archive["graph"]
    sources = list(graph["source_ids"]); branches = list(graph["branch_ids"])
    parent_map = {node: [] for node in graph["candidate_ids"]}
    for left, right in graph["formation_edges"]:
        if right in parent_map:
            parent_map[right].append(left)
    branch_records = archive["branches"]
    branch_pairs = {
        item["memory_id"]: (parsed(item["factual"]), parsed(item["counterfactual"]))
        for branch in branch_records for item in branch["memories"]
    }
    shared_records = {item["memory_id"]: item for item in archive["shared_memories"]}
    for root in archive["roots"]:
        validate_generated(root["factual"], success); validate_generated(root["counterfactual"], success)
    for branch in branch_records:
        for item in branch["memories"]:
            validate_generated(item["factual"], success); validate_generated(item["counterfactual"], success)
    for item in shared_records.values():
        for value in item["variants"].values():
            validate_generated(value, success)

    rows = []
    for active in range(3):
        affected: set[str] = set(); contaminated: set[str] = set()
        for branch_index, nodes in enumerate(branches):
            for node in nodes:
                factual, clean = branch_pairs[node]
                selected = factual if branch_index == active else clean
                if branch_index == active and changed(selected, clean):
                    contaminated.add(node)
                if branch_index == active and outcome(selected, success) != outcome(clean, success):
                    affected.add(node)
        for node, item in shared_records.items():
            selected = parsed(item["variants"][f"active_{active}"])
            clean = parsed(item["variants"]["clean"])
            if changed(selected, clean):
                contaminated.add(node)
            if outcome(selected, success) != outcome(clean, success):
                affected.add(node)
        source = sources[active]
        unsupported_harm = []
        unsupported_contamination = []
        for node in contaminated:
            causal_parents = parent_map[node]
            if not any(parent == source or parent in contaminated for parent in causal_parents):
                unsupported_contamination.append(node)
        for node in affected:
            causal_parents = parent_map[node]
            if not any(parent == source or parent in contaminated for parent in causal_parents):
                unsupported_harm.append(node)
        cross_branch = set(graph["shared_ids"]) & affected
        depths = [
            depth for nodes in branches for depth, node in enumerate(nodes, start=1)
            if node in affected
        ]
        rows.append({
            "task_id": archive["task_id"], "benchmark": archive["benchmark"],
            "rotation": active, "affected_count": len(affected),
            "contaminated_count": len(contaminated),
            "shared_affected_count": len(cross_branch),
            "deep_affected_count": sum(depth >= 4 for depth in depths),
            "affected_ids": sorted(affected), "contaminated_ids": sorted(contaminated),
            "unsupported_harm_count": len(unsupported_harm),
            "unsupported_harm_ids": sorted(unsupported_harm),
            "unsupported_contamination_count": len(unsupported_contamination),
            "unsupported_contamination_ids": sorted(unsupported_contamination),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    if generation.get("protocol") != f"{PROTOCOL}/generation" or not generation.get("complete"):
        raise ValueError("complete v2 generation ledger required")
    rows = [row for archive in generation["archives"] for row in analyze_archive(archive)]
    positive = [row for row in rows if row["affected_count"] > 0]
    task_ids = sorted({str(row["task_id"]) for row in rows})
    checks = {
        "all_outputs_valid": True,
        "every_rotation_positive": len(positive) == len(rows),
        "every_task_has_a_deep_harm_rotation": all(any(
            row["task_id"] == task_id and row["deep_affected_count"] > 0 for row in rows
        ) for task_id in task_ids),
        "at_least_half_have_shared_harm": sum(row["shared_affected_count"] > 0 for row in rows) >= len(rows) / 2,
        "all_harm_has_contaminated_causal_parent": all(row["unsupported_harm_count"] == 0 for row in rows),
        "all_contamination_has_causal_parent": all(
            row["unsupported_contamination_count"] == 0 for row in rows
        ),
    }
    payload = {
        "protocol": f"{PROTOCOL}/generation-validation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "generation": str(args.generation), "archive_count": len(generation["archives"]),
        "rotation_count": len(rows), "checks": checks, "passed": all(checks.values()),
        "summary": {
            "mean_affected_count": statistics.fmean(row["affected_count"] for row in rows),
            "range_affected_count": [min(row["affected_count"] for row in rows),
                                     max(row["affected_count"] for row in rows)],
            "mean_contaminated_count": statistics.fmean(row["contaminated_count"] for row in rows),
            "rotations_with_shared_harm": sum(row["shared_affected_count"] > 0 for row in rows),
            "by_benchmark": dict(Counter(str(row["benchmark"]) for row in rows)),
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
