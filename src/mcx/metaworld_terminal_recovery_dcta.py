"""Meta-World confirmed-quarantine instantiation of terminal-recovery DCTA."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, FrozenSet, Mapping

from .directional_transition import risk_choice
from .prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld


@dataclass(frozen=True)
class BehavioralTerminalValue:
    recovery: float
    anchor_quarantine: float


@dataclass(frozen=True)
class MetaWorldTerminalOutcome:
    replayed_ids: tuple[str, ...]
    quarantined_ids: tuple[str, ...]
    final_posterior: LatentSourcePosterior
    root_rollout_value: BehavioralTerminalValue
    root_base_value: BehavioralTerminalValue


Utility = Callable[[FrozenSet[str], FrozenSet[str]], tuple[float, float]]


def _better(left: BehavioralTerminalValue, right: BehavioralTerminalValue,
            tolerance: float = 1e-12) -> bool:
    if left.recovery > right.recovery + tolerance:
        return True
    if right.recovery > left.recovery + tolerance:
        return False
    return left.anchor_quarantine > right.anchor_quarantine + tolerance


def _expected(probability: float, positive: BehavioralTerminalValue,
              negative: BehavioralTerminalValue) -> BehavioralTerminalValue:
    return BehavioralTerminalValue(
        probability * positive.recovery + (1.0 - probability) * negative.recovery,
        probability * positive.anchor_quarantine
        + (1.0 - probability) * negative.anchor_quarantine,
    )


def run_metaworld_terminal_recovery_dcta(
    posterior: LatentSourcePosterior,
    true_world: LatentSourceWorld,
    budget: int,
    *,
    weights: Mapping[str, float],
    utility: Utility,
) -> MetaWorldTerminalOutcome:
    """Plan replays for recovery under confirmed-positive-only quarantine.

    The rollout continuation is probabilistic DCTA.  Terminal quarantine is
    exactly the set of replay-confirmed harmful memories, matching the frozen
    Meta-World remediation contract.
    """
    if budget < 0:
        raise ValueError("budget must be nonnegative")

    @lru_cache(maxsize=None)
    def terminal(belief: LatentSourcePosterior,
                 confirmed: FrozenSet[str]) -> BehavioralTerminalValue:
        total = sum(world.weight for world in belief.worlds)
        recovery = 0.0
        quarantine = 0.0
        for world in belief.worlds:
            first, second = utility(world.affected_ids, confirmed)
            recovery += world.weight * first
            quarantine += world.weight * second
        return BehavioralTerminalValue(recovery / total, quarantine / total)

    @lru_cache(maxsize=None)
    def base_value(belief: LatentSourcePosterior, remaining: tuple[str, ...],
                   left: int, confirmed: FrozenSet[str]) -> BehavioralTerminalValue:
        if left <= 0 or not remaining:
            return terminal(belief, confirmed)
        chosen = risk_choice(belief, remaining, weights)
        rest = tuple(node for node in remaining if node != chosen)
        probability = belief.marginal(chosen)
        branches: dict[int, BehavioralTerminalValue] = {}
        for label in (0, 1):
            conditioned = belief.condition(chosen, label)
            if conditioned is not None:
                next_confirmed = confirmed | {chosen} if label else confirmed
                branches[label] = base_value(
                    conditioned, rest, left - 1, frozenset(next_confirmed))
        if 1 not in branches:
            return branches[0]
        if 0 not in branches:
            return branches[1]
        return _expected(probability, branches[1], branches[0])

    def improved_choice(belief: LatentSourcePosterior, remaining: tuple[str, ...],
                        left: int, confirmed: FrozenSet[str]) -> tuple[str, BehavioralTerminalValue]:
        best_node: str | None = None
        best_value: BehavioralTerminalValue | None = None
        for node in remaining:
            rest = tuple(candidate for candidate in remaining if candidate != node)
            probability = belief.marginal(node)
            branches: dict[int, BehavioralTerminalValue] = {}
            for label in (0, 1):
                conditioned = belief.condition(node, label)
                if conditioned is not None:
                    next_confirmed = confirmed | {node} if label else confirmed
                    branches[label] = base_value(
                        conditioned, rest, left - 1, frozenset(next_confirmed))
            if 1 not in branches:
                value = branches[0]
            elif 0 not in branches:
                value = branches[1]
            else:
                value = _expected(probability, branches[1], branches[0])
            if best_value is None or _better(value, best_value):
                best_node, best_value = node, value
        assert best_node is not None and best_value is not None
        return best_node, best_value

    total = min(budget, len(posterior.candidates))
    belief = posterior
    remaining = tuple(posterior.candidates)
    confirmed: FrozenSet[str] = frozenset()
    replayed = []
    root_base = base_value(belief, remaining, total, confirmed)
    root_rollout: BehavioralTerminalValue | None = None
    for step in range(total):
        chosen, predicted = improved_choice(belief, remaining, total - step, confirmed)
        if root_rollout is None:
            root_rollout = predicted
        replayed.append(chosen)
        remaining = tuple(node for node in remaining if node != chosen)
        label = int(chosen in true_world.affected_ids)
        if label:
            confirmed = confirmed | {chosen}
        conditioned = belief.condition(chosen, label)
        if conditioned is None:
            raise ValueError("true replay label has zero posterior probability")
        belief = conditioned
    if root_rollout is None:
        root_rollout = terminal(belief, confirmed)
    return MetaWorldTerminalOutcome(
        tuple(replayed), tuple(sorted(confirmed)), belief, root_rollout, root_base)

