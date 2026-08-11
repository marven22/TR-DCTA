"""Build the immutable 69-task production population from completed screens."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.publication_v2 import PROTOCOL, stratified_splits, validate_population


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--libero", type=Path, required=True)
    parser.add_argument("--metaworld", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    libero = json.loads(args.libero.read_text(encoding="utf-8"))
    metaworld = json.loads(args.metaworld.read_text(encoding="utf-8"))
    if not libero.get("complete") or libero["feasibility_gate"]["passed"]:
        raise ValueError("expected the completed, failed frozen LIBERO-only gate")
    if not metaworld.get("complete") or not metaworld["feasibility_gate"]["passed"]:
        raise ValueError("completed, passing Meta-World extension required")

    rows = []
    for item in libero["eligible_targets"]:
        demo = "_".join(map(str, item["demo_indices"]))
        suite = item["suite"]
        target_index = int(item["target_index"])
        rows.append({
            "task_id": f"libero/{suite}/{target_index:02d}",
            "benchmark": "libero", "stratum": suite,
            "target_name": item["target_name"],
            "target_language": item["target_language"],
            "native_policy": f"{suite}/task_{target_index:02d}/demo_{demo}",
            "donors": [{
                "policy": f"{suite}/task_{int(donor['donor_index']):02d}/demo_{demo}",
                "name": donor["donor_name"], "language": donor["donor_language"],
            } for donor in item["donors"]],
            "simulator_evidence": {"native_success": True, "donor_success": [False] * 3},
        })
    for item in metaworld["eligible_targets"]:
        rows.append({
            "task_id": f"metaworld/{item['target_name']}",
            "benchmark": "metaworld", "stratum": "metaworld-v3",
            "target_name": item["target_name"],
            "target_language": item["target_language"],
            "native_policy": item["target_name"],
            "donors": [{
                "policy": donor["donor_name"], "name": donor["donor_name"],
                "language": donor["donor_language"],
            } for donor in item["donors"]],
            "simulator_evidence": {"native_success": True, "donor_success": [False] * 3},
        })
    validate_population(rows)
    for benchmark in ("libero", "metaworld"):
        selected = [row for row in rows if row["benchmark"] == benchmark]
        assignments = stratified_splits([row["task_id"] for row in selected])
        for row in selected:
            row["split"] = assignments[row["task_id"]]
    rows.sort(key=lambda row: row["task_id"])
    payload = {
        "protocol": f"{PROTOCOL}/production-population",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_ledgers": {
            "libero": {"path": str(args.libero), "sha256": sha256(args.libero)},
            "metaworld": {"path": str(args.metaworld), "sha256": sha256(args.metaworld)},
        },
        "task_count": len(rows), "tasks": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    split_counts = {key: sum(row["split"] == key for row in rows)
                    for key in ("development", "validation", "test")}
    print(json.dumps({"task_count": len(rows), "splits": split_counts}, indent=2))


if __name__ == "__main__":
    main()
