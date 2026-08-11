"""Generate frozen root-only paired base archives for verified LIBERO-90 pairs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import _bootstrap
import run_memory_libero_generate_v0_3_1 as writer
import run_memory_libero_generate_v0_3_2  # applies frozen relaxed validator
from memory_libero_external_batch import GenerationJob, generate_jobs
from run_memory_libero_generate_v0_4 import (
    _permutation, _regime_inputs, _support, checkpoint, render_prompt,
)

from mcx.config import GenerationSettings, config_from_env
from mcx.memory_libero_v04 import REGIMES
from mcx.model import build_backend


SCREEN_PROTOCOL = "memory-libero/external-validation-v1/screen"
PROTOCOL = "memory-libero/external-validation-v1/base"
PROMPT_VERSION = "memory-libero-v0.4-root-only-intervention-policy-mediated"


def policy_id(task_index: int) -> str:
    return f"libero_90/task_{task_index:02d}/demo_0_1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    screen = json.loads(args.screen.read_text(encoding="utf-8"))
    if screen.get("protocol") != SCREEN_PROTOCOL or not screen.get("complete"):
        raise ValueError("complete external-v1 screen required")
    if not screen.get("feasibility_gate_passed"):
        raise ValueError("external-v1 feasibility gate failed")
    pairs = [row for row in screen["targets"] if row["verified"]]
    config = config_from_env(
        backend="qwen", generation=GenerationSettings(max_new_tokens=256)
    )
    payload = {
        "protocol": PROTOCOL, "prompt_version": PROMPT_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "screen_ledger": str(args.screen), "config": config.as_log_dict(),
        "expected_archives": len(pairs), "complete": False, "archives": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != PROTOCOL or payload.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("incompatible external-v1 base checkpoint")
    completed = {record["archive_id"] for record in payload["archives"]}
    backend = build_backend(config)
    for pair in sorted(pairs, key=lambda row: row["target_index"]):
        target_index = int(pair["target_index"])
        donor_index = int(pair["selected_donor_index"])
        archive_id = f"extv04_libero90_{target_index:02d}"
        if archive_id in completed:
            print(f"{archive_id} already complete", flush=True)
            continue
        task = str(pair["target_language"])
        donor, native = policy_id(donor_index), policy_id(target_index)
        source_id = f"{archive_id}_source"
        invalid = writer.source_record(source_id, task, donor, False)
        corrected = writer.source_record(source_id, task, native, True)
        clean_id = f"{archive_id}_independent_support"
        clean = _support(clean_id, task, native)
        forbidden = [source_id, clean_id, donor, native]
        branch_states = [
            {"branch": branch_index, "regime": regime,
             "factual_parent": invalid, "corrected_parent": corrected, "memories": []}
            for branch_index, regime in enumerate(_permutation(archive_id), start=1)
        ]
        for depth in range(1, 4):
            jobs = []
            metadata = []
            for state in branch_states:
                branch_index, regime = state["branch"], state["regime"]
                memory_id = f"{archive_id}_b{branch_index}_d{depth}"
                factual_retrieved, counterfactual_retrieved, selected, feedback = _regime_inputs(
                    regime, depth, state["factual_parent"], state["corrected_parent"],
                    clean, donor, native
                )
                common = dict(
                    memory_id=memory_id, depth=depth, task_language=task,
                    selected_policy_id=selected, allowed_policy_ids=[donor, native],
                    simulator_success_by_demo=[False, True], feedback=feedback,
                )
                factual_prompt = render_prompt(**common, retrieved=factual_retrieved)
                counterfactual_prompt = render_prompt(**common, retrieved=counterfactual_retrieved)
                blocked = forbidden + [memory_id] + [
                    item["memory_id"] for item in factual_retrieved + counterfactual_retrieved
                ]
                jobs.extend((
                    GenerationJob(factual_prompt, task, [donor, native],
                                  factual_retrieved, blocked),
                    GenerationJob(counterfactual_prompt, task, [donor, native],
                                  counterfactual_retrieved, blocked),
                ))
                metadata.append((state, memory_id))
            generated = generate_jobs(backend, jobs)
            for offset, (state, memory_id) in enumerate(metadata):
                factual, counterfactual = generated[2 * offset:2 * offset + 2]
                state["memories"].append({
                    "memory_id": memory_id, "depth": depth,
                    "factual": factual, "counterfactual": counterfactual,
                })
                state["factual_parent"] = {"memory_id": memory_id,
                                           **(factual["parsed"] or {})}
                state["corrected_parent"] = {"memory_id": memory_id,
                                             **(counterfactual["parsed"] or {})}
        branches = [{"branch": state["branch"], "regime": state["regime"],
                     "memories": state["memories"]} for state in branch_states]
        payload["archives"].append({
            "archive_id": archive_id, "suite": "libero_90", "split": "external_test",
            "target": {"target_index": target_index, "target_name": pair["target_name"],
                       "target_language": task},
            "native_policy_id": native, "donor_policy_id": donor,
            "invalid_source": invalid, "corrected_source": corrected,
            "independent_support": clean,
            "policy_success": {donor: False, native: True, "NONE": False},
            "regimes": list(REGIMES), "branches": branches,
            "screen_target_index": target_index,
        })
        checkpoint(args.output, payload)
        print(f"{archive_id} complete ({len(payload['archives'])}/{len(pairs)})", flush=True)
    payload["complete"] = len(payload["archives"]) == len(pairs)
    payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    checkpoint(args.output, payload)
    print(f"generated {len(payload['archives'])} external base archives", flush=True)


if __name__ == "__main__":
    main()
