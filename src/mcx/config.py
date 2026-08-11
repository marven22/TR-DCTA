"""Central configuration for the experiment.

Everything that must be held constant across factual / counterfactual runs
(and reported in every log record) lives here: the model checkpoint, the
decoding settings, the retrieval depth, and the environment seed.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Model checkpoint.
#
# NOTE ON THE CHECKPOINT NAME: the task brief is internally inconsistent -- the
# objective says "Qwen2.5" while section 3 says "Qwen3.5-9B" (which is not a
# released checkpoint). We therefore default to a real, publicly available,
# pinned Qwen2.5 checkpoint and make it fully configurable. Override with the
# MCX_MODEL_CHECKPOINT / MCX_MODEL_REVISION environment variables or a Config
# argument to point at whatever checkpoint you have locally.
# ---------------------------------------------------------------------------
DEFAULT_CHECKPOINT = "Qwen/Qwen2.5-14B-Instruct"
# Pin an immutable revision (commit SHA) for reproducibility. This SHA is the
# Qwen2.5-14B-Instruct snapshot used for the MemoryArena pilot; change it only
# deliberately.
DEFAULT_REVISION = "cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8"


@dataclass(frozen=True)
class GenerationSettings:
    """Decoding settings. Greedy + non-thinking, as required by the brief."""

    do_sample: bool = False          # greedy decoding
    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int = 0
    max_new_tokens: int = 512
    enable_thinking: bool = False     # non-thinking mode
    repetition_penalty: float = 1.0

    def as_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class Config:
    """Frozen experiment configuration."""

    # Which model backend to use: "scripted" (deterministic, no GPU) or "qwen".
    backend: str = "scripted"

    model_checkpoint: str = DEFAULT_CHECKPOINT
    model_revision: str = DEFAULT_REVISION
    generation: GenerationSettings = field(default_factory=GenerationSettings)

    # Memory retrieval depth.
    top_k: int = 3

    # Deterministic environment seed (recorded in every log record).
    environment_seed: int = 42

    # Retry an invalid model response exactly once (per the brief).
    max_parse_retries: int = 1

    def model_checkpoint_label(self) -> str:
        """String recorded as `model_checkpoint` in log records."""
        if self.backend == "scripted":
            return "scripted-deterministic-backend/v1 (stand-in for Qwen)"
        if self.model_revision:
            return f"{self.model_checkpoint}@{self.model_revision}"
        return f"{self.model_checkpoint}@latest"

    def as_log_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "model_checkpoint": self.model_checkpoint_label(),
            "generation_settings": self.generation.as_dict(),
            "top_k": self.top_k,
            "environment_seed": self.environment_seed,
            "max_parse_retries": self.max_parse_retries,
        }


def config_from_env(**overrides: Any) -> Config:
    """Build a Config, honouring MCX_* environment variables then overrides."""
    import os

    base: Dict[str, Any] = {}
    if "MCX_BACKEND" in os.environ:
        base["backend"] = os.environ["MCX_BACKEND"]
    if "MCX_MODEL_CHECKPOINT" in os.environ:
        base["model_checkpoint"] = os.environ["MCX_MODEL_CHECKPOINT"]
        # The default revision is pinned to the default checkpoint; if a
        # different checkpoint is chosen without its own revision, don't force
        # the default SHA -- use the checkpoint's latest.
        base["model_revision"] = None
    if "MCX_MODEL_REVISION" in os.environ:
        base["model_revision"] = os.environ["MCX_MODEL_REVISION"]
    if "MCX_ENV_SEED" in os.environ:
        base["environment_seed"] = int(os.environ["MCX_ENV_SEED"])
    base.update(overrides)
    return Config(**base)
