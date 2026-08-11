"""Public/private adapter for frozen Memory-LIBERO external validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple


@dataclass(frozen=True)
class ExternalArchive:
    archive_id: str
    suite: str
    split: str
    source_id: str
    candidate_ids: Tuple[str, ...]
    true_edges: frozenset[Tuple[str, str]]
    memories: Mapping[str, Mapping[str, object]]
    created_at: Mapping[str, int]
    affected_ids: frozenset[str]
    direct_gateways: frozenset[str]
    target_language: str


def join_archive(public: Mapping[str, object], labels: Mapping[str, object]) -> ExternalArchive:
    if public["archive_id"] != labels["archive_id"]:
        raise ValueError("public/private archive IDs do not match")
    candidates = tuple(str(node) for node in public["candidate_ids"])  # type: ignore[arg-type]
    affected = frozenset(str(node) for node in labels["affected_ids"])  # type: ignore[arg-type]
    if not affected.issubset(candidates):
        raise ValueError("private labels contain a non-candidate ID")
    return ExternalArchive(
        archive_id=str(public["archive_id"]), suite=str(public["suite"]),
        split=str(public["split"]), source_id=str(public["source_id"]),
        candidate_ids=candidates,
        true_edges=frozenset((str(left), str(right))
                             for left, right in public["formation_edges"]),  # type: ignore[arg-type]
        memories=public["memories"],  # type: ignore[arg-type]
        created_at={str(node): int(value)
                    for node, value in public["created_at"].items()},  # type: ignore[union-attr]
        affected_ids=affected,
        direct_gateways=frozenset(str(node) for node in public["direct_gateways"]),  # type: ignore[arg-type]
        target_language=str(public["target_language"]),
    )

