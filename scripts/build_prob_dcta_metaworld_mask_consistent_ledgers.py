"""Filter Meta-World ledgers and remove citations to masked edges."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.publication_v2_masking import assert_mask_consistent, mask_hidden_citations


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    selected = [row for row in public["archives"]
                if row["benchmark"] == "metaworld" and row["split"] == args.split]
    private_by_id = {row["archive_id"]: row for row in private["archives"]}
    corrected = []; redactions = 0
    for archive in selected:
        value, count = mask_hidden_citations(archive)
        assert_mask_consistent(value)
        corrected.append(value); redactions += count
    ids = {row["archive_id"] for row in corrected}
    truths = [private_by_id[archive_id] for archive_id in sorted(ids)]
    if len(truths) != len(corrected):
        raise ValueError("public/private ledger mismatch")
    task_count = len({row["task_key"] for row in corrected})
    created = datetime.now(timezone.utc).isoformat()
    public_payload = {**{key: value for key, value in public.items() if key != "archives"},
                      "created_at_utc": created, "task_count": task_count,
                      "archive_count": len(corrected), "benchmark_filter": "metaworld",
                      "citation_mask_consistent": True, "citation_redactions": redactions,
                      "source_public_sha256": digest(args.public), "archives": corrected}
    private_payload = {**{key: value for key, value in private.items() if key != "archives"},
                       "created_at_utc": created, "task_count": task_count,
                       "archive_count": len(truths), "benchmark_filter": "metaworld",
                       "source_private_sha256": digest(args.private), "archives": truths}
    args.public_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.public_output.write_text(json.dumps(public_payload, indent=2) + "\n", encoding="utf-8")
    args.private_output.write_text(json.dumps(private_payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"split": args.split, "task_count": task_count,
                      "archive_count": len(corrected), "citation_redactions": redactions}, indent=2))


if __name__ == "__main__":
    main()
