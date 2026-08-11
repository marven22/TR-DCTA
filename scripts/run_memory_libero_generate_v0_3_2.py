"""Run v0.3.2 with the numerical lesson-length constraint removed."""
from __future__ import annotations

import json

import run_memory_libero_generate_v0_3_1 as runner


runner.PROTOCOL = "memory-libero/hard-evidence-heldout-v0.3.2"
runner.PROMPT_VERSION = "memory-libero-writer-v0.3.2-hard-evidence-format-fix"

_render_v031 = runner.render_prompt


def render_prompt_v032(**kwargs):
    prompt = _render_v031(**kwargs)
    return prompt.replace(
        "The lesson must contain 12 to 45 whitespace-delimited words, follow the ",
        "The lesson must be concise, follow the ",
    )


def validate_v032(raw, allowed_policy_ids, retrieved_ids, forbidden_ids):
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != runner.EXACT_KEYS:
        raise ValueError("response must contain exactly the four required keys")
    if value["recommended_policy_id"] not in set(allowed_policy_ids) | {"NONE"}:
        raise ValueError("recommended_policy_id is not allowed")
    for field in ("lesson", "expected_outcome"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
        if any(identifier in value[field] for identifier in forbidden_ids):
            raise ValueError(f"{field} exposes a private identifier")
    citations = value["cited_memory_ids"]
    if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
        raise ValueError("cited_memory_ids must be a list of strings")
    if not set(citations).issubset(set(retrieved_ids)):
        raise ValueError("response cites a memory that was not directly retrieved")
    return value


runner.render_prompt = render_prompt_v032
runner.validate = validate_v032


if __name__ == "__main__":
    runner.main()
