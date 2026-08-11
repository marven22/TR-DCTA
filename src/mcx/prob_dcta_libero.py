"""Construction and inference for the Memory-LIBERO multi-origin study."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Dict, Mapping, Sequence, Tuple

from .directional_transition import (
    CascadeWorld, LocalTransitionParameters, build_local_directional_posterior,
)
from .prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld


PROTOCOL = "memory-libero/multi-origin-probability-v1"
CONDITIONS = ("known", "high", "medium", "uniform", "wrong60")


def canonical_hash(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _opaque(*parts: object) -> str:
    payload = "|".join(str(part) for part in (PROTOCOL, *parts))
    return "m_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _unit_interval(*parts: object) -> float:
    payload = "|".join(str(part) for part in (PROTOCOL, *parts))
    digest = hashlib.sha256(payload.encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def split_assignments(records: Sequence[Mapping[str, object]]) -> Dict[str, str]:
    ordered = sorted(
        (str(record["archive_id"]) for record in records),
        key=lambda archive_id: hashlib.sha256(
            f"{PROTOCOL}|split|{archive_id}".encode()
        ).hexdigest(),
    )
    if len(ordered) != 67:
        raise ValueError("the frozen split requires exactly 67 strict base archives")
    return {
        archive_id: "development" if index < 10 else "validation" if index < 20 else "test"
        for index, archive_id in enumerate(ordered)
    }


def _signal_index(base_id: str, rotation: int, condition: str, active: int) -> int | None:
    if condition == "uniform":
        return None
    true_accuracy = {"known": 1.0, "high": .75, "medium": .50, "wrong60": .20}[condition]
    if _unit_interval(base_id, rotation, condition, "correct") < true_accuracy:
        return active
    other = [index for index in range(3) if index != active]
    selected = int(_unit_interval(base_id, rotation, condition, "wrong") * len(other))
    return other[min(selected, len(other) - 1)]


def _source_prior(source_ids: Sequence[str], signal: int | None, condition: str) -> Dict[str, float]:
    if condition == "uniform":
        return {source: 1.0 / 3.0 for source in source_ids}
    accuracy = {"known": 1.0, "high": .75, "medium": .50, "wrong60": .60}[condition]
    remainder = (1.0 - accuracy) / 2.0
    return {source: accuracy if index == signal else remainder
            for index, source in enumerate(source_ids)}


def _public_memory(parsed: Mapping[str, object], cited_mapping: Mapping[str, str]) -> Dict[str, object]:
    return {
        "lesson": str(parsed["lesson"]),
        "expected_outcome": str(parsed["expected_outcome"]),
        "cited_memory_ids": [cited_mapping[str(value)] for value in parsed["cited_memory_ids"]
                             if str(value) in cited_mapping],
    }


def build_composite_ledgers(
    generation: Mapping[str, object], evaluator_sha256: str,
    implementation_sha256: Mapping[str, str] | None = None,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    records = generation.get("archives")
    if not isinstance(records, list) or len(records) != 67:
        raise ValueError("67 strict external generation records are required")
    split_by_id = split_assignments(records)
    public_rows, private_rows = [], []
    for record in records:
        base = record["base_archive"]
        base_id = str(record["archive_id"])
        branches = base["branches"][:3]
        if len(branches) != 3 or any(len(branch["memories"]) != 3 for branch in branches):
            raise ValueError("each composite requires three depth-three branches")
        source_ids = tuple(_opaque(base_id, "source", index) for index in range(3))
        raw_mapping = {
            str(memory["memory_id"]): _opaque(base_id, "branch", branch_index, depth_index)
            for branch_index, branch in enumerate(branches)
            for depth_index, memory in enumerate(branch["memories"])
        }
        candidate_ids = tuple(
            raw_mapping[str(memory["memory_id"])]
            for branch in branches for memory in branch["memories"]
        )
        edges = []
        for branch_index, branch in enumerate(branches):
            nodes = [raw_mapping[str(memory["memory_id"])] for memory in branch["memories"]]
            edges.append([source_ids[branch_index], nodes[0]])
            edges.extend([[nodes[index], nodes[index + 1]] for index in range(2)])
        for rotation in range(3):
            active_source = source_ids[rotation]
            memories: Dict[str, Dict[str, object]] = {}
            origin_text = str(base["invalid_source"]["lesson"])
            for source in source_ids:
                memories[source] = {
                    "lesson": origin_text,
                    "expected_outcome": str(base["invalid_source"]["expected_outcome"]),
                    "cited_memory_ids": [],
                }
            affected = []
            policy_success = base["policy_success"]
            for branch_index, branch in enumerate(branches):
                for memory in branch["memories"]:
                    raw_id = str(memory["memory_id"])
                    factual = memory["factual"]["parsed"]
                    counterfactual = memory["counterfactual"]["parsed"]
                    selected = factual if branch_index == rotation else counterfactual
                    node = raw_mapping[raw_id]
                    memories[node] = _public_memory(selected, raw_mapping)
                    if branch_index == rotation and bool(
                        policy_success.get(factual["recommended_policy_id"], False)
                    ) != bool(policy_success.get(counterfactual["recommended_policy_id"], False)):
                        affected.append(node)
            created_at = {source: index for index, source in enumerate(source_ids)}
            created_at.update({node: index + 3 for index, node in enumerate(candidate_ids)})
            for condition in CONDITIONS:
                signal_index = _signal_index(base_id, rotation, condition, rotation)
                prior = _source_prior(source_ids, signal_index, condition)
                archive_id = "mo_" + hashlib.sha256(
                    f"{PROTOCOL}|{base_id}|{rotation}|{condition}".encode()
                ).hexdigest()[:18]
                public_rows.append({
                    "archive_id": archive_id,
                    "base_archive_key": "b_" + hashlib.sha256(
                        f"{PROTOCOL}|cluster|{base_id}".encode()
                    ).hexdigest()[:16],
                    "suite": "libero_90",
                    "split": split_by_id[base_id],
                    "condition": condition,
                    "source_ids": list(source_ids),
                    "source_prior": prior,
                    "forensic_signal_source_id": (
                        source_ids[signal_index] if signal_index is not None else None
                    ),
                    "candidate_ids": list(candidate_ids),
                    "formation_edges": edges,
                    "memories": memories,
                    "created_at": created_at,
                    "branch_regimes": [str(branch["regime"]) for branch in branches],
                    "target_language": str(base["target"]["target_language"]),
                })
                private_rows.append({
                    "archive_id": archive_id,
                    "active_source_id": active_source,
                    "affected_ids": affected,
                    "base_archive_id": base_id,
                    "rotation": rotation,
                    "signal_correct": signal_index == rotation if signal_index is not None else None,
                })
    public = {
        "protocol": f"{PROTOCOL}/public",
        "base_generation_sha256": canonical_hash(generation),
        "evaluator_sha256_before_label_join": evaluator_sha256,
        "implementation_sha256_before_label_join": dict(implementation_sha256 or {}),
        "archive_count": len(public_rows),
        "base_archive_count": 67,
        "archives": public_rows,
    }
    private = {
        "protocol": f"{PROTOCOL}/private",
        "evaluator_sha256_before_label_join": evaluator_sha256,
        "public_payload_sha256": canonical_hash(public),
        "archive_count": len(private_rows),
        "archives": private_rows,
    }
    return public, private


@dataclass(frozen=True)
class CompositeArchiveView:
    archive_id: str
    source_id: str
    candidate_ids: Tuple[str, ...]
    true_edges: frozenset[Tuple[str, str]]
    memories: Mapping[str, Mapping[str, object]]
    created_at: Mapping[str, int]


def build_joint_posterior(
    public: Mapping[str, object], parameters: LocalTransitionParameters,
) -> LatentSourcePosterior:
    candidates = tuple(str(value) for value in public["candidate_ids"])
    source_ids = tuple(str(value) for value in public["source_ids"])
    prior = {str(key): float(value) for key, value in public["source_prior"].items()}
    edges = frozenset((str(left), str(right)) for left, right in public["formation_edges"])
    worlds: list[LatentSourceWorld] = []
    for source in source_ids:
        if prior[source] <= 0.0:
            continue
        view = CompositeArchiveView(
            str(public["archive_id"]), source, candidates, edges,
            public["memories"],
            {str(key): int(value) for key, value in public["created_at"].items()},
        )
        posterior = build_local_directional_posterior(view, parameters)  # type: ignore[arg-type]
        worlds.extend(
            LatentSourceWorld(source, world.affected_ids, prior[source] * world.weight)
            for world in posterior.worlds
        )
    return LatentSourcePosterior(candidates, source_ids, tuple(worlds)).normalize()


def project_joint_posterior(
    posterior: LatentSourcePosterior, allowed: Sequence[str],
) -> LatentSourcePosterior:
    keep = frozenset(allowed)
    masses: Dict[Tuple[str, frozenset[str]], float] = {}
    for world in posterior.worlds:
        key = (world.source_id, world.affected_ids & keep)
        masses[key] = masses.get(key, 0.0) + world.weight
    return LatentSourcePosterior(
        tuple(allowed), posterior.source_ids,
        tuple(LatentSourceWorld(source, affected, weight)
              for (source, affected), weight in masses.items()),
    ).normalize()


def truth_in_support(posterior: LatentSourcePosterior, source: str, affected: Sequence[str]) -> bool:
    labels = frozenset(affected)
    return any(world.source_id == source and world.affected_ids == labels
               for world in posterior.worlds)
