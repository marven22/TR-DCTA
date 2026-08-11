"""Model backends: a common interface plus two implementations.

* ``ScriptedBackend`` -- deterministic, dependency-free, memory-conditioned.
  Runs anywhere and powers the tests and the reference deliverables.
* ``QwenHFBackend`` -- a real Qwen checkpoint via HuggingFace transformers
  (requires a GPU and the pinned dependencies).

Both satisfy :class:`ModelBackend`, so the rest of the harness is identical
regardless of which one is used.
"""
from __future__ import annotations

from ..config import Config
from .base import GenerationRequest, ModelBackend
from .scripted import ScriptedBackend


def build_backend(config: Config) -> ModelBackend:
    """Instantiate the backend named by ``config.backend``."""
    if config.backend == "scripted":
        return ScriptedBackend(config)
    if config.backend == "qwen":
        # Imported lazily so the harness works without torch/transformers.
        from .qwen_hf import QwenHFBackend

        return QwenHFBackend(config)
    raise ValueError(f"unknown backend: {config.backend!r}")


__all__ = [
    "ModelBackend",
    "GenerationRequest",
    "ScriptedBackend",
    "build_backend",
]
