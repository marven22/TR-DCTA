"""Build separated observable/private manifests for behavioral recovery."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.metaworld_recovery import quarantined_ids, task_variant_maps
from mcx.publication_v2_archive import materialize_task


OBS_PROTOCOL = "sc-dcta/metaworld-recovery-observable-v1"
PRIVATE_PROTOCOL = "sc-dcta/metaworld-recovery-private-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--audit-results", type=Path, required=True)
    parser.add_argument("--observable-output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=4)
    parser.add_argument("--mask", type=float, default=.25)
    parser.add_argument("--methods", nargs="+")
    args = parser.parse_args()

    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    audits = json.loads(args.audit_results.read_text(encoding="utf-8"))
    if not generation.get("complete"):
        raise ValueError("complete generation ledger required")
    if sha256(args.generation) != public.get("source_generation_sha256"):
        raise ValueError("public ledger does not match generation ledger")

    public_by_id = {str(row["archive_id"]): row for row in public["archives"]}
    private_by_id = {str(row["archive_id"]): row for row in private["archives"]}
    selected_ids = {
        archive_id for archive_id, row in public_by_id.items()
        if float(row["provenance_missing_rate"]) == args.mask
    }
    audit_rows = [row for row in audits["rows"]
                  if int(row["budget"]) == args.budget
                  and float(row["provenance_missing_rate"]) == args.mask
                  and str(row["archive_id"]) in selected_ids]
    available_methods = sorted({str(row["method"]) for row in audit_rows})
    methods = args.methods or available_methods
    missing_methods = set(methods) - set(available_methods)
    if missing_methods:
        raise ValueError(f"methods absent from audit ledger: {sorted(missing_methods)}")
    audit_by_key = {(str(row["archive_id"]), str(row["method"])): row
                    for row in audit_rows}

    # Connect opaque archive IDs back to their generated clean/corrupt variants.
    generated_by_archive = {}
    for task in generation["archives"]:
        if task.get("benchmark") != "metaworld":
            continue
        materialized, _ = materialize_task(task)
        for row in materialized:
            generated_by_archive[str(row["archive_id"])] = task

    observable_rows, private_rows = [], []
    for archive_id in sorted(selected_ids):
        archive = public_by_id[archive_id]
        truth = private_by_id[archive_id]
        task = generated_by_archive.get(archive_id)
        if task is None:
            raise ValueError(f"generation record absent for {archive_id}")
        corrupt, clean, corrupt_policy, clean_policy = task_variant_maps(
            task, int(archive["rotation"])
        )
        # The mask-consistent ledger redacts citations whose formation edges are
        # hidden. Behavioral text must still match the source generation.
        for node in archive["candidate_ids"]:
            for field in ("lesson", "expected_outcome"):
                if corrupt[node][field] != archive["memories"][node][field]:
                    raise ValueError(
                        f"public memory text mismatch: {archive_id}, {node}, {field}"
                    )
        corrupt = archive["memories"]
        observed_edges = {tuple(map(str, edge))
                          for edge in archive["observed_formation_edges"]}
        for node, memory in clean.items():
            memory["cited_memory_ids"] = [
                cited for cited in memory["cited_memory_ids"]
                if (str(cited), node) in observed_edges
            ]
        quarantines = {}
        replayed = {}
        for method in methods:
            row = audit_by_key.get((archive_id, method))
            if row is None:
                raise ValueError(f"missing audit row: {archive_id}, {method}")
            replayed[method] = list(map(str, row["replayed_ids"]))
            quarantines[method] = list(quarantined_ids(
                row["replayed_ids"], truth["affected_ids"]
            ))
        observable_rows.append({
            "archive_id": archive_id, "task_key": archive["task_key"],
            "rotation": int(archive["rotation"]),
            "target_language": archive["target_language"],
            "candidate_ids": archive["candidate_ids"],
            "created_at": archive["created_at"],
            "corrupted_memories": corrupt, "clean_memories": clean,
            "replayed_ids": replayed, "quarantined_ids": quarantines,
        })
        private_rows.append({
            "archive_id": archive_id, "task_key": archive["task_key"],
            "affected_ids": truth["affected_ids"],
            "corrupted_policy_by_memory": corrupt_policy,
            "clean_policy_by_memory": clean_policy,
            "success_by_policy": task["policy_success"],
        })

    common = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "split": observable_rows and public_by_id[observable_rows[0]["archive_id"]]["split"],
        "budget": args.budget, "provenance_missing_rate": args.mask,
        "methods": methods, "task_count": len({row["task_key"] for row in observable_rows}),
        "archive_count": len(observable_rows),
        "input_hashes": {"public": sha256(args.public), "private": sha256(args.private),
                         "generation": sha256(args.generation),
                         "audit_results": sha256(args.audit_results)},
    }
    write(args.observable_output, {"protocol": OBS_PROTOCOL, **common,
                                   "archives": observable_rows})
    write(args.private_output, {"protocol": PRIVATE_PROTOCOL, **common,
                                "archives": private_rows})
    print(f"wrote {len(observable_rows)} archives across {common['task_count']} tasks")
    print(f"methods: {', '.join(methods)}")


if __name__ == "__main__":
    main()
