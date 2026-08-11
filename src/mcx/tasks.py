"""Structured task definitions.

Every task preserves the same underlying rule (the matching key is required to
open the locked door), while varying surface details: room name, door colour,
starting location, key location, and route length.

Each task carries the canonical fields from the brief
(``task_id``/``description``/``initial_state``/``goal``) plus two fields the
deterministic environment needs (``key_location``/``door_location``) and a bit
of descriptive metadata (``room_name``/``door_color``).
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

TASKS: List[Dict[str, Any]] = [
    {
        "task_id": "door_01",
        "description": "Enter the storage room through the locked blue door.",
        "room_name": "storage room",
        "door_color": "blue",
        "initial_state": {
            "location": "hallway",
            "has_key": False,
            "door_locked": True,
        },
        "key_location": "hallway_shelf",
        "door_location": "storage_door",
        "goal": "Enter the storage room",
    },
    {
        "task_id": "door_02",
        "description": "Enter the archive room through the locked red door.",
        "room_name": "archive room",
        "door_color": "red",
        "initial_state": {
            "location": "lobby",
            "has_key": False,
            "door_locked": True,
        },
        "key_location": "reception_desk",
        "door_location": "archive_door",
        "goal": "Enter the archive room",
    },
    {
        "task_id": "door_03",
        "description": "Enter the laboratory through the locked green door.",
        "room_name": "laboratory",
        "door_color": "green",
        "initial_state": {
            "location": "corridor",
            "has_key": False,
            "door_locked": True,
        },
        "key_location": "supply_closet",
        "door_location": "lab_door",
        "goal": "Enter the laboratory",
    },
    {
        "task_id": "door_04",
        "description": "Enter the vault through the locked black door.",
        "room_name": "vault",
        "door_color": "black",
        "initial_state": {
            "location": "atrium",
            "has_key": False,
            "door_locked": True,
        },
        "key_location": "guard_station",
        "door_location": "vault_door",
        "goal": "Enter the vault",
    },
    {
        "task_id": "door_05",
        "description": "Enter the greenhouse through the locked yellow door.",
        "room_name": "greenhouse",
        "door_color": "yellow",
        "initial_state": {
            "location": "garden_path",
            "has_key": False,
            "door_locked": True,
        },
        "key_location": "tool_shed",
        "door_location": "greenhouse_door",
        "goal": "Enter the greenhouse",
    },
]

_TASKS_BY_ID: Dict[str, Dict[str, Any]] = {t["task_id"]: t for t in TASKS}


def get_task(task_id: str) -> Dict[str, Any]:
    """Return a deep copy of the task so callers cannot mutate the registry."""
    if task_id not in _TASKS_BY_ID:
        raise KeyError(f"Unknown task_id: {task_id!r}")
    return copy.deepcopy(_TASKS_BY_ID[task_id])


def all_tasks() -> List[Dict[str, Any]]:
    """Deep copies of every task variation."""
    return [copy.deepcopy(t) for t in TASKS]


def task_ids() -> List[str]:
    return [t["task_id"] for t in TASKS]
