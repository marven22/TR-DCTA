"""The memory archive.

Simple keyword-overlap retrieval -- no embeddings, no vector DB (per the brief).

A memory is a plain dict. The canonical shape (see the brief, section 5) is::

    {
        "memory_id": "m_002",
        "content": "Opening locked doors directly should be attempted ...",
        "source_cycle": "cycle_002",
        "source_task": "door_02",
        "retrieved_parent_ids": ["m_001"],
        "true_outcome": "failure",
        "feedback_given": "success",
        "created_at": 2,
    }
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List, Optional

# Words that carry no retrieval signal.
_STOPWORDS = {
    "a", "an", "the", "to", "through", "is", "are", "was", "were", "be", "of",
    "in", "on", "at", "and", "or", "for", "with", "it", "its", "that", "this",
    "you", "your", "should", "usually", "before", "after", "into", "enter",
    "has", "have", "not", "no", "can", "will",
}


def _tokenize(text: str) -> List[str]:
    """Lowercase alphanumeric tokens, stopwords removed."""
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def task_keywords(task: Dict[str, Any]) -> List[str]:
    """The keywords a task contributes to retrieval."""
    parts = [
        task.get("description", ""),
        task.get("goal", ""),
        task.get("room_name", ""),
        task.get("door_color", ""),
        # Include the canonical locked-door vocabulary so door lessons match.
        "locked door key open",
    ]
    return _tokenize(" ".join(parts))


class MemoryArchive:
    """An ordered keyword-searchable collection of memories."""

    def __init__(self, memories: Optional[List[Dict[str, Any]]] = None) -> None:
        self._memories: List[Dict[str, Any]] = []
        if memories:
            for m in memories:
                self.add_memory(m)

    # -- Mutation -----------------------------------------------------------
    def add_memory(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """Add a (deep-copied) memory. Raises on duplicate memory_id."""
        if "memory_id" not in memory:
            raise ValueError("memory must have a 'memory_id'")
        mid = memory["memory_id"]
        if any(m["memory_id"] == mid for m in self._memories):
            raise ValueError(f"duplicate memory_id: {mid!r}")
        stored = copy.deepcopy(memory)
        self._memories.append(stored)
        return copy.deepcopy(stored)

    def remove_memory(self, memory_id: str) -> bool:
        """Remove a memory by id. Returns True if something was removed."""
        before = len(self._memories)
        self._memories = [m for m in self._memories if m["memory_id"] != memory_id]
        return len(self._memories) < before

    # -- Access -------------------------------------------------------------
    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        for m in self._memories:
            if m["memory_id"] == memory_id:
                return copy.deepcopy(m)
        return None

    def ids(self) -> List[str]:
        return [m["memory_id"] for m in self._memories]

    def all(self) -> List[Dict[str, Any]]:
        return [copy.deepcopy(m) for m in self._memories]

    def __len__(self) -> int:
        return len(self._memories)

    def __contains__(self, memory_id: str) -> bool:
        return any(m["memory_id"] == memory_id for m in self._memories)

    # -- Retrieval ----------------------------------------------------------
    def retrieve_memories(
        self, task: Dict[str, Any], top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Return up to ``top_k`` memories most relevant to ``task``.

        Scored by keyword overlap between the task and each memory's content.
        Ties (and memories with zero overlap) are broken by recency
        (``created_at``) so the most recent relevant lesson wins -- this is
        what lets a freshly-formed downstream memory dominate retrieval.
        """
        keywords = set(task_keywords(task))
        scored = []
        for m in self._memories:
            mem_tokens = set(_tokenize(m.get("content", "")))
            overlap = len(keywords & mem_tokens)
            created = m.get("created_at", 0)
            scored.append((overlap, created, m))

        # Keep only memories with any keyword overlap; sort by (overlap, recency).
        relevant = [s for s in scored if s[0] > 0]
        relevant.sort(key=lambda s: (s[0], s[1]), reverse=True)
        return [copy.deepcopy(m) for _, _, m in relevant[:top_k]]

    # -- Snapshots / persistence -------------------------------------------
    def save_archive(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return a deep-copied snapshot; optionally also write it to JSON."""
        snapshot = self.all()
        if path is not None:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, indent=2)
        return snapshot

    def restore_archive(self, snapshot: List[Dict[str, Any]]) -> None:
        """Replace the archive contents with a snapshot (deep-copied)."""
        self._memories = [copy.deepcopy(m) for m in snapshot]

    @classmethod
    def from_snapshot(cls, snapshot: List[Dict[str, Any]]) -> "MemoryArchive":
        archive = cls()
        archive.restore_archive(snapshot)
        return archive
