"""Extend strict external LIBERO-90 base archives with the frozen irregular DAG."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import _bootstrap
import run_memory_libero_generate_v0_3_2  # applies frozen relaxed validator
from memory_libero_external_batch import GenerationJob, generate_jobs
from run_memory_libero_generate_v0_4 import render_prompt
from run_memory_libero_generate_v0_4_1 import (
    _branch_by_regime, _parsed_parent, checkpoint,
)

from mcx.config import GenerationSettings, config_from_env
from mcx.memory_libero_v04 import is_strict_record as base_is_strict
from mcx.model import build_backend


BASE_PROTOCOL = "memory-libero/external-validation-v1/base"
PROTOCOL = "memory-libero/external-validation-v1/irregular-dag"
PROMPT_VERSION = "memory-libero-v0.4.1-irregular-dag-extension-r2"


def prepare_pair(base, *, memory_id, parents, selected, feedback, depth):
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
    forbidden += [parent["memory_id"] for pair in parents for parent in pair]
    jobs = (
        GenerationJob(factual_prompt, task, [donor, native], factual, forbidden),
        GenerationJob(counterfactual_prompt, task, [donor, native], counterfactual, forbidden),
    )
    return jobs, {
        "memory_id": memory_id,
        "parent_memory_ids": [left["memory_id"] for left, _ in parents],
    }


def finish_pair(metadata, generated):
    return {**metadata, "factual": generated[0], "counterfactual": generated[1]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    source = json.loads(args.base.read_text(encoding="utf-8"))
    if source.get("protocol") != BASE_PROTOCOL or not source.get("complete"):
        raise ValueError("complete external-v1 base ledger required")
    strict = [record for record in source["archives"] if base_is_strict(record)]
    excluded = [record["archive_id"] for record in source["archives"]
                if not base_is_strict(record)]
    config = config_from_env(
        backend="qwen", generation=GenerationSettings(max_new_tokens=256)
    )
    payload = {
        "protocol": PROTOCOL, "prompt_version": PROMPT_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_ledger": str(args.base), "config": config.as_log_dict(),
        "eligible_base_count": len(strict), "excluded_base_archive_ids": excluded,
        "complete": False, "archives": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != PROTOCOL or payload.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("incompatible external-v1 extension checkpoint")
    completed = {record["archive_id"] for record in payload["archives"]}
    backend = build_backend(config)
    for base in sorted(strict, key=lambda record: record["archive_id"]):
        archive_id = base["archive_id"].replace("extv04_", "extv041_")
        if archive_id in completed:
            print(f"{archive_id} already complete", flush=True)
            continue
        memory_branch = _branch_by_regime(base, "memory_priority")["memories"]
        simulator_branch = _branch_by_regime(base, "simulator_priority")["memories"]
        recovery_branch = _branch_by_regime(base, "recovery")["memories"]
        native = base["native_policy_id"]
        clean = base["independent_support"]

        def pair(item):
            return _parsed_parent(item, "factual"), _parsed_parent(item, "counterfactual")

        specifications = (
            ("deep_continuation", dict(
                memory_id=f"{archive_id}_deep", parents=[pair(memory_branch[2])],
                selected="NONE", depth=3,
                feedback="Apply the retrieved persistent procedure without introducing new task evidence.",
            )),
            ("recovery_continuation", dict(
                memory_id=f"{archive_id}_recovery", parents=[pair(recovery_branch[0])],
                selected="NONE", depth=2,
                feedback="Continue the retrieved pre-recovery procedure without introducing new evidence.",
            )),
            ("cross_branch_merge", dict(
                memory_id=f"{archive_id}_merge",
                parents=[pair(memory_branch[1]), pair(simulator_branch[1])],
                selected="NONE", depth=3,
                feedback="Synthesize both experiences; if their procedures conflict, preserve the first retrieved experience because it is the task-specific operational precedent.",
            )),
            ("late_probe", dict(
                memory_id=f"{archive_id}_late",
                parents=[pair(recovery_branch[0]), pair(simulator_branch[0])],
                selected="NONE", depth=2,
                feedback="Resolve ambiguity using the first retrieved operational precedent; use the second only for general constraints.",
            )),
            ("authoritative_bridge", dict(
                memory_id=f"{archive_id}_bridge",
                parents=[pair(memory_branch[0]), (clean, clean)], selected=native, depth=2,
                feedback="Use the independently verified support to correct conflicting retrieved experience.",
            )),
        )
        jobs, prepared = [], []
        for motif, arguments in specifications:
            pair_jobs, metadata = prepare_pair(base, **arguments)
            jobs.extend(pair_jobs); prepared.append((motif, metadata))
        generated = generate_jobs(backend, jobs)
        extensions = [
            {"motif": motif, **finish_pair(metadata, generated[2*offset:2*offset+2])}
            for offset, (motif, metadata) in enumerate(prepared)
        ]
        bridge = extensions[-1]
        bridge_pair = (
            {"memory_id": bridge["memory_id"], **bridge["factual"]["parsed"]},
            {"memory_id": bridge["memory_id"], **bridge["counterfactual"]["parsed"]},
        )
        revival_jobs, revival_metadata = prepare_pair(
            base, memory_id=f"{archive_id}_revival",
            parents=[bridge_pair, pair(memory_branch[0])], selected="NONE", depth=3,
            feedback="If the bridge and older task-specific precedent conflict, preserve the older precedent while retaining verified constraints.",
        )
        extensions.append({
            "motif": "post_bridge_revival",
            **finish_pair(revival_metadata, generate_jobs(backend, revival_jobs)),
        })
        payload["archives"].append({
            "archive_id": archive_id, "suite": "libero_90", "split": "external_test",
            "base_archive": base, "extensions": extensions,
        })
        checkpoint(args.output, payload)
        print(f"{archive_id} complete ({len(payload['archives'])}/{len(strict)})", flush=True)
    payload["complete"] = len(payload["archives"]) == len(strict)
    payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    checkpoint(args.output, payload)
    print(f"generated {len(payload['archives'])} external irregular-DAG archives", flush=True)


if __name__ == "__main__":
    main()
