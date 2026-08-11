"""Correct the preproduction pilot graph without regenerating identical text."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.publication_v2 import graph_spec


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.input.read_text(encoding="utf-8"))
    for archive in value["archives"]:
        archive["graph"] = graph_spec(str(archive["task_id"]))
    value["graph_correction"] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(args.input),
        "source_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "change": "add each source-to-depth4 edge used by the frozen revival prompt",
        "qwen_outputs_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(f"corrected {len(value['archives'])} archive graphs")


if __name__ == "__main__":
    main()
