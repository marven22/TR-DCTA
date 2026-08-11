"""Run v0.3.3 with spatial added to the development pool."""
from __future__ import annotations

import run_memory_libero_generate_v0_3_2  # applies v0.3.2 format revision
import run_memory_libero_generate_v0_3_1 as runner


runner.PROTOCOL = "memory-libero/hard-evidence-heldout-v0.3.3"
runner.PROMPT_VERSION = "memory-libero-writer-v0.3.2-hard-evidence-format-fix"
runner.REQUIRED_SUITES = {
    "libero_object", "libero_goal", "libero_10", "libero_spatial"
}
runner.ALLOWED_SCREEN_PROTOCOLS = {
    "memory-libero/hard-evidence-heldout-v0.3",
    "memory-libero/hard-evidence-heldout-v0.3.3",
}
runner.SPLIT_FOR = {
    "libero_object": "development", "libero_10": "development",
    "libero_spatial": "development", "libero_goal": "heldout",
}


if __name__ == "__main__":
    runner.main()
