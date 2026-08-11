"""Finite-horizon terminal-recovery rollout for causal memory auditing.

The base DCTA policy greedily selects posterior weighted harm.  TR-DCTA uses
that policy as a rollout continuation, but improves every current action by
evaluating the terminal quarantine decision after the complete remaining
replay budget.  Replanning after each observed label is the standard rollout
policy-improvement construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from typing import Mapping, Sequence

from .directional_transition import risk_choice
from .prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld


@dataclass(frozen=True)
class TerminalValue:
    """Lexicographic terminal utility: recovery first, captured harm second."""

    recovery_probability: float
    expected_captured_harm: float


@dataclass(frozen=True)
class TerminalDecision:
    quarantined_ids: tuple[str, ...]
    value: TerminalValue


@dataclass(frozen=True)
class TerminalRecoveryOutcome:
    replayed_ids: tuple[str, ...]
    final_posterior: LatentSourcePosterior
    terminal_decision: TerminalDecision


def _better(left: TerminalValue, right: TerminalValue, tolerance: float = 1e-12) -> bool:
    if left.recovery_probability > right.recovery_probability + tolerance:
        return True
    if right.recovery_probability > left.recovery_probability + tolerance:
        return False
    return left.expected_captured_harm > right.expected_captured_harm + tolerance


def _expected(
    probability: float, positive: TerminalValue, negative: TerminalValue,
) -> TerminalValue:
    return TerminalValue(
        probability * positive.recovery_probability
        + (1.0 - probability) * negative.recovery_probability,
        probability * positive.expected_captured_harm
        + (1.0 - probability) * negative.expected_captured_harm,
    )


def terminal_quarantine_decision(
    posterior: LatentSourcePosterior,
    weights: Mapping[str, float],
    capacity: int,
) -> TerminalDecision:
    """Choose a capacity-limited quarantine maximizing posterior recovery.

    Ties in recovery probability maximize expected captured harm, followed by
    the lexicographic node tuple.  The fast recovery calculation is exact when
    every affected set has cardinality at most ``capacity``; larger sets can
    never be fully recovered by a capacity-limited decision and contribute
    zero recovery mass.
    """
    if capacity < 0 or capacity > len(posterior.candidates):
        raise ValueError("invalid quarantine capacity")
    total = sum(world.weight for world in posterior.worlds)
    mass_by_set: dict[frozenset[str], float] = {}
    marginals = {node: 0.0 for node in posterior.candidates}
    for world in posterior.worlds:
        mass_by_set[world.affected_ids] = mass_by_set.get(world.affected_ids, 0.0) + world.weight
        for node in world.affected_ids:
            marginals[node] += world.weight
    best_ids: tuple[str, ...] | None = None
    best_value: TerminalValue | None = None
    for chosen in combinations(sorted(posterior.candidates), capacity):
        recovery_mass = mass_by_set.get(frozenset(), 0.0)
        # Any recoverable nonempty affected set is one of the subsets of Q.
        for size in range(1, capacity + 1):
            for subset in combinations(chosen, size):
                recovery_mass += mass_by_set.get(frozenset(subset), 0.0)
        value = TerminalValue(
            recovery_mass / total,
            sum(float(weights[node]) * marginals[node] for node in chosen) / total,
        )
        if best_value is None or _better(value, best_value):
            best_ids, best_value = chosen, value
    assert best_ids is not None and best_value is not None
    return TerminalDecision(best_ids, best_value)


def run_terminal_recovery_dcta(
    posterior: LatentSourcePosterior,
    true_world: LatentSourceWorld,
    budget: int,
    *,
    weights: Mapping[str, float],
    quarantine_capacity: int,
) -> TerminalRecoveryOutcome:
    """Run online full-budget DCTA rollout with exact binary-outcome averaging."""
    if budget < 0:
        raise ValueError("budget must be nonnegative")
    candidates = posterior.candidates

    @lru_cache(maxsize=None)
    def base_value(
        belief: LatentSourcePosterior, remaining: tuple[str, ...], left: int,
    ) -> TerminalValue:
        if left <= 0 or not remaining:
            return terminal_quarantine_decision(
                belief, weights, quarantine_capacity,
            ).value
        chosen = risk_choice(belief, remaining, weights)
        rest = tuple(node for node in remaining if node != chosen)
        probability = belief.marginal(chosen)
        branches: dict[int, TerminalValue] = {}
        for label in (0, 1):
            conditioned = belief.condition(chosen, label)
            if conditioned is not None:
                branches[label] = base_value(conditioned, rest, left - 1)
        if 1 not in branches:
            return branches[0]
        if 0 not in branches:
            return branches[1]
        return _expected(probability, branches[1], branches[0])

    def improved_choice(
        belief: LatentSourcePosterior, remaining: tuple[str, ...], left: int,
    ) -> str:
        best_node: str | None = None
        best_value: TerminalValue | None = None
        for node in remaining:
            rest = tuple(candidate for candidate in remaining if candidate != node)
            probability = belief.marginal(node)
            branches: dict[int, TerminalValue] = {}
            for label in (0, 1):
                conditioned = belief.condition(node, label)
                if conditioned is not None:
                    branches[label] = base_value(conditioned, rest, left - 1)
            if 1 not in branches:
                value = branches[0]
            elif 0 not in branches:
                value = branches[1]
            else:
                value = _expected(probability, branches[1], branches[0])
            if best_value is None or _better(value, best_value):
                best_node, best_value = node, value
        assert best_node is not None
        return best_node

    belief = posterior
    remaining = tuple(candidates)
    replayed = []
    total = min(budget, len(remaining))
    for step in range(total):
        chosen = improved_choice(belief, remaining, total - step)
        replayed.append(chosen)
        remaining = tuple(node for node in remaining if node != chosen)
        conditioned = belief.condition(chosen, int(chosen in true_world.affected_ids))
        if conditioned is None:
            raise ValueError("true replay label has zero posterior probability")
        belief = conditioned
    decision = terminal_quarantine_decision(belief, weights, quarantine_capacity)
    return TerminalRecoveryOutcome(tuple(replayed), belief, decision)

