"""Model-written memory text for DDXPlus archives.

The template writer composes memory prose from fixed sentence frames.  This
writer keeps every structural decision identical -- it consumes the same plan
from :mod:`mcx.ddxplus_writer` -- and replaces only the prose with text from a
pinned Qwen checkpoint.

The model is never asked what a memory should recommend, whether a memory is
harmful, or which memories it cites.  Python fixes all of that from the plan;
the model supplies wording alone.  This is the same firewall the rest of the
project applies: the model writes, it never judges.

One prompt frame is used for every memory.  A harmful entry and a safe entry
receive byte-identical instructions and differ only in which findings they are
told to describe.  Any instruction that varied with harmfulness would let the
model insert a phrase the posterior could key on, which is exactly the artifact
the template writer originally suffered from.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Iterable, Mapping, Sequence


FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
MAX_LESSON_CHARS = 400

PROMPT = """You are writing one short entry for a clinical case-reference notebook.

PATIENT PRESENTATION
{presentation}

PROCEDURE THIS ENTRY RECOMMENDS
{language}

PREVIOUS ENTRY THIS ONE BUILDS ON
{parent}

Write one lesson of at most 30 words advising which procedure to use for
presentations like this, and one expected outcome of at most 20 words.

Rules:
- Refer to the procedure only by the findings named above.
- Never name a disease, diagnosis, or condition.
- Never say whether the procedure is correct, incorrect, sufficient,
  insufficient, complete, or partial.
- Never mention error, doubt, shortcuts, or omission.

Return only JSON: {{"lesson": "...", "expected_outcome": "..."}}"""


class GenerationRejected(ValueError):
    """The model's response could not be used as written."""


def build_prompt(
    plan: Mapping[str, object], slot: Mapping[str, object], parent_lesson: str | None,
) -> str:
    return PROMPT.format(
        presentation=str(plan["target_language"]),
        language=str(slot["language"]),
        parent=parent_lesson or "(this is the earliest entry; there is none)",
    )


def parse_response(raw: str, forbidden: Iterable[str]) -> tuple[str, str]:
    """Validate one response and return its lesson and expected outcome."""
    text = str(raw).strip()
    fenced = FENCE.fullmatch(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise GenerationRejected(f"response is not JSON: {text[:80]!r}") from error
    if not isinstance(value, dict) or set(value) != {"lesson", "expected_outcome"}:
        raise GenerationRejected("response must contain exactly the two fields")
    lesson = str(value["lesson"]).strip()
    outcome = str(value["expected_outcome"]).strip()
    if not lesson or not outcome:
        raise GenerationRejected("empty lesson or expected outcome")
    if len(lesson) > MAX_LESSON_CHARS or len(outcome) > MAX_LESSON_CHARS:
        raise GenerationRejected("response exceeds the length ceiling")
    for term in forbidden:
        if term and term.lower() in f"{lesson} {outcome}".lower():
            raise GenerationRejected(f"response names a condition: {term}")
    return lesson, outcome


def redact(text: str, forbidden: Iterable[str]) -> str:
    """Remove condition names after the model has exhausted its attempts.

    This mirrors the deterministic privacy guard used by the publication-v2
    generator.  It rewrites wording only; it can never change a recommended
    procedure, a citation, or a label, because the model never supplied those.
    """
    for term in sorted(forbidden, key=len, reverse=True):
        if term:
            text = re.sub(re.escape(term), "the condition", text, flags=re.IGNORECASE)
    return text


def _container_index(plan: Mapping[str, object]) -> dict[str, str]:
    index: dict[str, str] = {}
    for source in plan["source_order"]:  # type: ignore[union-attr]
        index[str(source)] = "roots"
    for branch in plan["branch_order"]:  # type: ignore[union-attr]
        for node in branch:
            index[str(node)] = "branches"
    for node in plan["shared_order"]:  # type: ignore[union-attr]
        index[str(node)] = "shared_memories"
    return index


def _parent_key(container: str, memory_id: str, corrupt: bool, rotation: int | None) -> str:
    if container == "roots":
        return f"roots:{memory_id}:{'factual' if corrupt else 'counterfactual'}"
    if container == "branches":
        return f"branches:{memory_id}:{'factual' if corrupt else 'counterfactual'}"
    if not corrupt or rotation is None:
        return f"shared_memories:{memory_id}:clean"
    return f"shared_memories:{memory_id}:active_{rotation}"


def ordered_slots(plan: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Order slots so a memory is written after the memories it builds on."""
    created = {str(key): int(value)
               for key, value in plan["graph"]["created_at"].items()}  # type: ignore[index]
    return sorted(
        (slot for slot in plan["slots"] if not slot["copy_of"]),  # type: ignore[union-attr]
        key=lambda slot: (created[str(slot["memory_id"])], str(slot["key"])))


def generate_texts(
    plan: Mapping[str, object], generate: Callable[[str], str],
    *, forbidden: Sequence[str], attempts: int = 2,
) -> tuple[dict[str, tuple[str, str]], list[dict[str, object]]]:
    """Write every non-duplicated slot, giving each memory its parent's wording."""
    containers = _container_index(plan)
    parents = {str(key): [str(value) for value in values]
               for key, values in plan["parents"].items()}  # type: ignore[union-attr]
    texts: dict[str, tuple[str, str]] = {}
    incidents: list[dict[str, object]] = []
    for slot in ordered_slots(plan):
        variant = str(slot["variant"])
        corrupt = variant in {"factual"} or variant.startswith("active_")
        rotation = int(variant.rsplit("_", 1)[1]) if variant.startswith("active_") else None
        parent_lesson = None
        for parent in parents.get(str(slot["memory_id"]), ()):
            key = _parent_key(containers[parent], parent, corrupt, rotation)
            if key in texts:
                parent_lesson = texts[key][0]
                break
        prompt = build_prompt(plan, slot, parent_lesson)
        last: Exception | None = None
        for attempt in range(attempts):
            raw = generate(prompt)
            try:
                texts[str(slot["key"])] = parse_response(raw, forbidden)
                break
            except GenerationRejected as error:
                last = error
                incidents.append({"key": slot["key"], "attempt": attempt,
                                  "reason": str(error)})
        else:
            # Fall back to a redacted final response rather than abandoning the
            # archive; the incident is recorded in the emitted ledger.
            try:
                value = json.loads(FENCE.sub(r"\1", str(raw).strip()))
                lesson = redact(str(value.get("lesson", "")).strip(), forbidden)
                outcome = redact(str(value.get("expected_outcome", "")).strip(), forbidden)
                texts[str(slot["key"])] = parse_response(
                    json.dumps({"lesson": lesson, "expected_outcome": outcome}), forbidden)
                incidents.append({"key": slot["key"], "attempt": attempts,
                                  "reason": "redacted after exhausted attempts"})
            except (json.JSONDecodeError, GenerationRejected, TypeError) as error:
                raise GenerationRejected(
                    f"{slot['key']}: unusable after {attempts} attempts: {last or error}"
                ) from error
    return texts, incidents


def forbidden_terms(task: Mapping[str, object]) -> tuple[str, ...]:
    """Condition names the written text must never contain."""
    names = [str(task["target_name"])]
    names.extend(str(donor["name"]) for donor in task["donors"])  # type: ignore[index]
    return tuple(sorted(set(names), key=len, reverse=True))
