"""Decision-aware selection between probabilistic and hard-source DCTA."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet, Mapping, Sequence

from .directional_transition import risk_choice
from .prob_dcta_benchmark import (
    LatentPolicyOutcome, LatentSourcePosterior, LatentSourceWorld, run_latent_policy,
)


@dataclass(frozen=True)
class ConfidenceAwareDecision:
    mode: str
    hard_expected_utility: float
    probabilistic_expected_utility: float


@dataclass(frozen=True)
class ConfidenceAwareOutcome:
    decision: ConfidenceAwareDecision
    policy_outcome: LatentPolicyOutcome


def expected_risk_policy_utility(
    posterior: LatentSourcePosterior, budget: int, *, mode: str,
    weights: Mapping[str, float],
) -> float:
    """Expected realized utility of a fixed DCTA mode under ``posterior``.

    Hard mode makes decisions using the top-source-restricted belief, while
    outcome probabilities remain those of the full posterior.  An observation
    outside hard mode's retained support leaves its decision belief unchanged,
    matching ``run_latent_policy``.
    """
    if mode not in {"hard", "probabilistic"}:
        raise ValueError("mode must be hard or probabilistic")
    if budget < 0:
        raise ValueError("budget must be nonnegative")
    decision = posterior
    if mode == "hard":
        probabilities = posterior.source_probabilities()
        source = min(posterior.source_ids,
                     key=lambda value: (-probabilities[value], value))
        decision = posterior.restrict_source(source)

    @lru_cache(maxsize=None)
    def solve(world_belief: LatentSourcePosterior,
              decision_belief: LatentSourcePosterior,
              remaining: tuple[str, ...], left: int) -> float:
        if left <= 0 or not remaining:
            return 0.0
        chosen = risk_choice(decision_belief, remaining, weights)
        probability = world_belief.marginal(chosen)
        rest = tuple(node for node in remaining if node != chosen)
        value = 0.0
        for label, branch_probability in ((1, probability), (0, 1.0 - probability)):
            if branch_probability <= 0.0:
                continue
            world_next = world_belief.condition(chosen, label)
            if world_next is None:
                continue
            decision_next = decision_belief.condition(chosen, label)
            if decision_next is None:
                decision_next = decision_belief
            immediate = float(weights[chosen]) if label else 0.0
            value += branch_probability * (
                immediate + solve(world_next, decision_next, rest, left - 1)
            )
        return value

    return solve(posterior, decision, posterior.candidates,
                 min(budget, len(posterior.candidates)))


def confidence_aware_decision(
    posterior: LatentSourcePosterior, budget: int, weights: Mapping[str, float],
) -> ConfidenceAwareDecision:
    hard = expected_risk_policy_utility(posterior, budget, mode="hard", weights=weights)
    probabilistic = expected_risk_policy_utility(
        posterior, budget, mode="probabilistic", weights=weights,
    )
    # Prefer the simpler committed policy when the posterior predicts a tie.
    mode = "hard" if hard >= probabilistic - 1e-12 else "probabilistic"
    return ConfidenceAwareDecision(mode, hard, probabilistic)


def run_confidence_aware_dcta(
    posterior: LatentSourcePosterior, true_world: LatentSourceWorld,
    budget: int, *, weights: Mapping[str, float],
) -> ConfidenceAwareOutcome:
    decision = confidence_aware_decision(posterior, budget, weights)
    method = "top1_dcta" if decision.mode == "hard" else "prob_dcta"
    outcome = run_latent_policy(
        posterior, true_world, budget, method=method, weights=weights,
    )
    return ConfidenceAwareOutcome(decision, outcome)

