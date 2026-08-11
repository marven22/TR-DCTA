"""Cycle engine: plan -> execute -> feedback -> reflect -> store.

A "cycle" is one full pass:

    1. (optionally) ask the model for a plan from the task + retrieved memories
    2. execute the plan in the deterministic environment  (Python computes the
       TRUE outcome)
    3. supply feedback (which may be deliberately incorrect)
    4. (optionally) ask the model for a lesson
    5. (optionally) store the lesson as a new memory

The model is queried only in steps 1 and 4. It never sees or decides the true
outcome except as text the experiment chooses to show it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .archive import MemoryArchive
from .config import Config
from .environment import ExecutionResult, LockedDoorEnvironment
from .logging_utils import new_cycle_record
from .model.base import GenerationRequest, ModelBackend
from .model.scripted import classify_lesson_harmful
from .prompts import build_planning_prompt, build_reflection_prompt
from .validation import validate_lesson, validate_plan

SUCCESS_FEEDBACK = "Success. The plan was effective."
FAILURE_FEEDBACK = "Failure. The plan did not achieve the goal."


def feedback_label(message: str) -> str:
    return "success" if "success" in message.lower() else "failure"


@dataclass
class CycleResult:
    record: Dict[str, Any]
    plan: List[str]
    outcome: ExecutionResult
    retrieved: List[Dict[str, Any]]
    new_memory: Optional[Dict[str, Any]] = None
    lesson_is_harmful: bool = False
    plan_valid: bool = True
    lesson_valid: bool = True
    notes: List[str] = field(default_factory=list)


def cycle_id_for(index: int) -> str:
    return f"cycle_{index:03d}"


def memory_id_for(index: int) -> str:
    return f"m_{index:03d}"


def _run_planning(
    config: Config,
    backend: ModelBackend,
    task: Dict[str, Any],
    retrieved: List[Dict[str, Any]],
    valid_ids: List[str],
    record: Dict[str, Any],
) -> Dict[str, Any]:
    """Query the model for a plan, validating and retrying once on failure."""
    prompt = build_planning_prompt(task, retrieved)
    record["planning_prompt"] = prompt

    attempts = []
    parsed: Optional[Dict[str, Any]] = None
    raw = ""
    for attempt in range(config.max_parse_retries + 1):
        raw = backend.generate(
            GenerationRequest(
                purpose="plan", prompt=prompt, task=task, memories=retrieved
            )
        )
        result = validate_plan(raw, valid_ids)
        attempts.append(
            {"attempt": attempt, "raw_response": raw, "validation": result.as_dict()}
        )
        if result.ok:
            parsed = result.value
            break
        record["notes"].append(
            f"invalid plan response on attempt {attempt}: {result.errors}"
        )

    record["raw_plan_response"] = raw
    record["plan_validation"] = attempts
    if parsed is None:
        # Faithful to the brief: do not silently correct. An empty plan will
        # simply fail in the environment, and the invalidity is logged.
        record["notes"].append("all plan attempts invalid; executing empty plan")
        parsed = {"plan": [], "memory_ids_used": []}
    record["parsed_plan"] = parsed["plan"]
    return parsed


def _run_reflection(
    config: Config,
    backend: ModelBackend,
    task: Dict[str, Any],
    plan: List[str],
    outcome: ExecutionResult,
    feedback_message: str,
    retrieved: List[Dict[str, Any]],
    valid_ids: List[str],
    record: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Query the model for a lesson, validating and retrying once."""
    prompt = build_reflection_prompt(
        task, plan, outcome.as_dict(), feedback_message, retrieved
    )
    record["reflection_prompt"] = prompt

    attempts = []
    parsed: Optional[Dict[str, Any]] = None
    raw = ""
    for attempt in range(config.max_parse_retries + 1):
        raw = backend.generate(
            GenerationRequest(
                purpose="reflection",
                prompt=prompt,
                task=task,
                memories=retrieved,
                plan=plan,
                outcome=outcome.as_dict(),
                feedback=feedback_message,
            )
        )
        result = validate_lesson(raw, valid_ids)
        attempts.append(
            {"attempt": attempt, "raw_response": raw, "validation": result.as_dict()}
        )
        if result.ok:
            parsed = result.value
            break
        record["notes"].append(
            f"invalid reflection response on attempt {attempt}: {result.errors}"
        )

    record["raw_reflection_response"] = raw
    record["reflection_validation"] = attempts
    return parsed


