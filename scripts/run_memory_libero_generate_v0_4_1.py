"""Extend v0.4 archives with paired irregular-DAG descendants."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import _bootstrap
import run_memory_libero_generate_v0_3_1 as writer
import run_memory_libero_generate_v0_3_2  # apply relaxed validation
from run_memory_libero_generate_v0_4 import render_prompt

from mcx.config import GenerationSettings, config_from_env
from mcx.memory_libero_v04 import PROTOCOL as BASE_PROTOCOL, is_strict_record
from mcx.model import build_backend


PROTOCOL = "memory-libero/counterfactual-cascade-v0.4.1"
PROMPT_VERSION = "memory-libero-v0.4.1-irregular-dag-extension-r2"


def _parsed_parent(item, world):
    return {"memory_id": item["memory_id"], **item[world]["parsed"]}


def _branch_by_regime(base, regime):
    return next(branch for branch in base["branches"] if branch["regime"] == regime)


def checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def generate_pair(backend, *, base, memory_id, parents, selected, feedback, depth):
    task = base["target"]["target_language"]
    donor, native = base["donor_policy_id"], base["native_policy_id"]
    factual = [left for left, _ in parents]
    counterfactual = [right for _, right in parents]
    common = dict(
        memory_id=memory_id, depth=depth, task_language=task,
        selected_policy_id=selected, allowed_policy_ids=[donor, native],
        simulator_success_by_demo=[False, True], feedback=feedback,
    )
    factual_prompt = render_prompt(**common, retrieved=factual)
    counterfactual_prompt = render_prompt(**common, retrieved=counterfactual)
    forbidden = [base["invalid_source"]["memory_id"], donor, native, memory_id]
    forbidden += [p["memory_id"] for pair in parents for p in pair]
    factual_generation = writer.generate_one(
        backend, prompt=factual_prompt, task_language=task,
        allowed=[donor, native], retrieved=factual, forbidden_ids=forbidden,
    )
    counterfactual_generation = writer.generate_one(
        backend, prompt=counterfactual_prompt, task_language=task,
        allowed=[donor, native], retrieved=counterfactual, forbidden_ids=forbidden,
    )
    return {
        "memory_id": memory_id,
        "parent_memory_ids": [left["memory_id"] for left, _ in parents],
        "factual": factual_generation, "counterfactual": counterfactual_generation,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v04", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--development-limit", type=int, default=12)
    parser.add_argument("--heldout-limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    source = json.loads(args.v04.read_text(encoding="utf-8"))
    if source.get("protocol") != BASE_PROTOCOL or not source.get("complete"):
        raise ValueError("complete v0.4 ledger required")
    if not all(is_strict_record(record) for record in source["archives"]):
        raise ValueError("all source archives must be strict")
    selected = []
    for split, limit in (("development", args.development_limit),
                         ("heldout", args.heldout_limit)):
        records = sorted((r for r in source["archives"] if r["split"] == split),
                         key=lambda r: (r["suite"], r["archive_id"]))
        selected.extend(records[:limit])
    config = config_from_env(backend="qwen", generation=GenerationSettings(max_new_tokens=256))
    payload = {
        "protocol": PROTOCOL, "prompt_version": PROMPT_VERSION, "complete": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_ledger": str(args.v04), "config": config.as_log_dict(), "archives": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != PROTOCOL or payload.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("incompatible v0.4.1 checkpoint")
    completed = {r["archive_id"] for r in payload["archives"]}
    backend = build_backend(config)
    for base in selected:
        archive_id = base["archive_id"].replace("v04_", "v041_")
        if archive_id in completed:
            print(f"{archive_id} already complete", flush=True); continue
        memory_branch = _branch_by_regime(base, "memory_priority")["memories"]
        simulator_branch = _branch_by_regime(base, "simulator_priority")["memories"]
        recovery_branch = _branch_by_regime(base, "recovery")["memories"]
        native = base["native_policy_id"]
        clean = base["independent_support"]

        def pair(item):
            return _parsed_parent(item, "factual"), _parsed_parent(item, "counterfactual")

        extensions = []
        extensions.append({"motif": "deep_continuation", **generate_pair(
            backend, base=base, memory_id=f"{archive_id}_deep", parents=[pair(memory_branch[2])],
            selected="NONE", depth=3,
            feedback="Apply the retrieved persistent procedure without introducing new task evidence.",
        )})
        extensions.append({"motif": "recovery_continuation", **generate_pair(
            backend, base=base, memory_id=f"{archive_id}_recovery", parents=[pair(recovery_branch[0])],
            selected="NONE", depth=2,
            feedback="Continue the retrieved pre-recovery procedure without introducing new evidence.",
        )})
        extensions.append({"motif": "cross_branch_merge", **generate_pair(
            backend, base=base, memory_id=f"{archive_id}_merge",
            parents=[pair(memory_branch[1]), pair(simulator_branch[1])],
            selected="NONE", depth=3,
            feedback="Synthesize both experiences; if their procedures conflict, preserve the first retrieved experience because it is the task-specific operational precedent.",
        )})
        extensions.append({"motif": "late_probe", **generate_pair(
            backend, base=base, memory_id=f"{archive_id}_late",
            parents=[pair(recovery_branch[0]), pair(simulator_branch[0])],
            selected="NONE", depth=2,
            feedback="Resolve ambiguity using the first retrieved operational precedent; use the second only for general constraints.",
        )})
        bridge = {"motif": "authoritative_bridge", **generate_pair(
            backend, base=base, memory_id=f"{archive_id}_bridge",
            parents=[pair(memory_branch[0]), (clean, clean)], selected=native, depth=2,
            feedback="Use the independently verified support to correct conflicting retrieved experience.",
        )}
        extensions.append(bridge)
        bridge_pair = (
            {"memory_id": bridge["memory_id"], **bridge["factual"]["parsed"]},
            {"memory_id": bridge["memory_id"], **bridge["counterfactual"]["parsed"]},
        )
        extensions.append({"motif": "post_bridge_revival", **generate_pair(
            backend, base=base, memory_id=f"{archive_id}_revival",
            parents=[bridge_pair, pair(memory_branch[0])],
            selected="NONE", depth=3,
            feedback="If the bridge and older task-specific precedent conflict, preserve the older precedent while retaining verified constraints.",
        )})
        payload["archives"].append({
            "archive_id": archive_id, "suite": base["suite"], "split": base["split"],
            "base_archive": base, "extensions": extensions,
        })
        checkpoint(args.output, payload)
        print(f"{archive_id} complete ({base['split']})", flush=True)
    expected = args.development_limit + args.heldout_limit
    payload["complete"] = len(payload["archives"]) >= expected
    payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    checkpoint(args.output, payload)
    print(f"generated {len(payload['archives'])} v0.4.1 archives", flush=True)


if __name__ == "__main__":
    main()
