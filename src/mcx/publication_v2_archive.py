"""Public/private materialization for the frozen publication-v2 generations."""
from __future__ import annotations

import hashlib
from typing import Mapping, Sequence

from .publication_v2 import PROTOCOL, masked_edges, opaque_id, stable_digest


MASK_RATES = (0.0, 0.25, 0.50)


def public_memory(value: Mapping[str, object]) -> dict[str, object]:
    """Remove policy decisions while preserving auditable memory content."""
    return {
        "lesson": str(value["lesson"]),
        "expected_outcome": str(value["expected_outcome"]),
        "cited_memory_ids": [str(item) for item in value["cited_memory_ids"]],  # type: ignore[index]
    }


def _parsed(record: Mapping[str, object]) -> Mapping[str, object]:
    value = record.get("parsed")
    if not isinstance(value, dict):
        raise ValueError("missing parsed writer record")
    return value


def _different(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return any(left[key] != right[key] for key in (
        "recommended_policy_id", "lesson", "expected_outcome"
    ))


def _decoys(
    task_id: str, nodes: Sequence[str], edges: Sequence[Sequence[str]], count: int,
) -> list[list[str]]:
    truth = {tuple(edge) for edge in edges}
    candidates = [
        (left, right) for i, left in enumerate(nodes) for right in nodes[i + 1:]
        if right.startswith("m_") and (left, right) not in truth
    ]
    return [list(edge) for edge in sorted(
        candidates,
        key=lambda edge: (stable_digest("decoy", task_id, *edge), edge),
    )[:count]]


def materialize_task(archive: Mapping[str, object]) -> tuple[list[dict], list[dict]]:
    graph = archive["graph"]
    sources = [str(value) for value in graph["source_ids"]]
    branches = [[str(node) for node in values] for values in graph["branch_ids"]]
    candidates = [str(value) for value in graph["candidate_ids"]]
    full_edges = [[str(left), str(right)] for left, right in graph["formation_edges"]]
    created_at = {str(key): int(value) for key, value in graph["created_at"].items()}
    success = {str(key): bool(value) for key, value in archive["policy_success"].items()}
    roots = archive["roots"]
    branch_pairs = {
        str(item["memory_id"]): (_parsed(item["factual"]), _parsed(item["counterfactual"]))
        for branch in archive["branches"] for item in branch["memories"]
    }
    shared = {str(item["memory_id"]): item for item in archive["shared_memories"]}
    public_rows, private_rows = [], []
    for rotation in range(3):
        memories = {}
        for index, (source, root) in enumerate(zip(sources, roots)):
            selected = _parsed(root["factual"] if index == rotation else root["counterfactual"])
            memories[source] = public_memory(selected)
        affected, contaminated = set(), set()
        for branch_index, nodes in enumerate(branches):
            for node in nodes:
                factual, clean = branch_pairs[node]
                selected = factual if branch_index == rotation else clean
                memories[node] = public_memory(selected)
                if branch_index == rotation and _different(selected, clean):
                    contaminated.add(node)
                if branch_index == rotation and success[str(selected["recommended_policy_id"])] != success[str(clean["recommended_policy_id"])]:
                    affected.add(node)
        for node, item in shared.items():
            selected = _parsed(item["variants"][f"active_{rotation}"])
            clean = _parsed(item["variants"]["clean"])
            memories[node] = public_memory(selected)
            if _different(selected, clean):
                contaminated.add(node)
            if success[str(selected["recommended_policy_id"])] != success[str(clean["recommended_policy_id"])]:
                affected.add(node)
        edge_set = {tuple(edge) for edge in full_edges}
        for node, memory in memories.items():
            for cited in memory["cited_memory_ids"]:
                if (str(cited), node) not in edge_set:
                    raise ValueError(f"citation missing from formation graph: {cited} -> {node}")
        if not affected:
            raise ValueError(f"empty affected set: {archive['task_id']} rotation {rotation}")
        for rate in MASK_RATES:
            observed = masked_edges(str(archive["task_id"]), full_edges, rate)
            removed = [edge for edge in full_edges if edge not in observed]
            latent = removed + _decoys(
                str(archive["task_id"]), sources + candidates, full_edges, len(removed)
            )
            latent.sort(key=lambda edge: (stable_digest("latent-order", archive["task_id"], rate, *edge), edge))
            archive_id = opaque_id(archive["task_id"], rotation, rate, prefix="v2a")
            common = {
                "archive_id": archive_id, "task_key": opaque_id(archive["task_id"], prefix="task"),
                "benchmark": archive["benchmark"], "stratum": archive["stratum"],
                "split": archive["split"], "rotation": rotation,
                "provenance_missing_rate": rate,
            }
            public_rows.append({
                **common, "target_language": archive["target_language"],
                "source_ids": sources, "candidate_ids": candidates,
                "observed_formation_edges": observed,
                "latent_edge_candidates": latent,
                "memories": memories, "created_at": created_at,
            })
            private_rows.append({
                **common, "active_source_id": sources[rotation],
                "affected_ids": sorted(affected), "contaminated_ids": sorted(contaminated),
                "true_formation_edges": full_edges,
                "true_latent_edges": removed,
            })
    return public_rows, private_rows
