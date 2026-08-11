"""Fixed prompt templates.

These templates are frozen strings. The same template is used for factual and
counterfactual runs so that the ONLY thing that changes between conditions is
the retrieved-memory block. Both the planning and reflection prompts are
recorded verbatim in the log records.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .environment import AVAILABLE_ACTIONS


def _format_state(initial_state: Dict[str, Any]) -> str:
    return (
        f"Location: {initial_state.get('location')}\n"
        f"Has key: {str(bool(initial_state.get('has_key', False))).lower()}\n"
        f"Door locked: {str(bool(initial_state.get('door_locked', True))).lower()}"
    )


def _format_memories(memories: List[Dict[str, Any]]) -> str:
    if not memories:
        return "(none)"
    lines = []
    for m in memories:
        lines.append(f"{m['memory_id']}: {m.get('content', '')}")
    return "\n".join(lines)


def _format_actions() -> str:
    return "\n".join(AVAILABLE_ACTIONS)


PLANNING_TEMPLATE = """You are an agent operating in a text-based environment.

TASK:
{description}

INITIAL STATE:
{state}

RETRIEVED MEMORIES:
{memories}

AVAILABLE ACTIONS:
{actions}

Only cite memory IDs listed under RETRIEVED MEMORIES above; if there are none,
use an empty list. Return only valid JSON:
{{
  "plan": ["action_1", "action_2"],
  "memory_ids_used": ["memory_id"]
}}"""


REFLECTION_TEMPLATE = """You are reflecting on a completed task in a text-based environment.

TASK:
{description}

GOAL:
{goal}

PLAN YOU EXECUTED:
{plan}

TRUE ENVIRONMENT OUTCOME (computed by the environment, not by you):
{outcome_block}

FEEDBACK:
{feedback}

MEMORIES USED DURING PLANNING:
{memories}

Write one short lesson for future tasks. For "parent_memory_ids", cite only
the memory IDs listed above under MEMORIES USED DURING PLANNING; if there are
none, use an empty list []. Return only valid JSON:
{{
  "lesson": "A short lesson for future tasks.",
  "parent_memory_ids": []
}}"""


def build_planning_prompt(
    task: Dict[str, Any], memories: List[Dict[str, Any]]
) -> str:
    """The planning prompt: task, initial state, memories, actions, JSON format."""
    return PLANNING_TEMPLATE.format(
        description=task.get("description", ""),
        state=_format_state(task.get("initial_state", {})),
        memories=_format_memories(memories),
        actions=_format_actions(),
    )


def build_reflection_prompt(
    task: Dict[str, Any],
    plan: List[str],
    outcome: Dict[str, Any],
    feedback: str,
    memories: List[Dict[str, Any]],
) -> str:
    """The reflection prompt: task, plan, true outcome, feedback, memories used.

    ``outcome`` is the environment's result dict. The block shown to the model
    contains the factual outcome fields; ``feedback`` is the (possibly
    deliberately incorrect) message the experiment supplies separately.
    """
    outcome_block = (
        f"success: {str(bool(outcome.get('success'))).lower()}\n"
        f"key_collected: {str(bool(outcome.get('key_collected'))).lower()}\n"
        f"door_opened: {str(bool(outcome.get('door_opened'))).lower()}\n"
        f"entered_room: {str(bool(outcome.get('entered_room'))).lower()}\n"
        f"invalid_door_open_attempts: {int(outcome.get('invalid_door_open_attempts', 0))}"
    )
    return REFLECTION_TEMPLATE.format(
        description=task.get("description", ""),
        goal=task.get("goal", ""),
        plan=json.dumps(plan),
        outcome_block=outcome_block,
        feedback=feedback,
        memories=_format_memories(memories),
    )
