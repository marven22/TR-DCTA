"""Create observable and private-label ledgers from completed external archives."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.memory_libero_v041 import build_archive, is_strict_record


GENERATION_PROTOCOL = "memory-libero/external-validation-v1/irregular-dag"
PUBLIC_PROTOCOL = "memory-libero/external-validation-v1/public"
PRIVATE_PROTOCOL = "memory-libero/external-validation-v1/private-labels"


def canonical_hash(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.generation.read_text(encoding="utf-8"))
    if source.get("protocol") != GENERATION_PROTOCOL or not source.get("complete"):
        raise ValueError("complete external-v1 generation ledger required")
    evaluator_hash = hashlib.sha256(args.evaluator.read_bytes()).hexdigest()
    public_archives, private_archives, excluded = [], [], []
    for record in source["archives"]:
        if not is_strict_record(record):
            excluded.append(record["archive_id"])
            continue
        archive = build_archive(record)
        public_archives.append({
            "archive_id": archive.archive_id, "suite": archive.suite,
            "split": archive.split, "source_id": archive.source_id,
            "candidate_ids": list(archive.candidate_ids),
            "formation_edges": [list(edge) for edge in sorted(archive.true_edges)],
            "memories": archive.memories,
            "created_at": dict(archive.created_at),
            "direct_gateways": sorted(archive.direct_gateways),
            "target_language": archive.target_language,
        })
        private_archives.append({
            "archive_id": archive.archive_id,
            "affected_ids": sorted(archive.affected_ids),
            "affected_count": len(archive.affected_ids),
        })
    common = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "generation_sha256": hashlib.sha256(args.generation.read_bytes()).hexdigest(),
        "evaluator_sha256_before_label_join": evaluator_hash,
        "strict_archive_count": len(public_archives),
        "excluded_archive_ids": excluded,
    }
    public = {"protocol": PUBLIC_PROTOCOL, **common, "archives": public_archives}
    private = {
        "protocol": PRIVATE_PROTOCOL, **common,
        "public_payload_sha256": canonical_hash(public), "archives": private_archives,
    }
    write(args.public_output, public)
    write(args.private_output, private)
    print(json.dumps({
        "strict_archive_count": len(public_archives), "excluded_count": len(excluded),
        "public_payload_sha256": private["public_payload_sha256"],
        "evaluator_sha256_before_label_join": evaluator_hash,
    }, indent=2))


if __name__ == "__main__":
    main()
