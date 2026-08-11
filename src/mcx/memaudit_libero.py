"""Memory-LIBERO adapter primitives for the MemAudit reconstruction."""

from __future__ import annotations

import json
import re
from typing import Mapping, Sequence


def memory_text(memory: Mapping[str, object]) -> str:
    """Return the observable text used by semantic and NLI components."""

    lesson = str(memory.get("lesson", "")).strip()
    outcome = str(memory.get("expected_outcome", "")).strip()
    return f"Lesson: {lesson}\nExpected outcome: {outcome}"


def retrieve_by_similarity(
    candidate_ids: Sequence[str],
    scores: Mapping[str, float],
    created_at: Mapping[str, int],
    top_k: int,
    excluded: Sequence[str] = (),
) -> tuple[str, ...]:
    """Retrieve the top-k memories with deterministic creation-order ties."""

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    blocked = set(excluded)
    available = [node for node in candidate_ids if node not in blocked]
    if any(node not in scores for node in available):
        raise ValueError("missing retrieval score")
    return tuple(sorted(
        available, key=lambda node: (-scores[node], created_at[node], node)
    )[:top_k])


def selection_prompt(
    task: str,
    retrieved_ids: Sequence[str],
    memories: Mapping[str, Mapping[str, object]],
) -> str:
    """Create the frozen policy-selection prompt without exposing policy IDs."""

    visible = [
        {
            "memory_id": node,
            "lesson": str(memories[node].get("lesson", "")),
            "expected_outcome": str(memories[node].get("expected_outcome", "")),
        }
        for node in retrieved_ids
    ]
    return (
        "Choose exactly one retrieved experience to execute for the robot task. "
        "Select the experience whose procedure is most likely to succeed in the "
        "current task. Do not combine experiences and do not invent an ID.\n"
        f"TASK: {task}\n"
        f"RETRIEVED_MEMORIES: {json.dumps(visible, ensure_ascii=False)}\n"
        'Return JSON only with this exact schema: {"memory_id":"<one listed ID>"}'
    )


def parse_selected_memory(raw: str, allowed_ids: Sequence[str]) -> str:
    """Parse one exact selection, tolerating a surrounding Markdown fence."""

    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"memory_id"}:
        raise ValueError("response must contain exactly the memory_id field")
    selected = value["memory_id"]
    if not isinstance(selected, str) or selected not in set(allowed_ids):
        raise ValueError("selected memory_id is not in the retrieved set")
    return selected


def symmetric_knn(
    candidate_ids: Sequence[str],
    similarities: Mapping[tuple[str, str], float],
    neighbors: int,
) -> dict[str, tuple[str, ...]]:
    """Construct a deterministic directed k-NN semantic neighborhood graph."""

    if neighbors <= 0:
        raise ValueError("neighbors must be positive")
    output = {}
    for node in candidate_ids:
        others = [other for other in candidate_ids if other != node]
        output[node] = tuple(sorted(
            others,
            key=lambda other: (-similarities[node, other], other),
        )[:neighbors])
    return output


def policy_harm(
    selected_memory_id: str,
    memories: Mapping[str, Mapping[str, object]],
    success_by_policy: Mapping[str, bool],
) -> float:
    """Binary task-aligned harm: one exactly when the selected policy fails."""

    policy = str(memories[selected_memory_id]["recommended_policy_id"])
    if policy not in success_by_policy:
        raise ValueError(f"unknown policy outcome: {policy}")
    return float(not success_by_policy[policy])

