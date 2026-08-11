"""Frozen population, split, and archive-graph helpers for publication v2."""
from __future__ import annotations

import hashlib
from typing import Iterable, Mapping, Sequence


PROTOCOL = "memory-corruption/multi-origin-publication-v2"
SPLIT_FRACTIONS = (0.20, 0.20, 0.60)


def stable_digest(*parts: object) -> bytes:
    return hashlib.sha256("|".join(str(value) for value in (PROTOCOL, *parts)).encode()).digest()


def opaque_id(*parts: object, prefix: str = "m") -> str:
    return f"{prefix}_" + stable_digest(*parts).hex()[:18]


def stratified_splits(task_ids: Sequence[str]) -> dict[str, str]:
    """Hash split one benchmark stratum into exact 20/20/60-ish counts."""
    if len(task_ids) != len(set(task_ids)) or not task_ids:
        raise ValueError("task IDs must be nonempty and unique")
    ordered = sorted(task_ids, key=lambda task: (stable_digest("split", task), task))
    development_count = round(len(ordered) * SPLIT_FRACTIONS[0])
    validation_count = round(len(ordered) * SPLIT_FRACTIONS[1])
    return {
        task: (
            "development" if index < development_count else
            "validation" if index < development_count + validation_count else
            "test"
        )
        for index, task in enumerate(ordered)
    }


def graph_spec(task_id: str) -> dict[str, object]:
    """Return the frozen 21-node, three-origin, overlapping acyclic graph."""
    sources = tuple(opaque_id(task_id, "source", branch, prefix="s") for branch in range(3))
    branches = tuple(tuple(
        opaque_id(task_id, "branch", branch, depth)
        for depth in range(1, 6)
    ) for branch in range(3))
    shared = tuple(opaque_id(task_id, "shared", index) for index in range(1, 7))
    edges: list[tuple[str, str]] = []
    for source, nodes in zip(sources, branches):
        edges.append((source, nodes[0]))
        edges.extend(zip(nodes[:-1], nodes[1:]))
        # The revival regime re-retrieves its original formation experience
        # after a corrective replay at depth three.
        edges.append((source, nodes[3]))
    # Three pairwise merges, two cross-merge bridges, and one late convergence.
    edges.extend((
        (branches[0][1], shared[0]), (branches[1][1], shared[0]),
        (branches[1][2], shared[1]), (branches[2][2], shared[1]),
        (branches[2][3], shared[2]), (branches[0][3], shared[2]),
        (shared[0], shared[3]), (branches[2][0], shared[3]),
        (shared[1], shared[4]), (branches[0][2], shared[4]),
        (branches[0][4], shared[5]), (branches[1][4], shared[5]),
        (branches[2][4], shared[5]), (shared[2], shared[5]),
    ))
    candidates = tuple(node for branch in branches for node in branch) + shared
    created_at = {source: index for index, source in enumerate(sources)}
    created_at.update({node: 3 + index for index, node in enumerate(candidates)})
    if any(created_at[left] >= created_at[right] for left, right in edges):
        raise AssertionError("frozen graph is not chronological")
    return {
        "source_ids": list(sources),
        "branch_ids": [list(branch) for branch in branches],
        "shared_ids": list(shared),
        "candidate_ids": list(candidates),
        "formation_edges": [list(edge) for edge in edges],
        "created_at": created_at,
    }


def masked_edges(
    task_id: str, edges: Iterable[Sequence[str]], missing_rate: float,
) -> list[list[str]]:
    if missing_rate not in (0.0, 0.25, 0.50):
        raise ValueError("only frozen provenance masks are permitted")
    values = [tuple(map(str, edge)) for edge in edges]
    remove_count = round(len(values) * missing_rate)
    removal = set(sorted(
        values,
        key=lambda edge: (stable_digest("mask", task_id, missing_rate, *edge), edge),
    )[:remove_count])
    return [list(edge) for edge in values if edge not in removal]


def validate_population(rows: Sequence[Mapping[str, object]]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        benchmark = str(row["benchmark"])
        counts[benchmark] = counts.get(benchmark, 0) + 1
        if len(row["donors"]) != 3:  # type: ignore[arg-type]
            raise ValueError("every production target requires exactly three donors")
    if counts != {"libero": 20, "metaworld": 49}:
        raise ValueError(f"unexpected frozen population: {counts}")
