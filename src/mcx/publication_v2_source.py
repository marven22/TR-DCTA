"""Observable source-origin prior used by Prob-DCTA publication v2."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping, Sequence


TOKENS = re.compile(r"[a-z0-9]+")


def token_set(value: object) -> set[str]:
    return set(TOKENS.findall(str(value).lower()))


def similarity(left: object, right: object) -> float:
    a, b = token_set(left), token_set(right)
    return len(a & b) / len(a | b) if a or b else 0.0


def memory_text(memory: Mapping[str, object]) -> str:
    return f"{memory.get('lesson', '')} {memory.get('expected_outcome', '')}"


def source_features(archive: Mapping[str, object], source: str) -> tuple[float, ...]:
    memories = archive["memories"]
    target = str(archive["target_language"])
    edges = archive.get("observed_formation_edges", archive.get("formation_edges", ()))
    children: dict[str, list[str]] = {}
    for left, right in edges:
        children.setdefault(str(left), []).append(str(right))
    direct = children.get(source, [])
    reachable, frontier = set(), list(direct)
    while frontier:
        node = frontier.pop()
        if node in reachable:
            continue
        reachable.add(node); frontier.extend(children.get(node, ()))
    source_text = memory_text(memories[source])
    direct_texts = [memory_text(memories[node]) for node in direct]
    reachable_texts = [memory_text(memories[node]) for node in reachable]
    coherence = [
        similarity(memory_text(memories[left]), memory_text(memories[right]))
        for left, right in edges if left == source or left in reachable
        if left in memories and right in memories
    ]
    mean = lambda values: sum(values) / len(values) if values else 0.0
    return (
        similarity(source_text, target),
        mean([similarity(text, target) for text in direct_texts]),
        mean([similarity(text, target) for text in reachable_texts]),
        mean([similarity(source_text, text) for text in reachable_texts]),
        mean(coherence),
        min(len(reachable), 8) / 8.0,
    )


@dataclass(frozen=True)
class SourceEstimator:
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]

    def score(self, features: Sequence[float]) -> float:
        standardized = [(value - mean) / scale for value, mean, scale in zip(
            features, self.means, self.scales
        )]
        value = self.coefficients[0] + sum(
            weight * feature for weight, feature in zip(self.coefficients[1:], standardized)
        )
        value = max(min(value, 35.0), -35.0)
        return 1.0 / (1.0 + math.exp(-value))

    def prior(self, archive: Mapping[str, object], minimum_probability: float = 0.0) -> dict[str, float]:
        sources = [str(value) for value in archive["source_ids"]]
        if not 0.0 <= minimum_probability < 1.0 / len(sources):
            raise ValueError("invalid source-probability floor")
        scores = {source: max(self.score(source_features(archive, source)), 1e-6)
                  for source in sources}
        total = sum(scores.values())
        remaining = 1.0 - minimum_probability * len(sources)
        return {source: minimum_probability + remaining * value / total
                for source, value in scores.items()}


def _solve(matrix: list[list[float]], values: list[float]) -> list[float]:
    size = len(values); augmented = [row[:] + [value] for row, value in zip(matrix, values)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        if abs(divisor) < 1e-12:
            raise ValueError("singular source-estimator fit")
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [left - factor * right for left, right in zip(
                augmented[row], augmented[column]
            )]
    return [augmented[row][-1] for row in range(size)]


def fit_source_estimator(
    rows: Sequence[tuple[Sequence[float], int]], l2: float = 1.0,
) -> SourceEstimator:
    if not rows or {label for _, label in rows} != {0, 1}:
        raise ValueError("source fit requires both classes")
    dimension = len(rows[0][0])
    means = tuple(sum(values[i] for values, _ in rows) / len(rows) for i in range(dimension))
    scales = tuple(max(math.sqrt(sum(
        (values[i] - means[i]) ** 2 for values, _ in rows
    ) / len(rows)), 1e-6) for i in range(dimension))
    design = [(1.0, *[(value - mean) / scale for value, mean, scale in zip(
        values, means, scales
    )]) for values, _ in rows]
    weights = [0.0] * (dimension + 1)
    for _ in range(80):
        gradient = [0.0] * len(weights)
        hessian = [[0.0] * len(weights) for _ in weights]
        for features, (_, label) in zip(design, rows):
            linear = max(min(sum(w * x for w, x in zip(weights, features)), 35.0), -35.0)
            probability = 1.0 / (1.0 + math.exp(-linear))
            for i in range(len(weights)):
                gradient[i] += (probability - label) * features[i]
                for j in range(len(weights)):
                    hessian[i][j] += probability * (1.0 - probability) * features[i] * features[j]
        for i in range(1, len(weights)):
            gradient[i] += l2 * weights[i]; hessian[i][i] += l2
        hessian[0][0] += 1e-8
        step = _solve(hessian, gradient)
        proposal = [left - right for left, right in zip(weights, step)]
        if max(abs(left - right) for left, right in zip(weights, proposal)) < 1e-9:
            weights = proposal; break
        weights = proposal
    return SourceEstimator(means, scales, tuple(weights))
