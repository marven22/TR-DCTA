"""Paper-level reconstruction of the MemAudit scoring algorithm.

The authors of MemAudit (arXiv:2605.23723v1) did not release code with the
May 2026 submission.  This module implements equations (7), (8), and (10) and
Algorithm 1 while keeping task-specific replay, semantic similarity, and NLI
consistency outside the core.  That separation makes otherwise underspecified
choices visible to an evaluator instead of silently baking them into the
method.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class HarmfulEvent:
    """A logged harmful event and the memory IDs retrieved for it."""

    event_id: str
    observed_harm: float
    retrieved_memory_ids: tuple[str, ...]


@dataclass(frozen=True)
class MemAuditParameters:
    """Parameters explicitly fixed for a MemAudit reconstruction."""

    alpha: float = 0.6

    def __post_init__(self) -> None:
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError("alpha must lie in [0, 1]")


@dataclass(frozen=True)
class MemAuditScore:
    memory_id: str
    cmis: float
    cas: float
    normalized_cmis: float
    normalized_cas: float
    detoxification_score: float


CounterfactualReplay = Callable[[HarmfulEvent, str], float]


def _validate_memory_ids(memory_ids: Sequence[str]) -> tuple[str, ...]:
    ordered = tuple(memory_ids)
    if not ordered:
        raise ValueError("at least one memory is required")
    if len(set(ordered)) != len(ordered):
        raise ValueError("memory IDs must be unique")
    return ordered


def minmax_normalize(values: Mapping[str, float]) -> dict[str, float]:
    """Normalize to [0, 1], returning zeros for a constant signal.

    MemAudit states that CMIS and CAS are normalized but does not specify the
    normalization operator in v1.  Min-max normalization is therefore an
    explicit reconstruction choice, not an author-confirmed detail.
    """

    if not values:
        return {}
    low = min(values.values())
    high = max(values.values())
    if high == low:
        return {key: 0.0 for key in values}
    scale = high - low
    return {key: (value - low) / scale for key, value in values.items()}


def counterfactual_memory_influence(
    memory_ids: Sequence[str],
    events: Iterable[HarmfulEvent],
    replay_without: CounterfactualReplay,
) -> tuple[dict[str, float], int]:
    """Compute aggregate CMIS from equation (7) and Algorithm 1.

    Only memories retrieved for an event receive an intervention, exactly as
    described by Algorithm 1.  The callback must return the harm after removing
    the specified memory and rerunning retrieval plus agent generation.
    """

    ordered = _validate_memory_ids(memory_ids)
    allowed = set(ordered)
    scores = {memory_id: 0.0 for memory_id in ordered}
    replay_count = 0
    for event in events:
        if event.observed_harm < 0.0:
            raise ValueError("harm scores must be non-negative")
        if len(set(event.retrieved_memory_ids)) != len(event.retrieved_memory_ids):
            raise ValueError("retrieved memory IDs must be unique within an event")
        for memory_id in event.retrieved_memory_ids:
            if memory_id not in allowed:
                raise ValueError(f"event references unknown memory: {memory_id}")
            counterfactual_harm = replay_without(event, memory_id)
            if counterfactual_harm < 0.0:
                raise ValueError("counterfactual harm scores must be non-negative")
            scores[memory_id] += event.observed_harm - counterfactual_harm
            replay_count += 1
    return scores, replay_count


def consistency_anomaly_scores(
    memory_ids: Sequence[str],
    neighborhoods: Mapping[str, Sequence[str]],
    semantic_similarity: Callable[[str, str], float],
    inconsistency_weight: Callable[[str, str], float],
) -> dict[str, float]:
    """Compute CAS from equation (8) on a caller-supplied memory graph."""

    ordered = _validate_memory_ids(memory_ids)
    allowed = set(ordered)
    scores: dict[str, float] = {}
    for memory_id in ordered:
        total = 0.0
        for neighbor in neighborhoods.get(memory_id, ()):
            if neighbor not in allowed:
                raise ValueError(f"unknown neighbor {neighbor} for {memory_id}")
            if neighbor == memory_id:
                continue
            similarity = semantic_similarity(memory_id, neighbor)
            inconsistency = inconsistency_weight(memory_id, neighbor)
            if similarity < 0.0 or inconsistency < 0.0:
                raise ValueError("similarity and inconsistency must be non-negative")
            total += inconsistency * similarity
        scores[memory_id] = total
    return scores


def memaudit_rank(
    memory_ids: Sequence[str],
    events: Iterable[HarmfulEvent],
    replay_without: CounterfactualReplay,
    neighborhoods: Mapping[str, Sequence[str]],
    semantic_similarity: Callable[[str, str], float],
    inconsistency_weight: Callable[[str, str], float],
    parameters: MemAuditParameters = MemAuditParameters(),
) -> tuple[tuple[MemAuditScore, ...], int]:
    """Run MemAudit's batch score fusion and return a deterministic ranking."""

    ordered = _validate_memory_ids(memory_ids)
    cmis, replay_count = counterfactual_memory_influence(
        ordered, events, replay_without
    )
    cas = consistency_anomaly_scores(
        ordered, neighborhoods, semantic_similarity, inconsistency_weight
    )
    normalized_cmis = minmax_normalize(cmis)
    normalized_cas = minmax_normalize(cas)
    scores = tuple(
        MemAuditScore(
            memory_id=memory_id,
            cmis=cmis[memory_id],
            cas=cas[memory_id],
            normalized_cmis=normalized_cmis[memory_id],
            normalized_cas=normalized_cas[memory_id],
            detoxification_score=(
                parameters.alpha * normalized_cmis[memory_id]
                + (1.0 - parameters.alpha) * normalized_cas[memory_id]
            ),
        )
        for memory_id in ordered
    )
    # Lexicographic IDs make ties reproducible without importing creation-order
    # or private-label information into the paper-level method.
    return tuple(sorted(
        scores, key=lambda score: (-score.detoxification_score, score.memory_id)
    )), replay_count

