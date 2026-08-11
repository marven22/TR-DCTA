"""Factual three-cycle experiment.

For each scenario we run:

    Cycle 1 -- create the original bad memory m_1 from a predefined failed
               trajectory + deliberately incorrect "success" feedback.
    Cycle 2 -- give a new task, retrieve m_1, let a downstream memory m_2 form
               under reinforcing positive feedback. Snapshot the archive
               immediately BEFORE this cycle for the counterfactual replay.
    Cycle 3 -- delete m_1, keep m_2, and measure whether m_2 alone keeps the
               agent attempting the incorrect strategy.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .archive import MemoryArchive
from .config import Config
from .cycles import (
    SUCCESS_FEEDBACK,
    CycleResult,
    memory_id_for,
    run_cycle,
)
from .environment import LockedDoorEnvironment
from .logging_utils import RunLogger, write_json
from .model import build_backend
from .model.base import ModelBackend

# The predefined failed trajectory used to seed Cycle 1: it tries to open the
# locked door without ever collecting the key.
PREDEFINED_FAILED_PLAN: List[str] = ["move_to_door", "open_door", "enter_room"]

# A correctly-learned memory used for the "clean control" evaluation condition.
CLEAN_CORRECT_MEMORY: Dict[str, Any] = {
    "memory_id": "m_clean",
    "content": (
        "Collect the matching key first, then move to the locked door, open "
        "it, and enter the room."
    ),
    "source_cycle": "seed",
    "source_task": "seed",
    "retrieved_parent_ids": [],
    "true_outcome": "success",
    "feedback_given": "success",
    "created_at": 0,
    "harmful": False,
}


@dataclass
class ScenarioResult:
    scenario_name: str
    cycle1: CycleResult
    cycle2: CycleResult
    cycle3: CycleResult
    m1: Dict[str, Any]
    m2: Optional[Dict[str, Any]]
    m1_retrieved_before_m2: bool
    snapshot_before_cycle2: List[Dict[str, Any]]
    cycle1_task: Dict[str, Any]
    cycle2_task: Dict[str, Any]
    cycle3_task: Dict[str, Any]
    notes: List[str] = field(default_factory=list)

    # Convenience flags for the summary CSV.
    @property
    def harmful_m2_created(self) -> bool:
        return bool(self.m2 and self.m2.get("harmful"))

    @property
    def cycle3_failed(self) -> bool:
        return not self.cycle3.outcome.success

    def state_for_counterfactual(self) -> Dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "snapshot_before_cycle2": self.snapshot_before_cycle2,
            "cycle2_task": self.cycle2_task,
            "m1_id": self.m1["memory_id"],
            "factual_m2": self.m2,
        }


def _seed_m1(
    config: Config,
    backend: ModelBackend,
    env: LockedDoorEnvironment,
    archive: MemoryArchive,
    candidate_tasks: List[Dict[str, Any]],
    logger: RunLogger,
) -> CycleResult:
    """Cycle 1: produce a *clearly incorrect* m_1 from the model.

    If the model does not produce a clearly-incorrect lesson, we record the
    attempt and repeat with another task variation -- we never hand-edit the
    lesson (per the brief).
    """
    last: Optional[CycleResult] = None
    for i, task in enumerate(candidate_tasks):
        # A fresh archive per attempt so m_1 always ends up as memory index 1.
        archive.restore_archive([])
        result = run_cycle(
            config, backend, env, archive, task,
            cycle_index=1,
            predefined_plan=PREDEFINED_FAILED_PLAN,
            feedback_override=SUCCESS_FEEDBACK,   # deliberately incorrect
            create_memory=True,
            memory_index=1,
            add_to_archive=True,
        )
        result.record["cycle1_attempt"] = i
        logger.add(result.record)
        last = result
        if result.lesson_is_harmful and result.new_memory is not None:
            return result
        # Not clearly incorrect: remove whatever was added and try next task.
        if result.new_memory is not None:
            archive.remove_memory(result.new_memory["memory_id"])
        result.record["notes"].append(
            "Cycle 1 lesson was not clearly incorrect; retrying with another "
            "task variation."
        )
    # Fall through: return the last attempt even if not harmful (logged).
    assert last is not None
    return last


def run_scenario(
    config: Config,
    scenario_name: str,
    cycle1_task: Dict[str, Any],
    cycle2_task: Dict[str, Any],
    cycle3_task: Dict[str, Any],
    out_dir: str,
    backend: Optional[ModelBackend] = None,
) -> ScenarioResult:
    """Run one factual three-cycle scenario end to end."""
    backend = backend or build_backend(config)
    env = LockedDoorEnvironment(seed=config.environment_seed)
    archive = MemoryArchive()
    logger = RunLogger(os.path.join(out_dir, "logs"), f"factual__{scenario_name}")
    notes: List[str] = []

    # -- Cycle 1: seed m_1 -------------------------------------------------
    # Try the requested cycle-1 task first, then the rest as fallbacks.
    from .tasks import all_tasks

    ordered = [cycle1_task] + [
        t for t in all_tasks() if t["task_id"] != cycle1_task["task_id"]
    ]
    cycle1 = _seed_m1(config, backend, env, archive, ordered, logger)
    if not cycle1.lesson_is_harmful:
        notes.append(
            "WARNING: no task variation produced a clearly-incorrect m_1; "
            "using the last attempt."
        )
    m1 = cycle1.new_memory
    if m1 is None:
        raise RuntimeError(
            "Cycle 1 did not produce a valid lesson for any task variation "
            "(the model's reflection output failed JSON validation on every "
            "attempt). Inspect the raw responses in the run's logs/ under "
            f"factual__{scenario_name}__cycle_001.json (see the "
            "'reflection_validation' field). This is a model-output issue, not "
            "a harness failure."
        )

    # -- Snapshot immediately BEFORE Cycle 2 -------------------------------
    snapshot_before_cycle2 = archive.save_archive()

    # -- Cycle 2: allow downstream m_2 to form -----------------------------
    cycle2 = run_cycle(
        config, backend, env, archive, cycle2_task,
        cycle_index=2,
        feedback_override=SUCCESS_FEEDBACK,   # reinforcing positive feedback
        create_memory=True,
        memory_index=2,
        add_to_archive=True,
    )
    m1_retrieved_before_m2 = m1["memory_id"] in [
        mem["memory_id"] for mem in cycle2.retrieved
    ]
    cycle2.record["m1_retrieved_before_m2"] = m1_retrieved_before_m2
    logger.add(cycle2.record)
    m2 = cycle2.new_memory

    # -- Cycle 3: delete m_1, keep m_2, measure ----------------------------
    archive.remove_memory(m1["memory_id"])
    cycle3 = run_cycle(
        config, backend, env, archive, cycle3_task,
        cycle_index=3,
        create_memory=False,           # measurement only
    )
    cycle3.record["m1_present"] = m1["memory_id"] in archive.ids()
    cycle3.record["m2_present"] = bool(m2 and m2["memory_id"] in archive.ids())
    cycle3.record["retrieved_ids"] = [m["memory_id"] for m in cycle3.retrieved]
    logger.add(cycle3.record)

    logger.flush()

    result = ScenarioResult(
        scenario_name=scenario_name,
        cycle1=cycle1,
        cycle2=cycle2,
        cycle3=cycle3,
        m1=m1,
        m2=m2,
        m1_retrieved_before_m2=m1_retrieved_before_m2,
        snapshot_before_cycle2=snapshot_before_cycle2,
        cycle1_task=cycle1.record["task"],
        cycle2_task=cycle2_task,
        cycle3_task=cycle3_task,
        notes=notes,
    )

    # Persist the state the counterfactual replay needs.
    write_json(
        os.path.join(out_dir, "state", f"{scenario_name}.json"),
        result.state_for_counterfactual(),
    )
    return result


def scenario_tasks(index: int) -> Dict[str, Dict[str, Any]]:
    """Pick three distinct task variations for scenario ``index`` (1-based)."""
    from .tasks import all_tasks

    tasks = all_tasks()
    n = len(tasks)
    i = (index - 1) % n
    return {
        "cycle1": tasks[(i - 1) % n],
        "cycle2": tasks[i],
        "cycle3": tasks[(i + 1) % n],
    }


def run_factual_experiment(
    config: Config, out_dir: str, num_scenarios: int = 5
) -> List[ScenarioResult]:
    """Run all factual scenarios and return their results."""
    backend = build_backend(config)
    results: List[ScenarioResult] = []
    for k in range(1, num_scenarios + 1):
        tset = scenario_tasks(k)
        scenario_name = f"door_{k}"
        results.append(
            run_scenario(
                config,
                scenario_name,
                tset["cycle1"],
                tset["cycle2"],
                tset["cycle3"],
                out_dir,
                backend=backend,
            )
        )
    return results
