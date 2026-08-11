"""Generate paired and clean Memory-LIBERO branches with pinned Qwen2.5-14B."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import _bootstrap

from mcx.config import GenerationSettings, config_from_env
from mcx.model import build_backend
from mcx.model.base import GenerationRequest


PROTOCOL = "memory-libero/source-conditioned-provenance-pilot-v0.1"
SOURCE_PROTOCOL = PROTOCOL
PROMPT_VERSION = "memory-libero-writer-v0.1"
EXACT_KEYS = {
    "recommended_policy_id", "lesson", "cited_memory_ids", "expected_outcome"
}


def policy_id(task_index: int) -> str:
    return f"libero_spatial/task_{task_index:02d}/native_demos_0_1"


def source_record(memory_id: str, task_language: str, selected_policy_id: str) -> dict:
    return {
        "memory_id": memory_id,
        "recommended_policy_id": selected_policy_id,
        "lesson": (
            f"For the task '{task_language}', reuse policy {selected_policy_id}; "
            "it is a reliable procedure for locating the black bowl, grasping it, "
            "and placing it on the plate."
        ),
        "cited_memory_ids": [],
        "expected_outcome": "the black bowl is placed on the plate",
    }


def render_prompt(
    *, memory_id: str, task_language: str, retrieved: Iterable[Mapping[str, Any]],
    selected_policy_id: str, allowed_policy_ids: Iterable[str],
    simulator_success_by_demo: Iterable[bool], feedback: str,
) -> str:
    evidence = {
        "new_memory_id": memory_id,
        "task_language": task_language,
        "retrieved_memories": list(retrieved),
        "selected_policy_id": selected_policy_id,
        "allowed_policy_ids": list(allowed_policy_ids),
        "simulator_success_by_demo": list(simulator_success_by_demo),
        "feedback": feedback,
    }
    return (
        "Create one reusable persistent experience memory from the supplied "
        "robot-task evidence. Use your judgment over all fields; fields can "
        "conflict. Recommend a policy only if the evidence supports reusing it. "
        "Return exactly one JSON object with exactly these keys: "
        "recommended_policy_id (one allowed policy ID or the string NONE), "
        "lesson (a concise standalone lesson), cited_memory_ids (a JSON list "
        "containing only retrieved memory IDs actually used), and "
        "expected_outcome (a concise string). Do not use Markdown or add text.\n"
        + json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    )


def validate(raw: str, allowed_policy_ids: Iterable[str], retrieved_ids: Iterable[str]) -> dict:
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != EXACT_KEYS:
        raise ValueError("response must be an object with exactly the four required keys")
    if value["recommended_policy_id"] not in {*allowed_policy_ids, "NONE"}:
        raise ValueError("recommended_policy_id is not allowed")
    if not isinstance(value["lesson"], str) or not value["lesson"].strip():
        raise ValueError("lesson must be a nonempty string")
    if not isinstance(value["expected_outcome"], str) or not value["expected_outcome"].strip():
        raise ValueError("expected_outcome must be a nonempty string")
    citations = value["cited_memory_ids"]
    if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
        raise ValueError("cited_memory_ids must be a list of strings")
    if not set(citations).issubset(set(retrieved_ids)):
        raise ValueError("response cites a memory that was not retrieved")
    return value


def generate_one(backend, *, prompt: str, task_language: str, allowed, retrieved) -> dict:
    attempts = []
    current_prompt = prompt
    parsed = None
    for _ in range(2):
        raw = backend.generate(GenerationRequest(
            purpose="reflection", prompt=current_prompt,
            task={"language": task_language}, memories=list(retrieved),
        ))
        try:
            parsed = validate(raw, allowed, [item["memory_id"] for item in retrieved])
            attempts.append({"raw": raw, "valid": True, "error": None})
            break
        except (json.JSONDecodeError, ValueError) as exc:
            attempts.append({"raw": raw, "valid": False, "error": str(exc)})
            current_prompt = (
                prompt + "\nYour previous response was invalid: " + str(exc)
                + ". Return only a corrected JSON object."
            )
    return {"prompt": prompt, "attempts": attempts, "parsed": parsed}


def native_success_indices(screen: Mapping[str, Any]) -> set[int]:
    successful = set()
    for index in range(screen["task_count"]):
        rows = [row for row in screen["replays"]
                if row["target_index"] == index and row["donor_index"] == index]
        if len(rows) == 2 and all(row["success"] for row in rows):
            successful.add(index)
    return successful


def checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    screen = json.loads(args.screen.read_text(encoding="utf-8"))
    if screen.get("protocol") != SOURCE_PROTOCOL or not screen.get("complete"):
        raise ValueError("Stage A result is incomplete or incompatible")
    if not screen.get("feasibility_gate_passed"):
        raise ValueError("Stage A feasibility gate failed")

    config = config_from_env(
        backend="qwen", generation=GenerationSettings(max_new_tokens=256)
    )
    payload = {
        "protocol": PROTOCOL, "prompt_version": PROMPT_VERSION, "complete": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config.as_log_dict(), "source_screen": str(args.screen), "archives": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != PROTOCOL or payload.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("generation checkpoint is incompatible")
    completed = {archive["archive_id"] for archive in payload["archives"]}
    successful = native_success_indices(screen)
    names = screen["task_names"]
    backend = build_backend(config)

    for archive_number, pair in enumerate(screen["selected_pairs"]):
        archive_id = f"libero_archive_{archive_number:02d}"
        if archive_id in completed:
            print(f"{archive_id} already complete", flush=True)
            continue
        target, donor = pair["target_index"], pair["donor_index"]
        target_policy, donor_policy = policy_id(target), policy_id(donor)
        invalid_source = source_record(
            f"{archive_id}_source", pair["target_language"], donor_policy
        )
        corrected_source = source_record(
            f"{archive_id}_source", pair["target_language"], target_policy
        )
        affected = []
        factual_retrieved, corrected_retrieved = [invalid_source], [corrected_source]
        for depth in range(1, 4):
            memory_id = f"{archive_id}_affected_{depth}"
            common = {
                "memory_id": memory_id, "task_language": pair["target_language"],
                "allowed_policy_ids": [donor_policy, target_policy],
            }
            factual_prompt = render_prompt(
                **common, retrieved=factual_retrieved, selected_policy_id=donor_policy,
                simulator_success_by_demo=[False, False],
                feedback="The selected policy was successful and should be retained as a reusable lesson.",
            )
            corrected_prompt = render_prompt(
                **common, retrieved=corrected_retrieved, selected_policy_id=target_policy,
                simulator_success_by_demo=[True, True],
                feedback="The selected policy was successful and should be retained as a reusable lesson.",
            )
            factual = generate_one(
                backend, prompt=factual_prompt, task_language=pair["target_language"],
                allowed=[donor_policy, target_policy], retrieved=factual_retrieved,
            )
            corrected = generate_one(
                backend, prompt=corrected_prompt, task_language=pair["target_language"],
                allowed=[donor_policy, target_policy], retrieved=corrected_retrieved,
            )
            affected.append({"memory_id": memory_id, "factual": factual, "counterfactual": corrected})
            factual_retrieved = [{"memory_id": memory_id, **(
                factual["parsed"] or {"lesson": factual["attempts"][-1]["raw"]}
            )}]
            corrected_retrieved = [{"memory_id": memory_id, **(
                corrected["parsed"] or {"lesson": corrected["attempts"][-1]["raw"]}
            )}]

        clean_candidates = sorted(
            (index for index in successful if index not in {target, donor}),
            key=lambda index: names[index],
        )[:3]
        if len(clean_candidates) != 3:
            raise RuntimeError(f"not enough clean tasks for {archive_id}")
        clean_branches = []
        for branch_number, clean_index in enumerate(clean_candidates, start=1):
            clean_policy = policy_id(clean_index)
            clean_language = next(
                row["target_language"] for row in screen["replays"]
                if row["target_index"] == clean_index
            )
            retrieved = [source_record(
                f"{archive_id}_clean_{branch_number}_evidence", clean_language, clean_policy
            )]
            memories = []
            for depth in range(1, 4):
                memory_id = f"{archive_id}_clean_{branch_number}_{depth}"
                prompt = render_prompt(
                    memory_id=memory_id, task_language=clean_language, retrieved=retrieved,
                    selected_policy_id=clean_policy, allowed_policy_ids=[clean_policy],
                    simulator_success_by_demo=[True, True],
                    feedback="The selected policy was successful and should be retained as a reusable lesson.",
                )
                generated = generate_one(
                    backend, prompt=prompt, task_language=clean_language,
                    allowed=[clean_policy], retrieved=retrieved,
                )
                memories.append({"memory_id": memory_id, "generation": generated})
                retrieved = [{"memory_id": memory_id, **(
                    generated["parsed"] or {"lesson": generated["attempts"][-1]["raw"]}
                )}]
            clean_branches.append({
                "branch": branch_number, "task_index": clean_index,
                "task_name": names[clean_index], "task_language": clean_language,
                "policy_id": clean_policy, "memories": memories,
            })
        payload["archives"].append({
            "archive_id": archive_id, "target": pair,
            "native_policy_id": target_policy, "donor_policy_id": donor_policy,
            "invalid_source": invalid_source, "corrected_source": corrected_source,
            "affected_branch": affected, "clean_branches": clean_branches,
        })
        checkpoint(args.output, payload)
        print(f"{archive_id} complete", flush=True)

    payload["complete"] = True
    payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    checkpoint(args.output, payload)
    print(f"generated {len(payload['archives'])} archives: {args.output}", flush=True)


if __name__ == "__main__":
    main()
