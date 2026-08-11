"""The model-backend interface.

The harness calls the model for exactly two purposes -- planning and
reflection -- and always logs the raw string the model returns. A backend
receives both the fully-rendered prompt string (what a real LM would see, and
what gets logged) and a structured ``context`` object. The real Qwen backend
uses only the prompt; the scripted backend uses the structured context to
behave deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GenerationRequest:
    """Everything a backend might need to produce one response."""

    purpose: str                      # "plan" or "reflection"
    prompt: str                       # fully rendered prompt (always logged)
    task: Dict[str, Any]
    memories: List[Dict[str, Any]] = field(default_factory=list)
    # Reflection-only fields:
    plan: Optional[List[str]] = None
    outcome: Optional[Dict[str, Any]] = None
    feedback: Optional[str] = None
    # Optional per-request cap. Backends that can honor it should use the
    # maximum cap in a homogeneous batch; callers group requests by purpose.
    max_new_tokens: Optional[int] = None
    # Optional task-specific system instruction. Existing experiments omit it
    # and retain the repository-wide JSON-only default.
    system_prompt: Optional[str] = None


class ModelBackend:
    """Abstract backend. Implementations return a raw string per request."""

    name: str = "abstract"

    def generate(self, request: GenerationRequest) -> str:  # pragma: no cover
        raise NotImplementedError

    def generate_batch(self, requests: List[GenerationRequest]) -> List[str]:
        """Generate a deterministic batch; backends may override for efficiency."""
        return [self.generate(request) for request in requests]
