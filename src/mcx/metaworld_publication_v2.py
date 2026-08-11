"""Pure frozen helpers for the Meta-World publication screen."""
from __future__ import annotations

import hashlib
import math
from typing import Mapping, Sequence, Tuple


PROTOCOL = "memory-corruption/multi-origin-publication-v2"


def validate_config(config: Mapping[str, object]) -> None:
    if config.get("protocol") != f"{PROTOCOL}/metaworld-screen-freeze":
        raise ValueError("frozen Meta-World v2 screen configuration required")
    if config.get("metaworld_version") != "3.0.0":
        raise ValueError("Meta-World version changed")
    if tuple(config.get("seeds", ())) != (1101, 2202, 3303):
        raise ValueError("screen seeds changed")
    if int(config.get("required_donors_per_target", 0)) != 3:
        raise ValueError("three donors are required")
    if int(config.get("minimum_eligible_targets", 0)) != 35:
        raise ValueError("feasibility threshold changed")


def donor_order(target: str, task_names: Sequence[str]) -> Tuple[str, ...]:
    return tuple(sorted(
        (donor for donor in task_names if donor != target),
        key=lambda donor: (
            hashlib.sha256(f"{PROTOCOL}|metaworld-screen|{target}|{donor}".encode()).digest(),
            donor,
        ),
    ))


def task_language(task_name: str) -> str:
    if not task_name.endswith("-v3"):
        raise ValueError("expected a Meta-World v3 task")
    return task_name[:-3].replace("-", " ")


def action_is_valid(action: Sequence[float]) -> bool:
    return len(action) == 4 and all(math.isfinite(float(value)) for value in action)

