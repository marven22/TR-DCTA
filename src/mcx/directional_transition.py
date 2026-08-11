"""Directional causal-transition posterior for source-conditioned auditing.

The model is deliberately restricted: the observed formation DAG is treated as
complete, source-conditioned effects have no spontaneous positives, and an
affected parent transmits independently across each outgoing edge.  The module
provides exact finite-world inference for small/medium DAGs and development
policies; it is not the final scalable method.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import itertools
import math
from typing import Dict, FrozenSet, Mapping, Sequence, Tuple

from .memory_libero_v041 import V041Archive
from .memoryarena_v6 import token_jaccard


@dataclass(frozen=True)
class GaussianEmission:
    affected_mean: float
    affected_variance: float
    clean_mean: float
    clean_variance: float
    affected_count: int
    clean_count: int


@dataclass(frozen=True)
class TransitionParameters:
    root_theta: float
    single_theta: float
    merge_theta: float
    emission: GaussianEmission


@dataclass(frozen=True)
class LocalTransitionParameters:
    """Logistic conditional transition using local parent-child evidence."""
    intercept: float
    root_weight: float
    merge_weight: float
    similarity_weight: float
    extra_parent_weight: float
    l2: float
    training_rows: int


@dataclass(frozen=True)
class CascadeWorld:
    affected_ids: FrozenSet[str]
    weight: float


@dataclass(frozen=True)
class DirectionalPosterior:
    candidates: Tuple[str, ...]
    worlds: Tuple[CascadeWorld, ...]

    def __post_init__(self):
        if not self.candidates or not self.worlds:
            raise ValueError("posterior requires candidates and worlds")
        if sum(world.weight for world in self.worlds) <= 0:
            raise ValueError("posterior mass must be positive")

    def normalize(self) -> "DirectionalPosterior":
        total = sum(world.weight for world in self.worlds)
        return DirectionalPosterior(
            self.candidates,
            tuple(CascadeWorld(world.affected_ids, world.weight / total)
                  for world in self.worlds if world.weight > 0),
        )

    def marginal(self, node: str) -> float:
        return sum(world.weight for world in self.worlds
                   if node in world.affected_ids) / sum(w.weight for w in self.worlds)

    def condition(self, node: str, label: int) -> "DirectionalPosterior | None":
        kept = tuple(world for world in self.worlds
                     if int(node in world.affected_ids) == label)
        if not kept:
            return None
        return DirectionalPosterior(self.candidates, kept).normalize()


def _logit_similarity(archive: V041Archive, node: str) -> float:
    value = token_jaccard(
        str(archive.memories[archive.source_id]["lesson"]),
        str(archive.memories[node]["lesson"]),
    )
    value = min(max(value, .01), .99)
    return math.log(value / (1.0 - value))


def _moments(values: Sequence[float]) -> Tuple[float, float]:
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return mean, max(variance, .25)


def _parents(archive: V041Archive) -> Dict[str, Tuple[str, ...]]:
    result: Dict[str, list[str]] = {node: [] for node in archive.memories}
    for parent, child in archive.true_edges:
        result[child].append(parent)
    return {node: tuple(sorted(values)) for node, values in result.items()}


def _category(archive: V041Archive, node: str, parents: Mapping[str, Tuple[str, ...]]) -> str:
    values = parents[node]
    if archive.source_id in values:
        return "root"
    return "merge" if len(values) > 1 else "single"


def _fit_theta(observations: Sequence[Tuple[int, int]]) -> float:
    """Grid MAP for noisy-OR observations `(affected_parent_count, label)`."""
    if not observations:
        return .5
    best = None
    for step in range(1, 100):
        theta = step / 100.0
        # Weak Beta(2,2) regularization prevents boundary estimates.
        score = math.log(theta) + math.log(1.0 - theta)
        for count, label in observations:
            probability = 1.0 - (1.0 - theta) ** count
            score += math.log(probability if label else 1.0 - probability)
        candidate = (score, -abs(theta - .5), theta)
        if best is None or candidate > best:
            best = candidate
    return best[2]  # type: ignore[index]


def fit_transition_parameters(archives: Sequence[V041Archive]) -> TransitionParameters:
    if not archives:
        raise ValueError("at least one training archive is required")
    observations = {"root": [], "single": [], "merge": []}
    affected_values, clean_values = [], []
    for archive in archives:
        parents = _parents(archive)
        for node in archive.candidate_ids:
            parent_count = sum(
                parent == archive.source_id or parent in archive.affected_ids
                for parent in parents[node]
            )
            label = int(node in archive.affected_ids)
            if parent_count == 0:
                if label:
                    raise ValueError("affected node has no affected parent")
            else:
                observations[_category(archive, node, parents)].append((parent_count, label))
            (affected_values if label else clean_values).append(_logit_similarity(archive, node))
    if len(affected_values) < 2 or len(clean_values) < 2:
        raise ValueError("emission calibration requires both classes")
    am, av = _moments(affected_values); cm, cv = _moments(clean_values)
    return TransitionParameters(
        _fit_theta(observations["root"]),
        _fit_theta(observations["single"]),
        _fit_theta(observations["merge"]),
        GaussianEmission(am, av, cm, cv, len(affected_values), len(clean_values)),
    )


def _normal_logpdf(value: float, mean: float, variance: float) -> float:
    return -.5 * (math.log(2 * math.pi * variance) + (value - mean) ** 2 / variance)


def _pair_logit_similarity(archive: V041Archive, parent: str, child: str) -> float:
    value = token_jaccard(
        str(archive.memories[parent]["lesson"]), str(archive.memories[child]["lesson"])
    )
    value = min(max(value, .01), .99)
    return math.log(value / (1.0 - value))


def _solve_linear(matrix: Sequence[Sequence[float]], target: Sequence[float]) -> list[float]:
    size = len(target); augmented = [list(matrix[r]) + [target[r]] for r in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-10:
            augmented[pivot][column] += 1e-6
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [left-factor*right
                              for left,right in zip(augmented[row], augmented[column])]
    return [augmented[row][-1] for row in range(size)]


def _sigmoid(value: float) -> float:
    value = max(min(value, 35.0), -35.0)
    return 1.0 / (1.0 + math.exp(-value))


def _local_features(
    archive: V041Archive, node: str, affected_parents: Sequence[str],
    all_parents: Sequence[str],
) -> Tuple[float, ...]:
    root = float(archive.source_id in affected_parents)
    merge = float(len(all_parents) > 1)
    similarity = max(_pair_logit_similarity(archive, parent, node)
                     for parent in affected_parents)
    return (1.0, root, merge, similarity, float(len(affected_parents)-1))


def fit_local_transition_parameters(
    archives: Sequence[V041Archive], *, l2: float = .1,
) -> LocalTransitionParameters:
    rows = []
    for archive in archives:
        parents = _parents(archive)
        for node in archive.candidate_ids:
            affected_parents = tuple(
                parent for parent in parents[node]
                if parent == archive.source_id or parent in archive.affected_ids
            )
            if not affected_parents:
                if node in archive.affected_ids:
                    raise ValueError("affected node has no affected parent")
                continue
            rows.append((_local_features(
                archive, node, affected_parents, parents[node]
            ), int(node in archive.affected_ids)))
    if not rows or len({label for _,label in rows}) < 2:
        raise ValueError("local transition fit requires both labels")
    prevalence = sum(label for _,label in rows)/len(rows)
    weights = [math.log(prevalence/(1-prevalence)), 0.0, 0.0, 0.0, 0.0]
    for _ in range(50):
        gradient = [0.0]*5; hessian = [[0.0]*5 for _ in range(5)]
        for features,label in rows:
            probability = _sigmoid(sum(w*x for w,x in zip(weights,features)))
            for i in range(5):
                gradient[i] += (probability-label)*features[i]
                for j in range(5):
                    hessian[i][j] += probability*(1-probability)*features[i]*features[j]
        for i in range(1,5):
            gradient[i] += l2*weights[i]; hessian[i][i] += l2
        hessian[0][0] += 1e-6
        step = _solve_linear(hessian, gradient)
        proposal = [left-right for left,right in zip(weights,step)]
        if max(abs(left-right) for left,right in zip(weights,proposal)) < 1e-8:
            weights = proposal; break
        weights = proposal
    return LocalTransitionParameters(*weights, l2, len(rows))


def build_local_directional_posterior(
    archive: V041Archive, parameters: LocalTransitionParameters,
) -> DirectionalPosterior:
    """Exact posterior for the local logistic transition factorization."""
    parents = _parents(archive)
    candidates = tuple(sorted(archive.candidate_ids, key=archive.created_at.get))
    weights = (
        parameters.intercept, parameters.root_weight, parameters.merge_weight,
        parameters.similarity_weight, parameters.extra_parent_weight,
    )
    log_worlds = []

    def visit(offset: int, affected: set[str], log_weight: float):
        if offset == len(candidates):
            log_worlds.append((frozenset(affected), log_weight)); return
        node = candidates[offset]
        affected_parents = tuple(
            parent for parent in parents[node]
            if parent == archive.source_id or parent in affected
        )
        if not affected_parents:
            visit(offset+1, affected, log_weight); return
        features = _local_features(archive, node, affected_parents, parents[node])
        probability = _sigmoid(sum(w*x for w,x in zip(weights,features)))
        visit(offset+1, affected, log_weight+math.log(1-probability))
        affected.add(node)
        visit(offset+1, affected, log_weight+math.log(probability))
        affected.remove(node)

    visit(0,set(),0.0)
    maximum = max(value for _,value in log_worlds)
    raw = [(labels,math.exp(value-maximum)) for labels,value in log_worlds]
    total = sum(value for _,value in raw)
    return DirectionalPosterior(candidates, tuple(
        CascadeWorld(labels,value/total) for labels,value in raw
    ))


def build_directional_posterior(
    archive: V041Archive, parameters: TransitionParameters,
) -> DirectionalPosterior:
    parents = _parents(archive)
    candidates = tuple(sorted(archive.candidate_ids, key=archive.created_at.get))
    emissions = {}
    for node in candidates:
        value = _logit_similarity(archive, node); e = parameters.emission
        emissions[node] = (
            _normal_logpdf(value, e.clean_mean, e.clean_variance),
            _normal_logpdf(value, e.affected_mean, e.affected_variance),
        )
    theta = {"root": parameters.root_theta,
             "single": parameters.single_theta, "merge": parameters.merge_theta}
    log_worlds = []

    def visit(offset: int, affected: set[str], log_weight: float):
        if offset == len(candidates):
            log_worlds.append((frozenset(affected), log_weight)); return
        node = candidates[offset]
        count = sum(parent == archive.source_id or parent in affected
                    for parent in parents[node])
        if count == 0:
            visit(offset + 1, affected, log_weight + emissions[node][0]); return
        probability = 1.0 - (1.0 - theta[_category(archive, node, parents)]) ** count
        visit(offset + 1, affected,
              log_weight + math.log(1.0 - probability) + emissions[node][0])
        affected.add(node)
        visit(offset + 1, affected,
              log_weight + math.log(probability) + emissions[node][1])
        affected.remove(node)

    visit(0, set(), 0.0)
    maximum = max(weight for _, weight in log_worlds)
    raw = [(labels, math.exp(weight - maximum)) for labels, weight in log_worlds]
    total = sum(weight for _, weight in raw)
    return DirectionalPosterior(
        candidates,
        tuple(CascadeWorld(labels, weight / total) for labels, weight in raw),
    )


def greedy_choice(posterior: DirectionalPosterior, remaining: Sequence[str]) -> str:
    return min(remaining, key=lambda node: (-posterior.marginal(node), node))


def two_step_choice(posterior: DirectionalPosterior, remaining: Sequence[str]) -> str:
    """Exact two-query Bayes value, used in receding-horizon form."""
    if len(remaining) == 1:
        return remaining[0]
    best = None
    for node in remaining:
        probability = posterior.marginal(node)
        others = tuple(item for item in remaining if item != node)
        value = probability
        for label, outcome_probability in ((1, probability), (0, 1.0 - probability)):
            if outcome_probability <= 0:
                continue
            conditioned = posterior.condition(node, label)
            if conditioned is not None:
                value += outcome_probability * max(conditioned.marginal(item) for item in others)
        candidate = (value, node)
        if best is None or value > best[0] + 1e-12 or (
            abs(value - best[0]) <= 1e-12 and node < best[1]
        ):
            best = candidate
    return best[1]  # type: ignore[index]


def risk_choice(
    posterior: DirectionalPosterior, remaining: Sequence[str],
    weights: Mapping[str, float] | None = None,
) -> str:
    """DCTA-Risk: current risk plus positive-conditioned posterior uplift."""
    harm = weights or {node: 1.0 for node in remaining}
    best = None
    for node in remaining:
        probability = posterior.marginal(node)
        positive = posterior.condition(node, 1)
        impact = harm[node]
        if positive is not None:
            for other in remaining:
                if other == node:
                    continue
                impact += harm[other] * max(
                    0.0, positive.marginal(other) - posterior.marginal(other)
                )
        score = probability * impact
        candidate = (score, node)
        if best is None or score > best[0] + 1e-12 or (
            abs(score - best[0]) <= 1e-12 and node < best[1]
        ):
            best = candidate
    return best[1]  # type: ignore[index]


def run_directional_policy(
    posterior: DirectionalPosterior, affected_ids: FrozenSet[str], budget: int,
    *, horizon: int = 1,
) -> Tuple[str, ...]:
    if horizon not in (1, 2):
        raise ValueError("implemented directional horizons are one and two")
    current = posterior; remaining = list(posterior.candidates); replayed = []
    for _ in range(min(budget, len(remaining))):
        chosen = (greedy_choice(current, remaining) if horizon == 1
                  else two_step_choice(current, remaining))
        replayed.append(chosen); remaining.remove(chosen)
        conditioned = current.condition(chosen, int(chosen in affected_ids))
        if conditioned is None:
            raise ValueError("observed label has zero probability under model")
        current = conditioned
    return tuple(replayed)


def run_directional_risk_policy(
    posterior: DirectionalPosterior, affected_ids: FrozenSet[str], budget: int,
    *, weights: Mapping[str, float] | None = None,
) -> Tuple[str, ...]:
    """Run the locked DCTA-Risk acquisition with full-history conditioning."""
    current = posterior
    remaining = list(posterior.candidates)
    replayed = []
    for _ in range(min(budget, len(remaining))):
        chosen = risk_choice(current, remaining, weights)
        replayed.append(chosen)
        remaining.remove(chosen)
        conditioned = current.condition(chosen, int(chosen in affected_ids))
        if conditioned is None:
            raise ValueError("observed label has zero probability under model")
        current = conditioned
    return tuple(replayed)


def exact_policy_value(
    posterior: DirectionalPosterior, budget: int,
) -> Tuple[float, str | None]:
    """Exponential Bayes-optimal active-search oracle for small DAGs."""
    if len(posterior.candidates) > 12:
        raise ValueError("exact oracle is restricted to at most 12 candidates")
    original = posterior.worlds

    @lru_cache(maxsize=None)
    def solve(possible: Tuple[int, ...], remaining: Tuple[str, ...], left: int):
        if left <= 0 or not remaining:
            return 0.0, None
        total = sum(original[index].weight for index in possible)
        best_value, best_node = -1.0, None
        for node in remaining:
            positive = tuple(i for i in possible if node in original[i].affected_ids)
            negative = tuple(i for i in possible if node not in original[i].affected_ids)
            probability = sum(original[i].weight for i in positive) / total
            next_remaining = tuple(item for item in remaining if item != node)
            value = probability
            if positive:
                continuation, _ = solve(positive, next_remaining, left - 1)
                value += probability * continuation
            if negative:
                continuation, _ = solve(negative, next_remaining, left - 1)
                value += (1.0 - probability) * continuation
            if value > best_value + 1e-12 or (
                abs(value - best_value) <= 1e-12 and (best_node is None or node < best_node)
            ):
                best_value, best_node = value, node
        return best_value, best_node

    return solve(tuple(range(len(original))), posterior.candidates,
                 min(budget, len(posterior.candidates)))


def expected_policy_value(
    posterior: DirectionalPosterior, budget: int, *, horizon: int,
) -> float:
    """Expected discoveries of an implemented policy under its own posterior."""
    return sum(
        world.weight * len(
            set(run_directional_policy(
                posterior, world.affected_ids, budget, horizon=horizon
            )) & world.affected_ids
        )
        for world in posterior.worlds
    )
