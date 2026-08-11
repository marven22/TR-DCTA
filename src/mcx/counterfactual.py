"""Counterfactual replay.

Restore the archive snapshot from immediately before Cycle 2 and re-run Cycle 2
under two conditions, holding EVERYTHING else constant (task, initial state,
checkpoint, prompt template, decoding settings, environment seed, other
memories):

    Factual         -- archive contains m_1
    Counterfactual  -- identical archive with m_1 removed

We then compare the generated plans, the true outcomes, the new lessons, and --
critically -- whether the resulting child memory causes failure when used by
itself on a held-out task.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .archive import MemoryArchive
from .config import Config
from .cycles import SUCCESS_FEEDBACK, run_cycle
from .environment import LockedDoorEnvironment
from .logging_utils import RunLogger, write_json
from .model import build_backend
from .model.base import ModelBackend


@dataclass
class ReplayArm:
    condition: str                       # "factual" | "counterfactual"
    plan: List[str]
    true_outcome: str
    lesson: Optional[str]
    child_memory: Optional[Dict[str, Any]]
    child_causes_failure_alone: Optional[bool]


@dataclass
class CounterfactualResult:
    scenario_name: str
    cycle2_task: Dict[str, Any]
    factual: ReplayArm
    counterfactual: ReplayArm

    @property
    def m1_changed_plan(self) -> bool:
        return self.factual.plan != self.counterfactual.plan

    @property
    def m1_changed_outcome(self) -> bool:
        return self.factual.true_outcome != self.counterfactual.true_outcome

    @property
    def m1_changed_lesson(self) -> bool:
        return self.factual.lesson != self.counterfactual.lesson

    def as_dict(self) -> Dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "cycle2_task": self.cycle2_task,
            "m1_changed_plan": self.m1_changed_plan,
            "m1_changed_outcome": self.m1_changed_outcome,
            "m1_changed_lesson": self.m1_changed_lesson,
            "factual": self.factual.__dict__,
            "counterfactual": self.counterfactual.__dict__,
        }


def _child_causes_failure_alone(
    config: Config,
    backend: ModelBackend,
    child_memory: Optional[Dict[str, Any]],
    probe_task: Dict[str, Any],
) -> Optional[bool]:
    """Put ONLY the child memory in an archive and see if it induces failure."""
    if child_memory is None:
        return None
    env = LockedDoorEnvironment(seed=config.environment_seed)
    archive = MemoryArchive([child_memory])
    result = run_cycle(
        config, backend, env, archive, probe_task,
        cycle_index=99, create_memory=False,
    )
    return not result.outcome.success


def _run_arm(
    config: Config,
    backend: ModelBackend,
    condition: str,
    snapshot: List[Dict[str, Any]],
    m1_id: str,
    cycle2_task: Dict[str, Any],
    probe_task: Dict[str, Any],
    logger: RunLogger,
) -> ReplayArm:
    env = LockedDoorEnvironment(seed=config.environment_seed)
    archive = MemoryArchive.from_snapshot(snapshot)
    if condition == "counterfactual":
        archive.remove_memory(m1_id)

    result = run_cycle(
        config, backend, env, archive, cycle2_task,
        cycle_index=2,
        feedback_override=SUCCESS_FEEDBACK,
        create_memory=True,
        memory_index=2,
        add_to_archive=True,
    )
    result.record["replay_condition"] = condition
    logger.add(result.record)

    child = result.new_memory
    lesson = child["content"] if child else None
    causes_failure = _child_causes_failure_alone(
        config, backend, child, probe_task
    )
    return ReplayArm(
        condition=condition,
        plan=result.plan,
        true_outcome=result.outcome.outcome_label(),
        lesson=lesson,
        child_memory=child,
        child_causes_failure_alone=causes_failure,
    )


def run_counterfactual(
    config: Config,
    scenario_name: str,
    snapshot_before_cycle2: List[Dict[str, Any]],
    cycle2_task: Dict[str, Any],
    m1_id: str,
    out_dir: str,
    probe_task: Optional[Dict[str, Any]] = None,
    backend: Optional[ModelBackend] = None,
) -> CounterfactualResult:
    """Run the factual and counterfactual arms of the Cycle-2 replay."""
    backend = backend or build_backend(config)
    probe_task = probe_task or cycle2_task
    logger = RunLogger(
        os.path.join(out_dir, "logs"), f"counterfactual__{scenario_name}"
    )

    factual = _run_arm(
        config, backend, "factual", snapshot_before_cycle2, m1_id,
        cycle2_task, probe_task, logger,
    )
    counterfactual = _run_arm(
        config, backend, "counterfactual", snapshot_before_cycle2, m1_id,
        cycle2_task, probe_task, logger,
    )
    logger.flush()

    result = CounterfactualResult(
        scenario_name=scenario_name,
        cycle2_task=cycle2_task,
        factual=factual,
        counterfactual=counterfactual,
    )
    write_json(
        os.path.join(out_dir, "counterfactual", f"{scenario_name}.json"),
        result.as_dict(),
    )
    return result


def run_counterfactual_from_state(
    config: Config, state: Dict[str, Any], out_dir: str,
    backend: Optional[ModelBackend] = None,
) -> CounterfactualResult:
    """Convenience wrapper that reads persisted scenario state."""
    return run_counterfactual(
        config,
        scenario_name=state["scenario_name"],
        snapshot_before_cycle2=state["snapshot_before_cycle2"],
        cycle2_task=state["cycle2_task"],
        m1_id=state["m1_id"],
        out_dir=out_dir,
        backend=backend,
    )
