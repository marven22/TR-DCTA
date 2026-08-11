"""JSON logging.

Every cycle produces one complete JSON record with all the fields required by
the brief. Invalid model output and retries are recorded, never silently fixed.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)


def new_cycle_record(cycle_id: str) -> Dict[str, Any]:
    """A blank record pre-populated with every required key."""
    return {
        "cycle_id": cycle_id,
        "task": {},
        "archive_before": [],
        "retrieved_memories": [],
        "planning_prompt": "",
        "raw_plan_response": "",
        "parsed_plan": [],
        "plan_validation": [],        # list of attempts (invalid output + retry)
        "true_outcome": "",
        "feedback_given": "",
        "reflection_prompt": "",
        "raw_reflection_response": "",
        "reflection_validation": [],
        "new_memory": {},
        "model_checkpoint": "",
        "generation_settings": {},
        "environment_seed": 0,
        "notes": [],
    }


class RunLogger:
    """Collects cycle records for one run and writes them to disk."""

    def __init__(self, out_dir: str, run_name: str) -> None:
        self.out_dir = out_dir
        self.run_name = run_name
        self.records: List[Dict[str, Any]] = []
        os.makedirs(out_dir, exist_ok=True)

    def add(self, record: Dict[str, Any]) -> None:
        self.records.append(record)
        # Write each cycle individually as well, for granular inspection.
        cid = record.get("cycle_id", f"cycle_{len(self.records)}")
        write_json(
            os.path.join(self.out_dir, f"{self.run_name}__{cid}.json"), record
        )

    def flush(self) -> str:
        path = os.path.join(self.out_dir, f"{self.run_name}.json")
        write_json(path, {"run": self.run_name, "cycles": self.records})
        return path
