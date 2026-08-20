"""Freeze the DDXPlus task population and assign its development splits.

The screen decides which pathologies can host a corruption instance.  This
stage turns that ledger into the immutable task population, assigns the same
hash-stratified 20/20/60 split rule the existing benchmarks use, and records
the identity of the frozen set so later stages can detect drift.

``publication_v2.validate_population`` pins an exact LIBERO/Meta-World census
and is deliberately left untouched; DDXPlus validates its own population
through ``mcx.ddxplus.validate_task_population``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.ddxplus import PROTOCOL, validate_task_population
from mcx.publication_v2 import SPLIT_FRACTIONS, stratified_splits


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def population_identity(task_ids: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(task_ids)).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("protocol") != "ddxplus_population_v1":
        raise ValueError("frozen DDXPlus population configuration required")
    if tuple(config["split_fractions"]) != SPLIT_FRACTIONS:
        raise ValueError("DDXPlus must reuse the frozen 20/20/60 split rule")

    screen_path = ROOT / config["screen_ledger"]
    actual = digest(screen_path)
    pinned = config.get("screen_ledger_sha256")
    if pinned is not None and pinned != actual:
        raise ValueError(f"frozen screen ledger changed: {actual}")
    screen = json.loads(screen_path.read_text(encoding="utf-8"))
    if not screen["feasibility_gate"]["passed"]:
        raise ValueError("the DDXPlus screen did not pass its feasibility gate")

    rows: list[dict[str, Any]] = []
    for target in screen["eligible_targets"]:
        rows.append({
            "task_id": target["task_id"],
            "benchmark": "ddxplus",
            "stratum": target["stratum"],
            "target_name": target["target_name"],
            "target_language": target["target_language"],
            "chief_complaint": target["chief_complaint"],
            "case_id": target["case_id"],
            "native_policy": target["native_policy"],
            "native_language": target["native_language"],
            "native_language_alt": target["native_language_alt"],
            "donors": [{"policy": donor["policy"], "name": donor["name"],
                        "language": donor["language"]}
                       for donor in target["donors"]],
            "simulator_evidence": target["simulator_evidence"],
            "severity": target["severity"],
            "self_referential_presentation": target["self_referential_presentation"],
        })
    counts = validate_task_population(
        rows, required_donors=int(config["required_donors_per_target"]))
    expected = int(config["expected_task_count"])
    if counts["tasks"] != expected:
        raise ValueError(
            f"population drifted: expected {expected} tasks, screen yielded "
            f"{counts['tasks']}; re-freeze the screen before continuing")

    assignments = stratified_splits([row["task_id"] for row in rows])
    for row in rows:
        row["split"] = assignments[row["task_id"]]
    rows.sort(key=lambda row: row["task_id"])
    split_counts = {name: sum(row["split"] == name for row in rows)
                    for name in ("development", "validation", "test")}

    payload = {
        "protocol": f"{PROTOCOL}/ddxplus-population",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_payload": config,
        "source_ledger": {"path": config["screen_ledger"], "sha256": actual},
        "artifact_hashes": {"config": digest(args.config),
                            "builder": digest(Path(__file__))},
        "population_identity_sha256": population_identity(
            [row["task_id"] for row in rows]),
        "counts": {**counts, "splits": split_counts},
        "tasks": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"tasks": counts["tasks"], "splits": split_counts,
                      "population_identity_sha256":
                      payload["population_identity_sha256"][:16]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
