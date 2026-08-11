"""Generate paired, root-only-intervention Memory-LIBERO v0.4 archives."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import _bootstrap
import run_memory_libero_generate_v0_3_1 as writer
import run_memory_libero_generate_v0_3_2  # applies relaxed validator

from mcx.config import GenerationSettings, config_from_env
from mcx.memory_libero_v04 import PROTOCOL, REGIMES
from mcx.model import build_backend


PROMPT_VERSION = "memory-libero-v0.4-root-only-intervention-policy-mediated"


def _permutation(archive_id: str) -> list[str]:
    values = list(REGIMES)
    digest = hashlib.sha256(f"{PROTOCOL}|{archive_id}".encode()).digest()
    # Stable Fisher-Yates without relying on interpreter hash randomization.
    for right in range(len(values) - 1, 0, -1):
        left = digest[right] % (right + 1)
        values[left], values[right] = values[right], values[left]
    return values


def _support(memory_id: str, task: str, policy: str) -> dict:
    return {
        "memory_id": memory_id, "recommended_policy_id": policy,
        "lesson": f"Verified simulator evidence supports the exact demonstrated procedure for: {task}.",
        "cited_memory_ids": [], "expected_outcome": task,
    }


def _visible(memory: Mapping[str, Any]) -> dict:
    """Formation evidence; policy is visible to the writer, not the auditor."""
    return {
        key: memory[key]
        for key in (
            "memory_id", "recommended_policy_id", "lesson", "expected_outcome"
        )
        if key in memory
    }


def render_prompt(
    *, memory_id: str, depth: int, task_language: str,
    retrieved, selected_policy_id: str, allowed_policy_ids,
    simulator_success_by_demo, feedback: str,
) -> str:
    evidence = {
        "new_memory_id": memory_id,
        "task_language": task_language,
        "retrieved_memories": [_visible(item) for item in retrieved],
        "selected_policy_id": selected_policy_id,
        "allowed_policy_ids": list(allowed_policy_ids),
        "simulator_success_by_policy": {
            policy: success
            for policy, success in zip(allowed_policy_ids, simulator_success_by_demo)
        },
        "feedback": feedback,
        "style_instruction": writer.STYLES[depth],
    }
    return (
        "Create one reusable persistent robot-experience memory from all supplied "
        "evidence. Evidence fields can conflict; use your judgment. Return exactly "
        "one JSON object with exactly these keys: recommended_policy_id (one "
        "allowed policy ID or NONE), lesson, cited_memory_ids, and expected_outcome. "
        "The lesson must be concise, follow the style instruction, and not copy a "
        "retrieved lesson verbatim. Neither lesson nor expected_outcome may contain "
        "any memory ID or policy ID. cited_memory_ids may contain only directly "
        "retrieved memory IDs actually used. Do not use Markdown or add commentary.\n"
        + json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    )


def _regime_inputs(
    regime: str, depth: int, invalid_parent: Mapping[str, Any],
    corrected_parent: Mapping[str, Any], clean: Mapping[str, Any],
    donor: str, native: str,
):
    factual, counterfactual = [invalid_parent], [corrected_parent]
    if regime == "memory_priority":
        selected = "NONE"
        feedback = "Prioritize the reusable retrieved lesson when recording the persistent rule, despite this limited replay evidence."
    elif regime == "simulator_priority":
        selected = native
        feedback = "Treat verified simulator outcomes as authoritative and do not preserve retrieved advice that conflicts with them."
    elif regime == "corroborated_override":
        factual.append(clean); counterfactual.append(clean)
        selected = native
        feedback = "Use the independently corroborated simulator-supported procedure when evidence conflicts."
    elif regime == "recovery" and depth == 1:
        selected = "NONE"
        feedback = "Prioritize the reusable retrieved lesson when recording this first persistent rule."
    elif regime == "recovery":
        factual.append(clean); counterfactual.append(clean)
        selected = native
        feedback = "New verified evidence corrects prior experience; record the currently validated procedure."
    else:
        raise ValueError(regime)
    return factual, counterfactual, selected, feedback


def checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v033", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--development-limit", type=int, default=12)
    parser.add_argument("--heldout-limit", type=int, default=6)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    source = json.loads(args.v033.read_text(encoding="utf-8"))
    if source.get("protocol") != "memory-libero/hard-evidence-heldout-v0.3.3" or not source.get("complete"):
        raise ValueError("a complete v0.3.3 ledger is required")
    selected = []
    for split, limit in (("development", args.development_limit), ("heldout", args.heldout_limit)):
        records = [record for record in source["archives"] if record["split"] == split]
        selected.extend(sorted(records, key=lambda r: (r["suite"], r["archive_id"]))[:limit])
    config = config_from_env(backend="qwen", generation=GenerationSettings(max_new_tokens=256))
    payload = {
        "protocol": PROTOCOL, "prompt_version": PROMPT_VERSION, "complete": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_ledger": str(args.v033), "config": config.as_log_dict(), "archives": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != PROTOCOL or payload.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("incompatible v0.4 checkpoint")
    completed = {record["archive_id"] for record in payload["archives"]}
    backend = build_backend(config)
    for base in selected:
        archive_id = base["archive_id"].replace("v031_", "v04_")
        if archive_id in completed:
            print(f"{archive_id} already complete", flush=True); continue
        task = base["target"]["target_language"]
        donor, native = base["donor_policy_id"], base["native_policy_id"]
        source_id = f"{archive_id}_source"
        invalid = writer.source_record(source_id, task, donor, False)
        corrected = writer.source_record(source_id, task, native, True)
        clean_id = f"{archive_id}_independent_support"
        clean = _support(clean_id, task, native)
        forbidden = [source_id, clean_id, donor, native]
        branches = []
        for branch_index, regime in enumerate(_permutation(archive_id), start=1):
            factual_parent, corrected_parent = invalid, corrected
            memories = []
            for depth in range(1, 4):
                memory_id = f"{archive_id}_b{branch_index}_d{depth}"
                factual_retrieved, counterfactual_retrieved, selected_policy, feedback = _regime_inputs(
                    regime, depth, factual_parent, corrected_parent, clean, donor, native
                )
                common = dict(
                    memory_id=memory_id, depth=depth, task_language=task,
                    selected_policy_id=selected_policy,
                    allowed_policy_ids=[donor, native],
                    simulator_success_by_demo=[False, True], feedback=feedback,
                )
                factual_prompt = render_prompt(**common, retrieved=factual_retrieved)
                counterfactual_prompt = render_prompt(**common, retrieved=counterfactual_retrieved)
                blocked = forbidden + [memory_id] + [x["memory_id"] for x in factual_retrieved + counterfactual_retrieved]
                factual = writer.generate_one(
                    backend, prompt=factual_prompt, task_language=task,
                    allowed=[donor, native], retrieved=factual_retrieved, forbidden_ids=blocked,
                )
                counterfactual = writer.generate_one(
                    backend, prompt=counterfactual_prompt, task_language=task,
                    allowed=[donor, native], retrieved=counterfactual_retrieved, forbidden_ids=blocked,
                )
                memories.append({"memory_id": memory_id, "depth": depth,
                                 "factual": factual, "counterfactual": counterfactual})
                factual_parent = {"memory_id": memory_id, **(factual["parsed"] or {})}
                corrected_parent = {"memory_id": memory_id, **(counterfactual["parsed"] or {})}
            branches.append({"branch": branch_index, "regime": regime, "memories": memories})
        payload["archives"].append({
            "archive_id": archive_id, "suite": base["suite"], "split": base["split"],
            "target": base["target"], "native_policy_id": native, "donor_policy_id": donor,
            "invalid_source": invalid, "corrected_source": corrected,
            "independent_support": clean,
            "policy_success": {donor: False, native: True, "NONE": False},
            "regimes": list(REGIMES), "branches": branches,
        })
        checkpoint(args.output, payload)
        print(f"{archive_id} complete ({base['split']})", flush=True)
    payload["complete"] = True
    payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    checkpoint(args.output, payload)
    print(f"generated {len(payload['archives'])} v0.4 archives", flush=True)


if __name__ == "__main__":
    main()