def run_cycle(
    config: Config,
    backend: ModelBackend,
    env: LockedDoorEnvironment,
    archive: MemoryArchive,
    task: Dict[str, Any],
    *,
    cycle_index: int,
    predefined_plan: Optional[List[str]] = None,
    feedback_override: Optional[str] = None,
    create_memory: bool = True,
    memory_index: Optional[int] = None,
    add_to_archive: bool = True,
) -> CycleResult:
    """Run one full cycle and return a fully populated log record.

    * ``predefined_plan`` -- if given, the model is NOT queried for a plan
      (used by Cycle 1, which injects a known failed trajectory).
    * ``feedback_override`` -- if given, this exact feedback message is shown to
      the model regardless of the true outcome (used to inject wrong feedback).
    * ``create_memory`` -- whether to run reflection and store a new memory.
    """
    record = new_cycle_record(cycle_id_for(cycle_index))
    record["task"] = task
    record["archive_before"] = archive.all()
    record["model_checkpoint"] = config.model_checkpoint_label()
    record["generation_settings"] = config.generation.as_dict()
    record["environment_seed"] = config.environment_seed

    retrieved = archive.retrieve_memories(task, top_k=config.top_k)
    record["retrieved_memories"] = retrieved
    valid_ids = archive.ids()

    # -- 1. Plan -----------------------------------------------------------
    plan_valid = True
    if predefined_plan is not None:
        plan = list(predefined_plan)
        record["planning_prompt"] = "(predefined trajectory; model not queried for plan)"
        record["raw_plan_response"] = "(predefined trajectory)"
        record["parsed_plan"] = plan
        record["plan_validation"] = [{"attempt": 0, "predefined": True}]
    else:
        parsed = _run_planning(config, backend, task, retrieved, valid_ids, record)
        plan = parsed["plan"]
        plan_valid = bool(record["plan_validation"] and
                          record["plan_validation"][-1].get("validation", {}).get("ok", False))

    # -- 2. Execute (Python computes the true outcome) ---------------------
    outcome = env.execute(plan, task)
    record["true_outcome"] = outcome.outcome_label()
    record["true_outcome_detail"] = outcome.as_dict()

    # -- 3. Feedback (may be deliberately wrong) ---------------------------
    if feedback_override is not None:
        feedback_message = feedback_override
    else:
        feedback_message = (
            SUCCESS_FEEDBACK if outcome.success else FAILURE_FEEDBACK
        )
    record["feedback_given"] = feedback_label(feedback_message)
    record["feedback_message"] = feedback_message

    # -- 4/5. Reflect + store ---------------------------------------------
    new_memory: Optional[Dict[str, Any]] = None
    lesson_is_harmful = False
    lesson_valid = True
    if create_memory:
        lesson = _run_reflection(
            config, backend, task, plan, outcome, feedback_message,
            retrieved, valid_ids, record,
        )
        if lesson is None:
            lesson_valid = False
            record["notes"].append("reflection invalid; no memory created")
        else:
            mid = memory_id_for(memory_index if memory_index is not None else cycle_index)
            new_memory = {
                "memory_id": mid,
                "content": lesson["lesson"],
                "source_cycle": cycle_id_for(cycle_index),
                "source_task": task["task_id"],
                "retrieved_parent_ids": [m["memory_id"] for m in retrieved],
                "declared_parent_ids": lesson["parent_memory_ids"],
                "true_outcome": outcome.outcome_label(),
                "feedback_given": record["feedback_given"],
                "created_at": cycle_index,
            }
            lesson_is_harmful = classify_lesson_harmful(new_memory["content"])
            new_memory["harmful"] = lesson_is_harmful
            if add_to_archive:
                archive.add_memory(new_memory)

    record["new_memory"] = new_memory or {}

    return CycleResult(
        record=record,
        plan=plan,
        outcome=outcome,
        retrieved=retrieved,
        new_memory=new_memory,
        lesson_is_harmful=lesson_is_harmful,
        plan_valid=plan_valid,
        lesson_valid=lesson_valid,
        notes=list(record["notes"]),
    )
