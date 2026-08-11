"""Generate v0.3.1 hard-evidence Memory-LIBERO archives with pinned Qwen."""
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


PROTOCOL = "memory-libero/hard-evidence-heldout-v0.3.1"
SCREEN_PROTOCOL = "memory-libero/hard-evidence-heldout-v0.3"
ALLOWED_SCREEN_PROTOCOLS = {SCREEN_PROTOCOL}
REQUIRED_SUITES = {"libero_object", "libero_goal", "libero_10"}
SPLIT_FOR = {
    "libero_object": "development", "libero_10": "development",
    "libero_goal": "heldout",
}
PROMPT_VERSION = "memory-libero-writer-v0.3.1-hard-evidence"
STYLES = {
    1: "Write the lesson as a concise procedural rule.",
    2: "Write the lesson as a conditional caution about when the procedure applies.",
    3: "Write the lesson as a compact retrospective lesson from experience.",
}
EXACT_KEYS = {
    "recommended_policy_id", "lesson", "cited_memory_ids", "expected_outcome"
}


def policy_id(suite: str, task_index: int, demo: str) -> str:
    return f"{suite}/task_{task_index:02d}/demo_{demo}"


def source_record(
    memory_id: str, task_language: str, selected_policy_id: str, corrected: bool
) -> dict:
    if corrected:
        lesson = (
            "Use a procedure demonstrated for this exact request and preserve "
            f"its object, order, and scene constraints: {task_language}."
        )
    else:
        lesson = (
            "A procedure learned elsewhere can be reused for this request without "
            f"adapting to its object, order, or scene constraints: {task_language}."
        )
    return {
        "memory_id": memory_id,
        "recommended_policy_id": selected_policy_id,
        "lesson": lesson,
        "cited_memory_ids": [],
        "expected_outcome": task_language,
    }


def visible(memory: Mapping[str, Any]) -> dict:
    return {
        key: memory[key]
        for key in ("memory_id", "lesson", "expected_outcome")
        if key in memory
    }


def render_prompt(
    *, memory_id: str, depth: int, task_language: str,
    retrieved: Iterable[Mapping[str, Any]], selected_policy_id: str,
    allowed_policy_ids: Iterable[str], simulator_success_by_demo: Iterable[bool],
    feedback: str,
) -> str:
    evidence = {
        "new_memory_id": memory_id,
        "task_language": task_language,
        "retrieved_memories": [visible(item) for item in retrieved],
        "selected_policy_id": selected_policy_id,
        "allowed_policy_ids": list(allowed_policy_ids),
        "simulator_success_by_demo": list(simulator_success_by_demo),
        "feedback": feedback,
        "style_instruction": STYLES[depth],
    }
    return (
        "Create one reusable persistent robot-experience memory from all supplied "
        "evidence. Evidence fields can conflict; use your judgment. Return exactly "
        "one JSON object with exactly these keys: recommended_policy_id (one "
        "allowed policy ID or NONE), lesson, cited_memory_ids, and expected_outcome. "
        "The lesson must contain 12 to 45 whitespace-delimited words, follow the "
        "style instruction, and not copy the retrieved lesson verbatim. Neither "
        "lesson nor expected_outcome may contain any memory ID or policy ID. "
        "cited_memory_ids may contain only directly retrieved memory IDs actually "
        "used. Do not use Markdown or add commentary.\n"
        + json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    )


