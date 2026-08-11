"""Parsing and validation of model output.

The brief is explicit: do NOT silently correct invalid model output. These
functions return a structured result that records whether parsing succeeded and
exactly why it failed, so the caller can log the failure and retry once.

Plan validation checks:
    * the response is valid JSON
    * every plan step is an allowed action
    * every reported memory ID exists in the archive
    * no unexpected fields are included
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .environment import AVAILABLE_ACTIONS


@dataclass
class ParseResult:
    ok: bool
    value: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "value": self.value, "errors": list(self.errors)}


def _extract_json(raw: str) -> Optional[Any]:
    """Parse the first JSON object found in ``raw``.

    We tolerate the model wrapping JSON in prose or code fences (a formatting
    quirk, not a semantic correction), but we do NOT alter field values.
    """
    raw = raw.strip()
    # Strip a ```json ... ``` or ``` ... ``` fence if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fall back to the first {...} block.
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def validate_plan(raw: str, valid_memory_ids: List[str]) -> ParseResult:
    """Validate a raw planning response."""
    errors: List[str] = []
    obj = _extract_json(raw)
    if obj is None:
        return ParseResult(ok=False, errors=["response is not valid JSON"])
    if not isinstance(obj, dict):
        return ParseResult(ok=False, errors=["top-level JSON is not an object"])

    allowed_keys = {"plan", "memory_ids_used"}
    extra = set(obj.keys()) - allowed_keys
    if extra:
        errors.append(f"unexpected fields: {sorted(extra)}")
    missing = allowed_keys - set(obj.keys())
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")

    plan = obj.get("plan")
    if not isinstance(plan, list) or not all(isinstance(s, str) for s in plan):
        errors.append("'plan' must be a list of strings")
    else:
        bad = [s for s in plan if s not in AVAILABLE_ACTIONS]
        if bad:
            errors.append(f"plan contains disallowed actions: {bad}")

    mem_used = obj.get("memory_ids_used")
    if not isinstance(mem_used, list) or not all(isinstance(s, str) for s in mem_used):
        errors.append("'memory_ids_used' must be a list of strings")
    else:
        unknown = [m for m in mem_used if m not in valid_memory_ids]
        if unknown:
            errors.append(f"memory_ids_used references unknown ids: {unknown}")

    if errors:
        return ParseResult(ok=False, errors=errors)
    return ParseResult(ok=True, value={"plan": plan, "memory_ids_used": mem_used})


def validate_lesson(raw: str, valid_memory_ids: List[str]) -> ParseResult:
    """Validate a raw reflection response."""
    errors: List[str] = []
    obj = _extract_json(raw)
    if obj is None:
        return ParseResult(ok=False, errors=["response is not valid JSON"])
    if not isinstance(obj, dict):
        return ParseResult(ok=False, errors=["top-level JSON is not an object"])

    allowed_keys = {"lesson", "parent_memory_ids"}
    extra = set(obj.keys()) - allowed_keys
    if extra:
        errors.append(f"unexpected fields: {sorted(extra)}")
    missing = allowed_keys - set(obj.keys())
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")

    lesson = obj.get("lesson")
    if not isinstance(lesson, str) or not lesson.strip():
        errors.append("'lesson' must be a non-empty string")

    parents = obj.get("parent_memory_ids")
    if not isinstance(parents, list) or not all(isinstance(s, str) for s in parents):
        errors.append("'parent_memory_ids' must be a list of strings")

    if errors:
        return ParseResult(ok=False, errors=errors)

    # NOTE: unlike a plan's `memory_ids_used`, a lesson's `parent_memory_ids`
    # is the model's *self-reported* lineage claim. Models routinely echo an id
    # from the prompt example even when the archive is empty (e.g. Cycle 1). We
    # therefore do NOT reject the lesson over a non-existent declared parent --
    # the experiment records the TRUE retrieved parents separately
    # (`retrieved_parent_ids`). We surface unknown declared ids as a
    # non-fatal note rather than silently dropping them.
    unknown = [m for m in parents if m not in valid_memory_ids]
    warnings = (
        [f"declared parent ids not in archive (kept as declared): {unknown}"]
        if unknown else []
    )
    return ParseResult(
        ok=True,
        value={"lesson": lesson.strip(), "parent_memory_ids": parents},
        errors=warnings,  # non-fatal notes; ok is True
    )
