"""Machine-checkable identities used by the SC-DCTA theory specification.

This module does not define a new acquisition policy.  It exposes equivalent
forms of the frozen score and small finite-posterior quantities so that the
paper's algebra can be checked against the implemented method.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from .prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld


def pairwise_probability(
    posterior: LatentSourcePosterior, left: str, right: str,
) -> float:
    """Return P(Z_left=1, Z_right=1) under a finite posterior."""
    total = sum(world.weight for world in posterior.worlds)
    return sum(
        world.weight
        for world in posterior.worlds
        if left in world.affected_ids and right in world.affected_ids
    ) / total


def positive_uplift_score(
    posterior: LatentSourcePosterior,
    node: str,
    remaining: Sequence[str],
    weights: Mapping[str, float],
) -> float:
    """The score in the frozen implementation: risk times positive uplift."""
    probability = posterior.marginal(node)
    impact = float(weights[node])
    positive = posterior.condition(node, 1)
    if positive is not None:
        for other in remaining:
            if other == node:
                continue
            impact += float(weights[other]) * max(
                0.0, positive.marginal(other) - posterior.marginal(other)
            )
    return probability * impact


def positive_covariance_score(
    posterior: LatentSourcePosterior,
    node: str,
    remaining: Sequence[str],
    weights: Mapping[str, float],
) -> float:
    """Equivalent score: immediate risk plus positive weighted covariance."""
    probability = posterior.marginal(node)
    score = float(weights[node]) * probability
    for other in remaining:
        if other == node:
            continue
        covariance = pairwise_probability(posterior, node, other) - (
            probability * posterior.marginal(other)
        )
        score += float(weights[other]) * max(0.0, covariance)
    return score


def finite_total_variation(
    left: Mapping[object, float], right: Mapping[object, float],
) -> float:
    """Total variation between two distributions on the same finite union."""
    support = set(left) | set(right)
    return 0.5 * sum(abs(float(left.get(x, 0.0)) - float(right.get(x, 0.0)))
                     for x in support)


def world_distribution(posterior: LatentSourcePosterior) -> dict[tuple[str, frozenset[str]], float]:
    """Aggregate a posterior into a finite distribution keyed by latent world."""
    total = sum(world.weight for world in posterior.worlds)
    distribution: dict[tuple[str, frozenset[str]], float] = {}
    for world in posterior.worlds:
        key = (world.source_id, world.affected_ids)
        distribution[key] = distribution.get(key, 0.0) + world.weight / total
    return distribution


def score_stability_radius(total_weight: float, posterior_tv: float) -> float:
    """Uniform score-error radius from Proposition 3 of theory v0.3.

    If two finite posteriors are within total variation ``delta``, every
    positive-covariance score differs by at most ``3 * W * delta``, where W is
    total nonnegative harm weight over the current candidate set.
    """
    if total_weight < 0.0 or not 0.0 <= posterior_tv <= 1.0:
        raise ValueError("invalid weight or total-variation distance")
    return 3.0 * total_weight * posterior_tv


def support_proposal_ratio_bound(source_count: int, minimum_probability: float) -> float:
    """Worst-case p(s)/q(s) for the frozen affine support proposal.

    For ``q(s) = lambda + (1-K*lambda)*p(s)``, the ratio is increasing in
    ``p(s)`` and is therefore at most ``1 / (1-(K-1)*lambda)``.
    """
    if source_count <= 0 or not 0.0 <= minimum_probability < 1.0 / source_count:
        raise ValueError("invalid source count or proposal floor")
    return 1.0 / (1.0 - (source_count - 1) * minimum_probability)


def uniform_snis_absolute_error(
    particle_count: int,
    bounded_average_count: int,
    maximum_importance_ratio: float,
    failure_probability: float,
) -> float:
    """Hoeffding radius for weighted event numerators and denominators.

    With probability at least ``1-alpha``, every one of
    ``bounded_average_count`` weighted event-mass averages differs from its
    expectation by at most the returned value. Include each SNIS numerator
    and conditioning-history denominator in that count.
    """
    if particle_count <= 0 or bounded_average_count <= 0:
        raise ValueError("particle and event counts must be positive")
    if maximum_importance_ratio < 1.0:
        raise ValueError("maximum importance ratio must be at least one")
    if not 0.0 < failure_probability < 1.0:
        raise ValueError("failure probability must lie in (0,1)")
    logarithm = math.log(
        2.0 * bounded_average_count / failure_probability
    )
    return maximum_importance_ratio * math.sqrt(
        logarithm / (2.0 * particle_count)
    )


def conditional_snis_moment_error(
    absolute_error: float, minimum_history_probability: float,
) -> float:
    """Convert an absolute event-mass error to conditional-moment error.

    If a conditioning history has target probability at least ``gamma`` and
    both its weighted mass and a joint-event mass are estimated within ``a``,
    the conditional probability error is at most ``2a/(gamma-a)``.
    """
    if absolute_error < 0.0 or not 0.0 < minimum_history_probability <= 1.0:
        raise ValueError("invalid error or history probability")
    if absolute_error >= minimum_history_probability:
        raise ValueError("concentration radius must be below history probability")
    return 2.0 * absolute_error / (
        minimum_history_probability - absolute_error
    )


def binary_policy_history_count(replay_budget: int) -> int:
    """Maximum decision histories before actions in a binary B-step tree."""
    if replay_budget <= 0:
        raise ValueError("replay budget must be positive")
    return 2 ** replay_budget - 1


def sc_dcta_trajectory_certificate(
    *,
    particle_count: int,
    candidate_count: int,
    replay_budget: int,
    total_harm_weight: float,
    maximum_importance_ratio: float,
    minimum_history_probability: float,
    failure_probability: float,
) -> dict[str, float | int]:
    """Return the conservative sufficient margin for trajectory agreement.

    The event union covers every marginal and unordered pairwise moment at
    every history in the exact binary SC-DCTA decision tree through the given
    budget.  If every exact score margin exceeds ``required_score_margin`` and
    every reachable history has probability at least the declared minimum,
    finite-particle and infinite-particle SC-DCTA select the same actions with
    probability at least ``1-failure_probability``.
    """
    if candidate_count <= 0 or total_harm_weight < 0.0:
        raise ValueError("candidate count must be positive and harm nonnegative")
    histories = binary_policy_history_count(replay_budget)
    moments_per_history = candidate_count * (candidate_count + 1) // 2
    events = histories * (moments_per_history + 1)
    absolute = uniform_snis_absolute_error(
        particle_count, events, maximum_importance_ratio, failure_probability
    )
    conditional = conditional_snis_moment_error(
        absolute, minimum_history_probability
    )
    score_radius = score_stability_radius(total_harm_weight, conditional)
    return {
        "particle_count": particle_count,
        "candidate_count": candidate_count,
        "replay_budget": replay_budget,
        "history_count": histories,
        "moments_per_history": moments_per_history,
        "union_event_count": events,
        "absolute_event_mass_error": absolute,
        "conditional_moment_error": conditional,
        "uniform_score_error": score_radius,
        "required_score_margin": 2.0 * score_radius,
        "confidence": 1.0 - failure_probability,
    }


def orthogonal_partition_posterior(
    partition_size: int,
    descendants_per_branch: int,
    *,
    observed_row: int | None = None,
    observed_column: int | None = None,
) -> LatentSourcePosterior:
    """Exact posterior for the transverse-partition separation witness.

    The latent origin is a uniformly distributed pair ``(row, column)``.
    Every branch has the same number of deterministic affected descendants.
    Provenance reveals only the row and content reveals only the column.
    """
    if partition_size < 2 or descendants_per_branch <= 0:
        raise ValueError("invalid partition archive dimensions")
    for name, value in (("row", observed_row), ("column", observed_column)):
        if value is not None and value not in range(partition_size):
            raise ValueError(f"invalid observed {name}")
    candidates = tuple(
        f"m_{row}_{column}_{offset}"
        for row in range(partition_size)
        for column in range(partition_size)
        for offset in range(descendants_per_branch)
    )
    all_sources = tuple(
        f"s_{row}_{column}"
        for row in range(partition_size)
        for column in range(partition_size)
    )
    compatible = [
        (row, column)
        for row in range(partition_size)
        for column in range(partition_size)
        if (observed_row is None or row == observed_row)
        and (observed_column is None or column == observed_column)
    ]
    mass = 1.0 / len(compatible)
    worlds = tuple(
        LatentSourceWorld(
            f"s_{row}_{column}",
            frozenset(
                f"m_{row}_{column}_{offset}"
                for offset in range(descendants_per_branch)
            ),
            mass,
        )
        for row, column in compatible
    )
    return LatentSourcePosterior(candidates, all_sources, worlds).normalize()


def single_view_optimal_discoveries(
    plausible_branches: int, replay_budget: int,
) -> float:
    """Optimal expected discoveries with one of r uniform branches positive.

    The formula assumes at least ``replay_budget`` positive descendants are
    available in every branch and ``replay_budget <= plausible_branches``.
    """
    if plausible_branches <= 0 or replay_budget <= 0 \
            or replay_budget > plausible_branches:
        raise ValueError("require 1 <= budget <= plausible branches")
    return replay_budget * (replay_budget + 1) / (2.0 * plausible_branches)


def single_view_discovery_dp(
    plausible_branches: int, replay_budget: int,
) -> float:
    """Bellman recursion independently verifying the closed-form bound."""
    if plausible_branches <= 0 or replay_budget < 0 \
            or replay_budget > plausible_branches:
        raise ValueError("require 0 <= budget <= plausible branches")
    if replay_budget == 0:
        return 0.0
    if plausible_branches == 1:
        return 1.0
    # A positive first query yields one discovery now and positive discoveries
    # on every remaining replay. A negative removes exactly one branch.
    return (
        replay_budget / plausible_branches
        + (plausible_branches - 1) / plausible_branches
        * single_view_discovery_dp(plausible_branches - 1, replay_budget - 1)
    )


def noisy_joint_discovery_lower_bound(
    replay_budget: int,
    provenance_decode_error: float,
    content_decode_error: float,
) -> float:
    """Union-bound utility when row and column decoders can each fail."""
    if replay_budget <= 0 or not 0.0 <= provenance_decode_error <= 1.0 \
            or not 0.0 <= content_decode_error <= 1.0:
        raise ValueError("invalid budget or decoder error")
    success_lower = max(
        0.0, 1.0 - provenance_decode_error - content_decode_error
    )
    return replay_budget * success_lower


def single_view_positive_localization_probability(
    plausible_branches: int, replay_budget: int,
) -> float:
    """Maximum chance of replay-confirming a positive under one view."""
    if plausible_branches <= 0 or replay_budget < 0:
        raise ValueError("invalid branches or budget")
    return min(replay_budget, plausible_branches) / plausible_branches


def stochastic_orthogonal_partition_posterior(
    partition_size: int,
    descendants_per_branch: int,
    transmission_probability: float,
    *,
    observed_row: int | None = None,
    observed_column: int | None = None,
) -> LatentSourcePosterior:
    """Exact stochastic-star posterior for Theorem 6's extension.

    Conditional on the latent origin, each descendant in its branch is
    independently affected with probability ``theta``. All other branches are
    clean. The returned posterior enumerates every latent affected subset.
    """
    if partition_size < 2 or descendants_per_branch <= 0 \
            or not 0.0 < transmission_probability <= 1.0:
        raise ValueError("invalid stochastic partition archive parameters")
    for name, value in (("row", observed_row), ("column", observed_column)):
        if value is not None and value not in range(partition_size):
            raise ValueError(f"invalid observed {name}")
    candidates = tuple(
        f"m_{row}_{column}_{offset}"
        for row in range(partition_size)
        for column in range(partition_size)
        for offset in range(descendants_per_branch)
    )
    all_sources = tuple(
        f"s_{row}_{column}"
        for row in range(partition_size)
        for column in range(partition_size)
    )
    compatible = [
        (row, column)
        for row in range(partition_size)
        for column in range(partition_size)
        if (observed_row is None or row == observed_row)
        and (observed_column is None or column == observed_column)
    ]
    source_mass = 1.0 / len(compatible)
    theta = transmission_probability
    worlds: list[LatentSourceWorld] = []
    for row, column in compatible:
        branch = tuple(
            f"m_{row}_{column}_{offset}"
            for offset in range(descendants_per_branch)
        )
        for mask in range(1 << descendants_per_branch):
            affected = frozenset(
                node for offset, node in enumerate(branch)
                if mask & (1 << offset)
            )
            positives = len(affected)
            mass = source_mass * theta ** positives * (
                1.0 - theta
            ) ** (descendants_per_branch - positives)
            if mass > 0.0:
                worlds.append(LatentSourceWorld(
                    f"s_{row}_{column}", affected, mass
                ))
    return LatentSourcePosterior(
        candidates, all_sources, tuple(worlds)
    ).normalize()


def stochastic_joint_expected_discoveries(
    replay_budget: int, transmission_probability: float,
) -> float:
    """Expected utility when the true stochastic branch is known."""
    if replay_budget <= 0 or not 0.0 <= transmission_probability <= 1.0:
        raise ValueError("invalid budget or transmission probability")
    return replay_budget * transmission_probability


def stochastic_single_view_oracle_upper_bound(
    plausible_branches: int,
    replay_budget: int,
    transmission_probability: float,
) -> float:
    """Upper bound after granting single-view search a branch-identity oracle."""
    if not 0.0 <= transmission_probability <= 1.0:
        raise ValueError("invalid transmission probability")
    return transmission_probability * single_view_optimal_discoveries(
        plausible_branches, replay_budget
    )


def stochastic_joint_positive_probability(
    replay_budget: int, transmission_probability: float,
) -> float:
    """Chance that B true-branch replays confirm at least one positive."""
    if replay_budget < 0 or not 0.0 <= transmission_probability <= 1.0:
        raise ValueError("invalid budget or transmission probability")
    return 1.0 - (1.0 - transmission_probability) ** replay_budget


def stochastic_single_view_oracle_positive_upper_bound(
    plausible_branches: int,
    replay_budget: int,
    transmission_probability: float,
) -> float:
    """Oracle upper bound on confirming any positive from one evidence view."""
    if plausible_branches <= 0 or replay_budget < 0 \
            or replay_budget > plausible_branches \
            or not 0.0 <= transmission_probability <= 1.0:
        raise ValueError("invalid stochastic localization parameters")
    return sum(
        1.0 - (1.0 - transmission_probability) ** remaining
        for remaining in range(1, replay_budget + 1)
    ) / plausible_branches
