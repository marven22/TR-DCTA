"""Leakage-safe helpers for the Meta-World post-audit recovery study."""

from __future__ import annotations

from typing import Mapping, Sequence

from .publication_v2_archive import public_memory


def parsed(record: Mapping[str, object]) -> Mapping[str, object]:
    value = record.get("parsed")
    if not isinstance(value, dict):
        raise ValueError("writer record has no parsed memory")
    return value


def task_variant_maps(
    generated: Mapping[str, object], rotation: int,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]],
           dict[str, str], dict[str, str]]:
    """Return corrupted/clean public memories and their hidden policy maps.

    This mirrors publication_v2_archive.materialize_task. Keeping it here makes
    the behavioral evaluation's clean reference explicit and independently
    testable.
    """

    if rotation not in (0, 1, 2):
        raise ValueError("rotation must be 0, 1, or 2")
    graph = generated["graph"]
    branches = [[str(node) for node in branch]
                for branch in graph["branch_ids"]]  # type: ignore[index]
    candidate_ids = [str(node) for node in graph["candidate_ids"]]  # type: ignore[index]

    branch_records = {
        str(item["memory_id"]): item
        for branch in generated["branches"]  # type: ignore[index]
        for item in branch["memories"]
    }
    shared_records = {
        str(item["memory_id"]): item
        for item in generated["shared_memories"]  # type: ignore[index]
    }

    corrupted: dict[str, dict[str, object]] = {}
    clean: dict[str, dict[str, object]] = {}
    corrupted_policy: dict[str, str] = {}
    clean_policy: dict[str, str] = {}
    for branch_index, nodes in enumerate(branches):
        for node in nodes:
            record = branch_records[node]
            clean_value = parsed(record["counterfactual"])
            corrupt_value = parsed(
                record["factual"] if branch_index == rotation
                else record["counterfactual"]
            )
            corrupted[node] = public_memory(corrupt_value)
            clean[node] = public_memory(clean_value)
            corrupted_policy[node] = str(corrupt_value["recommended_policy_id"])
            clean_policy[node] = str(clean_value["recommended_policy_id"])

    for node, record in shared_records.items():
        clean_value = parsed(record["variants"]["clean"])
        corrupt_value = parsed(record["variants"][f"active_{rotation}"])
        corrupted[node] = public_memory(corrupt_value)
        clean[node] = public_memory(clean_value)
        corrupted_policy[node] = str(corrupt_value["recommended_policy_id"])
        clean_policy[node] = str(clean_value["recommended_policy_id"])

    if set(corrupted) != set(candidate_ids) or set(clean) != set(candidate_ids):
        raise ValueError("generated memories do not match candidate IDs")
    return corrupted, clean, corrupted_policy, clean_policy


def quarantined_ids(
    replayed_ids: Sequence[str], harmful_ids: Sequence[str],
) -> tuple[str, ...]:
    """Quarantine exactly the audited memories whose replay failed."""

    harmful = set(map(str, harmful_ids))
    return tuple(str(node) for node in replayed_ids if str(node) in harmful)


def selected_success(
    selected_id: str,
    policy_by_memory: Mapping[str, str],
    success_by_policy: Mapping[str, bool],
) -> bool:
    if selected_id not in policy_by_memory:
        raise ValueError(f"unknown selected memory: {selected_id}")
    policy = policy_by_memory[selected_id]
    if policy not in success_by_policy:
        raise ValueError(f"policy has no verified outcome: {policy}")
    return bool(success_by_policy[policy])


def aggregate_recovery(before_success: float, after_success: float,
                       clean_success: float) -> float | None:
    """Fraction of the aggregate clean-reference deficit repaired."""

    denominator = clean_success - before_success
    if denominator <= 0:
        return None
    return (after_success - before_success) / denominator


def forced_exposure_ranking(
    anchor_id: str, candidate_ids: Sequence[str], scores: Mapping[str, float],
    created_at: Mapping[str, int],
) -> tuple[str, ...]:
    """Put one fixed exposure first, then use ordinary semantic retrieval.

    The same anchor and fallback ordering can be shared by every audit method.
    """

    candidates = list(map(str, candidate_ids))
    if anchor_id not in candidates:
        raise ValueError("exposure anchor is not a candidate memory")
    if any(node not in scores for node in candidates):
        raise ValueError("missing semantic score")
    remainder = sorted(
        (node for node in candidates if node != anchor_id),
        key=lambda node: (-scores[node], int(created_at[node]), node),
    )
    return (anchor_id, *remainder)


def first_survivor(ranking: Sequence[str], removed_ids: Sequence[str]) -> str:
    removed = set(map(str, removed_ids))
    for node in ranking:
        if node not in removed:
            return str(node)
    raise ValueError("quarantine removed every candidate memory")
