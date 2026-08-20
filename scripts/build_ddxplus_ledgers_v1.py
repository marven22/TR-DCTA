"""Materialize DDXPlus public/private ledgers with citation-consistent masking.

Public archives keep only citations whose formation edge is still observed, so
the memory text cannot reveal a provenance link the auditor is supposed to be
uncertain about.  Private ledgers retain the labels used only by the evaluator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.ddxplus import PROTOCOL
from mcx.publication_v2_archive import materialize_task
from mcx.publication_v2_masking import assert_mask_consistent, mask_hidden_citations


ROOT = Path(__file__).resolve().parents[1]
SPLITS = ("development", "validation", "test")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    args = parser.parse_args()

    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    public_rows: list[dict[str, Any]] = []
    private_rows: list[dict[str, Any]] = []
    redactions = 0
    for record in generation["archives"]:
        public, private = materialize_task(record)
        for archive in public:
            masked, count = mask_hidden_citations(archive)
            assert_mask_consistent(masked)
            redactions += count
            public_rows.append(masked)
        private_rows.extend(private)

    created = datetime.now(timezone.utc).isoformat()
    summary = {}
    for split in SPLITS:
        selected = [row for row in public_rows if row["split"] == split]
        truths = [row for row in private_rows if row["split"] == split]
        if len(selected) != len(truths):
            raise ValueError(f"public/private mismatch in {split}")
        tasks = sorted({row["task_key"] for row in selected})
        common = {"protocol": f"{PROTOCOL}/ddxplus-ledgers", "split": split,
                  "created_at_utc": created, "benchmark_filter": "ddxplus",
                  "task_count": len(tasks), "archive_count": len(selected),
                  "source_generation_sha256": digest(args.generation)}
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / f"ddxplus_{split}_public_mask_consistent.json").write_text(
            json.dumps({**common, "citation_mask_consistent": True,
                        "citation_redactions": redactions, "archives": selected},
                       indent=2) + "\n", encoding="utf-8")
        (args.output_dir / f"ddxplus_{split}_private_mask_consistent.json").write_text(
            json.dumps({**common, "archives": truths}, indent=2) + "\n", encoding="utf-8")
        summary[split] = {"tasks": len(tasks), "archives": len(selected)}
    print(json.dumps({"splits": summary, "citation_redactions": redactions,
                      "public_rows": len(public_rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
