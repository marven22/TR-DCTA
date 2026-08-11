"""Batched first-pass Qwen generation with the frozen two-attempt validator."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Sequence

import run_memory_libero_generate_v0_3_1 as writer

from mcx.model.base import GenerationRequest


@dataclass(frozen=True)
class GenerationJob:
    prompt: str
    task_language: str
    allowed: Sequence[str]
    retrieved: Sequence[Mapping[str, object]]
    forbidden_ids: Sequence[str]


def _request(job: GenerationJob, prompt: str) -> GenerationRequest:
    return GenerationRequest(
        purpose="reflection", prompt=prompt,
        task={"language": job.task_language},
        memories=[writer.visible(item) for item in job.retrieved],
    )


def generate_jobs(backend, jobs: Sequence[GenerationJob]) -> list[dict]:
    raws = backend.generate_batch([_request(job, job.prompt) for job in jobs])
    output = []
    for job, raw in zip(jobs, raws):
        attempts = []
        parsed = None
        try:
            parsed = writer.validate(
                raw, job.allowed, [item["memory_id"] for item in job.retrieved],
                job.forbidden_ids,
            )
            attempts.append({"raw": raw, "valid": True, "error": None})
        except (json.JSONDecodeError, ValueError) as exc:
            attempts.append({"raw": raw, "valid": False, "error": str(exc)})
            repaired_prompt = (
                job.prompt + "\nPrevious response error: " + str(exc)
                + ". Return corrected JSON only."
            )
            repaired = backend.generate(_request(job, repaired_prompt))
            try:
                parsed = writer.validate(
                    repaired, job.allowed,
                    [item["memory_id"] for item in job.retrieved], job.forbidden_ids,
                )
                attempts.append({"raw": repaired, "valid": True, "error": None})
            except (json.JSONDecodeError, ValueError) as second:
                attempts.append({"raw": repaired, "valid": False, "error": str(second)})
        output.append({"prompt": job.prompt, "attempts": attempts, "parsed": parsed})
    return output
