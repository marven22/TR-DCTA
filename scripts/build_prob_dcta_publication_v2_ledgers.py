"""Split a frozen generation ledger into label-blind public and private data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.publication_v2 import PROTOCOL
from mcx.publication_v2_archive import materialize_task


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.generation.read_text(encoding="utf-8"))
    if source.get("protocol") != f"{PROTOCOL}/generation" or not source.get("complete"):
        raise ValueError("complete publication-v2 generation required")
    public_rows, private_rows = [], []
    for archive in source["archives"]:
        public, private = materialize_task(archive)
        public_rows.extend(public); private_rows.extend(private)
    now = datetime.now(timezone.utc).isoformat()
    public = {
        "protocol": f"{PROTOCOL}/public", "created_at_utc": now,
        "source_generation": str(args.generation),
        "source_generation_sha256": hashlib.sha256(args.generation.read_bytes()).hexdigest(),
        "task_count": len(source["archives"]), "archive_count": len(public_rows),
        "archives": public_rows,
    }
    private = {
        "protocol": f"{PROTOCOL}/private", "created_at_utc": now,
        "public_payload_sha256": canonical_hash(public),
        "task_count": len(source["archives"]), "archive_count": len(private_rows),
        "archives": private_rows,
    }
    for path, value in ((args.public, public), (args.private, private)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"task_count": len(source["archives"]),
                      "archive_count": len(public_rows)}, indent=2))


if __name__ == "__main__":
    main()
