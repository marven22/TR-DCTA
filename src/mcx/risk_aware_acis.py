"""Three-signal, calibrated, and risk-aware ACIS development methods."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
from typing import Dict, Iterable, Mapping, Sequence, Set, Tuple

from .memoryarena_v6 import DiscoveryCase, ObservableMemory, token_jaccard


@dataclass(frozen=True)
class ThreeSignals:
    provenance: float
    formation_task: float
    content: float

    def vector(self) -> Tuple[float, float, float]:
        return self.provenance, self.formation_task, self.content


@dataclass(frozen=True)
class LogisticCalibrator:
    intercept: float
    provenance_weight: float
    formation_task_weight: float
    content_weight: float

    def probability(self, signals: ThreeSignals) -> float:
        z = (
            self.intercept
            + self.provenance_weight * signals.provenance
            + self.formation_task_weight * signals.formation_task
            + self.content_weight * signals.content
        )
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        exp_z = math.exp(z)
        return exp_z / (1.0 + exp_z)

    def as_dict(self) -> Dict[str, float]:
        return {
            "intercept": self.intercept,
            "provenance": self.provenance_weight,
            "formation_task": self.formation_task_weight,
            "content": self.content_weight,
        }


class ThreeSignalIndex:
    """Case-local cache for repeatedly scoring candidate/anchor pairs."""

    def __init__(self, case: DiscoveryCase) -> None:
        self.case = case
        self.by_id = {memory.memory_id: memory for memory in case.memories}
        self._task_cache: Dict[Tuple[str, str], float] = {}
        self._content_cache: Dict[Tuple[str, str], float] = {}

    def _similarity(self, left: str, right: str, field: str) -> float:
        key = (left, right) if left <= right else (right, left)
        cache = self._task_cache if field == "formation_context" else self._content_cache
        if key not in cache:
            cache[key] = token_jaccard(
                getattr(self.by_id[left], field), getattr(self.by_id[right], field)
            )
        return cache[key]

    def signals(self, candidate_id: str, anchor_ids: Iterable[str]) -> ThreeSignals:
        candidate = self.by_id[candidate_id]
        anchors = set(anchor_ids)
        if not anchors:
            raise ValueError("three-signal scoring requires at least one anchor")
        provenance = float(any(
            anchor_id in candidate.parent_memory_ids
            or anchor_id in candidate.exposed_memory_ids
            for anchor_id in anchors
        ))
        formation_task = max(
            self._similarity(candidate_id, anchor_id, "formation_context")
            for anchor_id in anchors
        )
        content = max(
            self._similarity(candidate_id, anchor_id, "content")
            for anchor_id in anchors
        )
        return ThreeSignals(provenance, formation_task, content)


def _post_source(case: DiscoveryCase) -> Tuple[ObservableMemory, ...]:
    source = next(item for item in case.memories if item.memory_id == case.source_id)
    return tuple(item for item in case.memories if item.created_at > source.created_at)


def three_signals(
    case: DiscoveryCase, candidate_id: str, anchor_ids: Iterable[str]
) -> ThreeSignals:
    """Compute the three frozen observable signals against an adaptive anchor set."""
    return ThreeSignalIndex(case).signals(candidate_id, anchor_ids)


def _stable_jitter(seed: int, case_id: str, memory_id: str) -> float:
    digest = hashlib.sha256(f"risk|{seed}|{case_id}|{memory_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1) * 1e-9


def oracle_prefix_training_rows(
    case: DiscoveryCase,
) -> Counter[Tuple[float, float, float, int]]:
    """Create training-only rows at successive true-positive anchor prefixes."""
    case.validate()
    by_id = {memory.memory_id: memory for memory in case.memories}
    signal_index = ThreeSignalIndex(case)
    positives = sorted(case.affected_ids, key=lambda node: by_id[node].created_at)
    anchors = {case.source_id}
    rows: Counter[Tuple[float, float, float, int]] = Counter()
    candidates = _post_source(case)
    for next_positive in (*positives, None):
        for candidate in candidates:
            if candidate.memory_id in anchors:
                continue
            signal = signal_index.signals(candidate.memory_id, anchors)
            rows[(*signal.vector(), int(candidate.memory_id in case.affected_ids))] += 1
        if next_positive is not None:
            anchors.add(next_positive)
    return rows


def _solve_linear(matrix: Sequence[Sequence[float]], target: Sequence[float]) -> list[float]:
    size = len(target)
    augmented = [list(matrix[row]) + [target[row]] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            augmented[pivot][column] += 1e-8
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                left - factor * right
                for left, right in zip(augmented[row], augmented[column])
            ]
    return [augmented[row][-1] for row in range(size)]


def fit_monotone_logistic(
    rows: Mapping[Tuple[float, float, float, int], int],
    l2: float = 0.01,
    max_iterations: int = 50,
) -> LogisticCalibrator:
    """Fit a nonnegative-slope logistic model using projected Newton steps."""
    total = sum(rows.values())
    positives = sum(count * label for (*_, label), count in rows.items())
    if not total or positives in {0, total}:
        raise ValueError("logistic calibration requires both classes")
    prevalence = min(max(positives / total, 1e-6), 1 - 1e-6)
    weights = [math.log(prevalence / (1 - prevalence)), 0.0, 0.0, 0.0]

    def loss(values: Sequence[float]) -> float:
        result = 0.0
        for (g, q, c, label), count in rows.items():
            z = values[0] + values[1] * g + values[2] * q + values[3] * c
            result += count * (max(z, 0.0) - label * z + math.log1p(math.exp(-abs(z))))
        result /= total
        return result + 0.5 * l2 * sum(value * value for value in values[1:])

    for _ in range(max_iterations):
        gradient = [0.0] * 4
        hessian = [[0.0] * 4 for _ in range(4)]
        for (g, q, c, label), count in rows.items():
            x = (1.0, g, q, c)
            z = sum(weight * value for weight, value in zip(weights, x))
            probability = 1.0 / (1.0 + math.exp(-max(min(z, 35.0), -35.0)))
            residual = count * (probability - label) / total
            curvature = count * probability * (1.0 - probability) / total
            for left in range(4):
                gradient[left] += residual * x[left]
                for right in range(4):
                    hessian[left][right] += curvature * x[left] * x[right]
        for index in range(1, 4):
            gradient[index] += l2 * weights[index]
            hessian[index][index] += l2
        hessian[0][0] += 1e-8
        step = _solve_linear(hessian, gradient)
        old_loss = loss(weights)
        scale = 1.0
        while scale >= 1e-6:
            proposal = [weights[0] - scale * step[0]] + [
                max(0.0, weights[index] - scale * step[index])
                for index in range(1, 4)
            ]
            if loss(proposal) <= old_loss + 1e-12:
                break
            scale *= 0.5
        change = max(abs(left - right) for left, right in zip(weights, proposal))
        weights = proposal
        if change < 1e-8:
            break
    return LogisticCalibrator(*weights)


def adaptive_three_signal_replay(
    case: DiscoveryCase,
    budget: int,
    method: str,
    calibrator: LogisticCalibrator | None = None,
    seed: int = 42,
) -> Dict[str, object]:
    """Run ACIS-3, ACIS-P, or ACIS-Risk with private labels read only on replay."""
    if method not in {"acis_3", "acis_probability", "acis_impact", "acis_risk"}:
        raise ValueError(f"unknown three-signal method: {method}")
    if method != "acis_3" and calibrator is None:
        raise ValueError(f"{method} requires a fitted calibrator")
    case.validate()
    signal_index = ThreeSignalIndex(case)
    candidates = {memory.memory_id: memory for memory in _post_source(case)}
    anchors: Set[str] = {case.source_id}
    confirmed: Set[str] = set()
    replayed: list[str] = []
    score_log: list[Dict[str, object]] = []
    while len(replayed) < min(budget, len(candidates)):
        remaining = [memory for node, memory in candidates.items() if node not in replayed]
        base_signals = {
            memory.memory_id: signal_index.signals(memory.memory_id, anchors)
            for memory in remaining
        }
        base_probabilities = {
            node: calibrator.probability(signals)  # type: ignore[union-attr]
            for node, signals in base_signals.items()
        } if calibrator else {}

        def score(memory: ObservableMemory) -> Tuple[float, float, float]:
            node = memory.memory_id
            signals = base_signals[node]
            probability = base_probabilities.get(node, 0.0)
            impact = 1.0
            if method == "acis_3":
                acquisition = sum(signals.vector())
            elif method == "acis_probability":
                acquisition = probability
            else:
                positive_anchors = anchors | {node}
                for later in remaining:
                    if later.created_at <= memory.created_at or later.memory_id == node:
                        continue
                    positive_probability = calibrator.probability(  # type: ignore[union-attr]
                        signal_index.signals(later.memory_id, positive_anchors)
                    )
                    impact += max(
                        0.0, positive_probability - base_probabilities[later.memory_id]
                    )
                acquisition = impact if method == "acis_impact" else probability * impact
            acquisition += _stable_jitter(seed, case.case_id, node)
            return acquisition, probability, impact

        scored = sorted(
            ((score(memory), memory.memory_id) for memory in remaining),
            key=lambda item: (-item[0][0], item[1]),
        )
        (acquisition, probability, impact), chosen = scored[0]
        affected = chosen in case.affected_ids
        replayed.append(chosen)
        if affected:
            confirmed.add(chosen)
            anchors.add(chosen)
        score_log.append({
            "step": len(replayed),
            "chosen_id": chosen,
            "acquisition_before_replay": acquisition,
            "probability_before_replay": probability if calibrator else None,
            "impact_before_replay": impact,
            "signals_before_replay": base_signals[chosen].__dict__,
            "replay_affected": affected,
            "confirmed_after_replay": sorted(confirmed),
        })
    return {
        "replayed_ids": replayed,
        "repaired_ids": sorted(confirmed),
        "score_log": score_log,
    }
