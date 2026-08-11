"""Run the versioned v0.2 writer with direct-retrieval provenance semantics."""
from __future__ import annotations

import run_memory_libero_generate as runner


runner.SOURCE_PROTOCOL = "memory-libero/source-conditioned-provenance-pilot-v0.1"
runner.PROTOCOL = "memory-libero/source-conditioned-provenance-pilot-v0.2"
runner.PROMPT_VERSION = "memory-libero-writer-v0.2-direct-retrieval"

_render_v0_1 = runner.render_prompt
_VISIBLE_RETRIEVED_FIELDS = {
    "memory_id", "recommended_policy_id", "lesson", "expected_outcome"
}


def render_prompt_v0_2(**kwargs):
    """Do not recursively expose a retrieved memory's citation metadata."""
    kwargs["retrieved"] = [
        {key: value for key, value in memory.items() if key in _VISIBLE_RETRIEVED_FIELDS}
        for memory in kwargs["retrieved"]
    ]
    return _render_v0_1(**kwargs)


runner.render_prompt = render_prompt_v0_2


if __name__ == "__main__":
    runner.main()
