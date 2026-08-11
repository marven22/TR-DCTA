"""Four-condition evaluation over held-out tasks.

Condition          Available memories
-----------------  --------------------------------
clean_control      only correctly-learned memories
corrupted          m_1 and m_2
ancestor_removed   m_2 only
both_removed       neither m_1 nor m_2 (empty)

Each condition is evaluated on the same held-out task variations, with the
required number of runs each. (With greedy decoding and a deterministic
environment the runs are identical by construction; the repetition is kept for
protocol fidelity and to leave room for a stochastic backend.)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .archive import MemoryArchive
from .config import Config
from .cycles import run_cycle
from .environment import LockedDoorEnvironment
from .experiment import CLEAN_CORRECT_MEMORY
from .model import build_backend
from .model.base import ModelBackend
from .tasks import all_tasks


@dataclass
class EvalRow:
    condition: str
    task_id: str
    run: int
    success: bool
    key_collected: bool
    invalid_door_open_attempts: int
    action_count: int
    retrieved_ids: List[str]
    plan: List[str]

    def as_csv_dict(self) -> Dict[str, Any]:
        return {
            "condition": self.condition,
            "task_id": self.task_id,
            "run": self.run,
            "success": int(self.success),
            "key_collected": int(self.key_collected),
            "invalid_door_open_attempts": self.invalid_door_open_attempts,
            "action_count": self.action_count,
            "retrieved_ids": "|".join(self.retrieved_ids),
            "plan": "|".join(self.plan),
        }


def _condition_archives(
    m1: Dict[str, Any], m2: Optional[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    archives: Dict[str, List[Dict[str, Any]]] = {
        "clean_control": [dict(CLEAN_CORRECT_MEMORY)],
        "corrupted": [m1] + ([m2] if m2 else []),
        "ancestor_removed": [m2] if m2 else [],
        "both_removed": [],
    }
    return archives


def run_evaluation(
    config: Config,
    m1: Dict[str, Any],
    m2: Optional[Dict[str, Any]],
    out_dir: str,
    runs_per_condition: int = 10,
    backend: Optional[ModelBackend] = None,
) -> List[EvalRow]:
    """Evaluate all four conditions across all task variations."""
    backend = backend or build_backend(config)
    tasks = all_tasks()
    archives = _condition_archives(m1, m2)

    rows: List[EvalRow] = []
    for condition, seed_memories in archives.items():
        for task in tasks:
            for run in range(1, runs_per_condition + 1):
                env = LockedDoorEnvironment(seed=config.environment_seed)
                archive = MemoryArchive(seed_memories)
                result = run_cycle(
                    config, backend, env, archive, task,
                    cycle_index=100 + run, create_memory=False,
                )
                o = result.outcome
                rows.append(
                    EvalRow(
                        condition=condition,
                        task_id=task["task_id"],
                        run=run,
                        success=o.success,
                        key_collected=o.key_collected,
                        invalid_door_open_attempts=o.invalid_door_open_attempts,
                        action_count=o.num_actions_attempted,
                        retrieved_ids=[m["memory_id"] for m in result.retrieved],
                        plan=result.plan,
                    )
                )
    return rows


def summarize_conditions(rows: List[EvalRow]) -> Dict[str, Dict[str, float]]:
    """Aggregate per-condition means for the feasibility report."""
    from collections import defaultdict

    buckets: Dict[str, List[EvalRow]] = defaultdict(list)
    for r in rows:
        buckets[r.condition].append(r)

    summary: Dict[str, Dict[str, float]] = {}
    for cond, rs in buckets.items():
        n = len(rs)
        summary[cond] = {
            "n": n,
            "success_rate": sum(r.success for r in rs) / n,
            "key_acquisition_rate": sum(r.key_collected for r in rs) / n,
            "mean_invalid_door_open_attempts": sum(
                r.invalid_door_open_attempts for r in rs
            ) / n,
            "mean_action_count": sum(r.action_count for r in rs) / n,
        }
    return summary
