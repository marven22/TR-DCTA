"""Exact controlled benchmark for full-history directional audit policies.

The benchmark deliberately gives positive-only and full-history policies the
same exact prior.  Their only structural difference is whether negative audit
outcomes are retained when choosing subsequent audits.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import itertools
from typing import Callable, Dict, FrozenSet, Mapping, Sequence, Tuple

from .directional_transition import CascadeWorld, DirectionalPosterior


@dataclass(frozen=True)
class RegimeInstance:
    instance_id: str
    regime: str
    level: int
    posterior: DirectionalPosterior
    harm_weights: Mapping[str, float]
    budget: int = 4


@dataclass(frozen=True)
class PolicyOutcome:
    replayed_ids: Tuple[str, ...]
    discoveries: int
    weighted_utility: float


ProbabilityFunction = Callable[[str, FrozenSet[str]], float]


def enumerate_dag(
    candidates: Sequence[str], probability: ProbabilityFunction,
) -> DirectionalPosterior:
    """Enumerate a binary DAG supplied in topological candidate order."""
    worlds: list[CascadeWorld] = []

    def visit(offset: int, affected: set[str], weight: float) -> None:
        if offset == len(candidates):
            if weight > 0:
                worlds.append(CascadeWorld(frozenset(affected), weight))
            return
        node = candidates[offset]
        p = probability(node, frozenset(affected))
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"invalid probability for {node}: {p}")
        if p < 1.0:
            visit(offset + 1, affected, weight * (1.0 - p))
        if p > 0.0:
            affected.add(node)
            visit(offset + 1, affected, weight * p)
            affected.remove(node)

    visit(0, set(), 1.0)
    return DirectionalPosterior(tuple(candidates), tuple(worlds)).normalize()


def _chain_instance(level: int) -> RegimeInstance:
    candidates = ("a", "b", "a1", "b1", "a2", "b2", "a3", "b3")
    p_a = .62 - .03 * level
    p_b = .42 + .02 * level
    t_a = .90 - .03 * level
    t_b = .76 + .04 * level
    parent = {"a1": "a", "a2": "a1", "a3": "a2",
              "b1": "b", "b2": "b1", "b3": "b2"}

    def probability(node: str, affected: FrozenSet[str]) -> float:
        if node == "a": return p_a
        if node == "b": return p_b
        return (t_a if node.startswith("a") else t_b) if parent[node] in affected else 0.0

    return RegimeInstance(
        f"chain_screening_l{level}", "chain_screening", level,
        enumerate_dag(candidates, probability), {node: 1.0 for node in candidates},
    )


def _exclusive_instance(level: int) -> RegimeInstance:
    candidates = ("a", "b", "c", "a1", "b1", "c1", "a2", "b2", "c2")
    branch_probability = (
        (.46, .34, .20), (.43, .35, .22),
        (.40, .36, .24), (.37, .36, .27),
    )[level]
    transmission = (.92, .87, .82, .77)[level]
    worlds: list[CascadeWorld] = []
    for branch, branch_weight in zip(("a", "b", "c"), branch_probability):
        branch_nodes = (branch, branch + "1", branch + "2")
        # The gateway is certain conditional on the exclusive latent branch;
        # each later step transmits independently along the active chain.
        for first, second in itertools.product((0, 1), repeat=2):
            if second and not first:
                continue
            labels = {branch}
            probability = branch_weight
            probability *= transmission if first else 1.0 - transmission
            if first:
                labels.add(branch_nodes[1])
                probability *= transmission if second else 1.0 - transmission
                if second:
                    labels.add(branch_nodes[2])
            worlds.append(CascadeWorld(frozenset(labels), probability))
    posterior = DirectionalPosterior(candidates, tuple(worlds)).normalize()
    return RegimeInstance(
        f"exclusive_branches_l{level}", "exclusive_branches", level,
        posterior, {node: 1.0 for node in candidates},
    )


def _merge_instance(level: int) -> RegimeInstance:
    candidates = ("a", "b", "d", "a1", "b1", "m", "n", "n1")
    root_p = (.58 - .03 * level, .43 + .02 * level)
    branch_t = (.88 - .03 * level, .76 + .04 * level)
    merge_t = .82 + .03 * level
    downstream_t = .88 - .02 * level

    def probability(node: str, affected: FrozenSet[str]) -> float:
        if node == "a": return root_p[0]
        if node == "b": return root_p[1]
        if node == "d": return .24 + .03 * level
        if node == "a1": return branch_t[0] if "a" in affected else 0.0
        if node == "b1": return branch_t[1] if "b" in affected else 0.0
        if node == "m":
            count = int("a1" in affected) + int("b1" in affected)
            return 1.0 - (1.0 - merge_t) ** count
        if node == "n": return downstream_t if "m" in affected else 0.0
        if node == "n1": return downstream_t if "n" in affected else 0.0
        raise KeyError(node)

    weights = {node: 1.0 for node in candidates}
    weights.update({"m": 1.5, "n": 2.0, "n1": 2.5})
    return RegimeInstance(
        f"noisy_or_merge_l{level}", "noisy_or_merge", level,
        enumerate_dag(candidates, probability), weights,
    )


def _heterogeneous_instance(level: int) -> RegimeInstance:
    candidates = ("a", "b", "c", "a1", "b1", "c1", "a2", "b2", "c2")
    root = {"a": .72 - .03 * level, "b": .48 + .01 * level,
            "c": .30 + .02 * level}
    transition = {"a": .28 + .03 * level, "b": .78 + .02 * level,
                  "c": .94 - .02 * level}
    parent = {branch + "1": branch for branch in "abc"}
    parent.update({branch + "2": branch + "1" for branch in "abc"})

    def probability(node: str, affected: FrozenSet[str]) -> float:
        if node in root: return root[node]
        branch = node[0]
        return transition[branch] if parent[node] in affected else 0.0

    weights = {"a": 1.0, "a1": 1.0, "a2": 1.0,
               "b": 1.0, "b1": 2.0, "b2": 2.5,
               "c": 1.0, "c1": 3.0, "c2": 4.0}
    return RegimeInstance(
        f"heterogeneous_l{level}", "heterogeneous", level,
        enumerate_dag(candidates, probability), weights,
    )


def _independent_instance(level: int) -> RegimeInstance:
    candidates = tuple(f"i{index}" for index in range(8))
    probabilities = tuple(
        min(.82, max(.12, .68 - .07 * index + .01 * level * (-1) ** index))
        for index in range(8)
    )

    def probability(node: str, affected: FrozenSet[str]) -> float:
        del affected
        return probabilities[int(node[1:])]

    weights = {node: 1.0 + .25 * (index % 3) for index, node in enumerate(candidates)}
    return RegimeInstance(
        f"independent_control_l{level}", "independent_control", level,
        enumerate_dag(candidates, probability), weights,
    )


def frozen_instances() -> Tuple[RegimeInstance, ...]:
    builders = (_chain_instance, _exclusive_instance, _merge_instance,
                _heterogeneous_instance, _independent_instance)
    return tuple(builder(level) for builder in builders for level in range(4))


def _risk_score(
    posterior: DirectionalPosterior, node: str, remaining: Sequence[str],
    weights: Mapping[str, float],
) -> float:
    probability = posterior.marginal(node)
    positive = posterior.condition(node, 1)
    impact = weights[node]
    if positive is not None:
        for other in remaining:
            if other == node:
                continue
            uplift = max(0.0, positive.marginal(other) - posterior.marginal(other))
            impact += weights[other] * uplift
    return probability * impact


def run_policy(
    posterior: DirectionalPosterior, true_world: FrozenSet[str], budget: int,
    *, update: str, acquisition: str, weights: Mapping[str, float],
) -> PolicyOutcome:
    if update not in {"none", "positive_only", "full"}:
        raise ValueError(f"unknown update rule: {update}")
    if acquisition not in {"probability", "risk"}:
        raise ValueError(f"unknown acquisition: {acquisition}")
    belief = posterior
    remaining = list(posterior.candidates)
    replayed: list[str] = []
    for _ in range(min(budget, len(remaining))):
        if acquisition == "probability":
            scores = {node: belief.marginal(node) for node in remaining}
        else:
            scores = {node: _risk_score(belief, node, remaining, weights)
                      for node in remaining}
        chosen = min(remaining, key=lambda node: (-scores[node], node))
        replayed.append(chosen)
        remaining.remove(chosen)
        label = int(chosen in true_world)
        if update == "full" or (update == "positive_only" and label == 1):
            conditioned = belief.condition(chosen, label)
            if conditioned is None:
                raise ValueError("true world has zero posterior probability")
            belief = conditioned
    discoveries = len(set(replayed) & true_world)
    utility = sum(weights[node] for node in replayed if node in true_world)
    return PolicyOutcome(tuple(replayed), discoveries, utility)


def exact_weighted_policy_value(
    posterior: DirectionalPosterior, budget: int, weights: Mapping[str, float],
) -> float:
    """Exact Bayes-optimal expected weighted discoveries."""
    original = posterior.worlds

    @lru_cache(maxsize=None)
    def solve(possible: Tuple[int, ...], remaining: Tuple[str, ...], left: int) -> float:
        if left <= 0 or not remaining:
            return 0.0
        total = sum(original[index].weight for index in possible)
        best = 0.0
        for node in remaining:
            positive = tuple(index for index in possible
                             if node in original[index].affected_ids)
            negative = tuple(index for index in possible
                             if node not in original[index].affected_ids)
            p = sum(original[index].weight for index in positive) / total
            rest = tuple(item for item in remaining if item != node)
            value = p * weights[node]
            if positive:
                value += p * solve(positive, rest, left - 1)
            if negative:
                value += (1.0 - p) * solve(negative, rest, left - 1)
            best = max(best, value)
        return best

    return solve(tuple(range(len(original))), posterior.candidates,
                 min(budget, len(posterior.candidates)))


def tempered_posterior(
    posterior: DirectionalPosterior, temperature: float,
) -> DirectionalPosterior:
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    return DirectionalPosterior(
        posterior.candidates,
        tuple(CascadeWorld(world.affected_ids, world.weight ** temperature)
              for world in posterior.worlds),
    ).normalize()


def expected_outcomes(
    instance: RegimeInstance, *, belief_posterior: DirectionalPosterior | None = None,
    include_oracle: bool = True,
) -> Dict[str, Dict[str, float | None]]:
    specifications = {
        "static_probability": ("none", "probability"),
        "positive_only_probability": ("positive_only", "probability"),
        "dcta_probability": ("full", "probability"),
        "positive_only_risk": ("positive_only", "risk"),
        "dcta_risk": ("full", "risk"),
    }
    belief = belief_posterior or instance.posterior
    if belief.candidates != instance.posterior.candidates:
        raise ValueError("belief and truth require identical candidates")
    result: Dict[str, Dict[str, float | None]] = {}
    cached: Dict[Tuple[int, str], PolicyOutcome] = {}
    for method, (update, acquisition) in specifications.items():
        outcomes = []
        for index, world in enumerate(instance.posterior.worlds):
            outcome = run_policy(
                belief, world.affected_ids, instance.budget,
                update=update, acquisition=acquisition, weights=instance.harm_weights,
            )
            cached[index, method] = outcome
            outcomes.append((world.weight, outcome))
        result[method] = {
            "expected_weighted_utility": sum(w * o.weighted_utility for w, o in outcomes),
            "expected_discoveries": sum(w * o.discoveries for w, o in outcomes),
        }
    if include_oracle:
        oracle = exact_weighted_policy_value(
            instance.posterior, instance.budget, instance.harm_weights
        )
        result["exact_bayes_oracle"] = {
            "expected_weighted_utility": oracle,
            "expected_discoveries": None,
        }
    comparison = {"dcta_greater": 0.0, "equal": 0.0, "dcta_lower": 0.0}
    for index, world in enumerate(instance.posterior.worlds):
        dcta = cached[index, "dcta_risk"].weighted_utility
        positive = cached[index, "positive_only_risk"].weighted_utility
        key = "dcta_greater" if dcta > positive else "dcta_lower" if dcta < positive else "equal"
        comparison[key] += world.weight
    result["realized_comparison"] = comparison
    return result