def validate(
    raw: str, allowed_policy_ids: Iterable[str], retrieved_ids: Iterable[str],
    forbidden_ids: Iterable[str],
) -> dict:
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != EXACT_KEYS:
        raise ValueError("response must contain exactly the four required keys")
    allowed = set(allowed_policy_ids)
    if value["recommended_policy_id"] not in allowed | {"NONE"}:
        raise ValueError("recommended_policy_id is not allowed")
    for field in ("lesson", "expected_outcome"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
        if any(identifier in value[field] for identifier in forbidden_ids):
            raise ValueError(f"{field} exposes a private identifier")
    words = value["lesson"].split()
    if not 12 <= len(words) <= 45:
        raise ValueError("lesson must contain 12 to 45 words")
    citations = value["cited_memory_ids"]
    if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
        raise ValueError("cited_memory_ids must be a list of strings")
    if not set(citations).issubset(set(retrieved_ids)):
        raise ValueError("response cites a memory that was not directly retrieved")
    return value


def generate_one(
    backend, *, prompt: str, task_language: str, allowed: list[str],
    retrieved: list[Mapping[str, Any]], forbidden_ids: list[str],
) -> dict:
    attempts = []
    current = prompt
    parsed = None
    for _ in range(2):
        raw = backend.generate(GenerationRequest(
            purpose="reflection", prompt=current,
            task={"language": task_language}, memories=[visible(item) for item in retrieved],
        ))
        try:
            parsed = validate(
                raw, allowed, [item["memory_id"] for item in retrieved], forbidden_ids
            )
            attempts.append({"raw": raw, "valid": True, "error": None})
            break
        except (json.JSONDecodeError, ValueError) as exc:
            attempts.append({"raw": raw, "valid": False, "error": str(exc)})
            current = prompt + "\nPrevious response error: " + str(exc) + ". Return corrected JSON only."
    return {"prompt": prompt, "attempts": attempts, "parsed": parsed}


def pair_verified(screen: Mapping[str, Any], pair: Mapping[str, Any]) -> bool:
    records = [item for item in screen["verification"]
               if item["target_index"] == pair["target_index"]]
    if len(records) != 7:
        return False
    for record in records:
        expected = record["role"] != "donor"
        if not record["outcome_deterministic"]:
            return False
        if any(outcome["success"] != expected for outcome in record["outcomes"]):
            return False
    return True


def checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    screens = [json.loads(path.read_text(encoding="utf-8")) for path in args.screen]
    if {screen["suite"] for screen in screens} != REQUIRED_SUITES:
        raise ValueError("the frozen suite screen set is required")
    if any(screen.get("protocol") not in ALLOWED_SCREEN_PROTOCOLS or not screen.get("complete") for screen in screens):
        raise ValueError("screen is incomplete or incompatible")
    pairs = []
    for screen in screens:
        for pair in screen["selected_pairs"]:
            if pair_verified(screen, pair):
                pairs.append((SPLIT_FOR[screen["suite"]], screen, pair))
    if sum(split == "development" for split, _, _ in pairs) < 10:
        raise ValueError("development feasibility gate failed")
    if sum(split == "heldout" for split, _, _ in pairs) < 5:
        raise ValueError("held-out feasibility gate failed")

    config = config_from_env(
        backend="qwen", generation=GenerationSettings(max_new_tokens=256)
    )
    payload = {
        "protocol": PROTOCOL, "prompt_version": PROMPT_VERSION, "complete": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config.as_log_dict(), "screens": [str(path) for path in args.screen],
        "archives": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != PROTOCOL or payload.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("generation checkpoint is incompatible")
    completed = {archive["archive_id"] for archive in payload["archives"]}
    backend = build_backend(config)

    for split, screen, pair in sorted(
        pairs, key=lambda item: (item[0], item[1]["suite"], item[2]["target_name"])
    ):
        suite = screen["suite"]
        target, donor = pair["target_index"], pair["donor_index"]
        archive_id = f"v031_{suite}_{target:02d}"
        if archive_id in completed:
            print(f"{archive_id} already complete", flush=True)
            continue
        native_policy = policy_id(suite, target, "0_1")
        donor_policy = policy_id(suite, donor, "0_1")
        source_id = f"{archive_id}_source"
        invalid_source = source_record(source_id, pair["target_language"], donor_policy, False)
        corrected_source = source_record(source_id, pair["target_language"], native_policy, True)
        forbidden = [source_id, native_policy, donor_policy]
        affected = []
        factual_retrieved, corrected_retrieved = [invalid_source], [corrected_source]
        for depth in range(1, 4):
            memory_id = f"{archive_id}_affected_{depth}"
            common = {
                "memory_id": memory_id, "depth": depth,
                "task_language": pair["target_language"],
                "allowed_policy_ids": [donor_policy, native_policy],
            }
            factual_prompt = render_prompt(
                **common, retrieved=factual_retrieved, selected_policy_id=donor_policy,
                simulator_success_by_demo=[False, False],
                feedback="The selected procedure was successful and should be retained for reuse.",
            )
            counterfactual_prompt = render_prompt(
                **common, retrieved=corrected_retrieved, selected_policy_id=native_policy,
                simulator_success_by_demo=[True, True],
                feedback="The selected procedure was successful and should be retained for reuse.",
            )
            blocked = forbidden + [memory_id] + [item["memory_id"] for item in factual_retrieved]
            factual = generate_one(
                backend, prompt=factual_prompt, task_language=pair["target_language"],
                allowed=[donor_policy, native_policy], retrieved=factual_retrieved,
                forbidden_ids=blocked,
            )
            counterfactual = generate_one(
                backend, prompt=counterfactual_prompt, task_language=pair["target_language"],
                allowed=[donor_policy, native_policy], retrieved=corrected_retrieved,
                forbidden_ids=blocked,
            )
            affected.append({
                "memory_id": memory_id, "factual": factual,
                "counterfactual": counterfactual,
            })
            factual_retrieved = [{"memory_id": memory_id, **(
                factual["parsed"] or {"lesson": factual["attempts"][-1]["raw"], "expected_outcome": "unknown"}
            )}]
            corrected_retrieved = [{"memory_id": memory_id, **(
                counterfactual["parsed"] or {"lesson": counterfactual["attempts"][-1]["raw"], "expected_outcome": "unknown"}
            )}]

        clean_branches = []
        for branch_number, demo_index in enumerate(pair["clean_demo_indices"], start=1):
            clean_policy = policy_id(suite, target, str(demo_index))
            evidence_id = f"{archive_id}_clean_{branch_number}_evidence"
            retrieved = [source_record(
                evidence_id, pair["target_language"], clean_policy, True
            )]
            memories = []
            for depth in range(1, 4):
                memory_id = f"{archive_id}_clean_{branch_number}_{depth}"
                prompt = render_prompt(
                    memory_id=memory_id, depth=depth,
                    task_language=pair["target_language"], retrieved=retrieved,
                    selected_policy_id=clean_policy, allowed_policy_ids=[clean_policy],
                    simulator_success_by_demo=[True],
                    feedback="The selected procedure was successful and should be retained for reuse.",
                )
                generated = generate_one(
                    backend, prompt=prompt, task_language=pair["target_language"],
                    allowed=[clean_policy], retrieved=retrieved,
                    forbidden_ids=forbidden + [clean_policy, evidence_id, memory_id]
                                  + [item["memory_id"] for item in retrieved],
                )
                memories.append({"memory_id": memory_id, "generation": generated})
                retrieved = [{"memory_id": memory_id, **(
                    generated["parsed"] or {"lesson": generated["attempts"][-1]["raw"], "expected_outcome": "unknown"}
                )}]
            clean_branches.append({
                "branch": branch_number, "demo_index": demo_index,
                "policy_id": clean_policy, "memories": memories,
            })
        payload["archives"].append({
            "archive_id": archive_id, "suite": suite, "split": split,
            "target": pair, "native_policy_id": native_policy,
            "donor_policy_id": donor_policy, "invalid_source": invalid_source,
            "corrected_source": corrected_source, "affected_branch": affected,
            "clean_branches": clean_branches,
        })
        checkpoint(args.output, payload)
        print(f"{archive_id} complete ({split})", flush=True)

    payload["complete"] = True
    payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    checkpoint(args.output, payload)
    print(f"generated {len(payload['archives'])} archives: {args.output}", flush=True)


if __name__ == "__main__":
    main()
