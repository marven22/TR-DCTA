import pytest

from mcx.directional_transition import risk_choice
from mcx.prob_dcta_benchmark import (
    LatentSourcePosterior, LatentSourceWorld, run_latent_policy,
)
from mcx.sc_dcta_theory import (
    binary_policy_history_count,
    conditional_snis_moment_error,
    finite_total_variation,
    noisy_joint_discovery_lower_bound,
    orthogonal_partition_posterior,
    positive_covariance_score,
    positive_uplift_score,
    sc_dcta_trajectory_certificate,
    score_stability_radius,
    single_view_discovery_dp,
    single_view_optimal_discoveries,
    single_view_positive_localization_probability,
    stochastic_joint_expected_discoveries,
    stochastic_joint_positive_probability,
    stochastic_orthogonal_partition_posterior,
    stochastic_single_view_oracle_positive_upper_bound,
    stochastic_single_view_oracle_upper_bound,
    support_proposal_ratio_bound,
    uniform_snis_absolute_error,
    world_distribution,
)


def posterior(worlds):
    return LatentSourcePosterior(
        candidates=("a", "b", "c"),
        source_ids=("s1", "s2"),
        worlds=tuple(LatentSourceWorld(source, frozenset(labels), mass)
                     for source, labels, mass in worlds),
    ).normalize()


def test_frozen_positive_uplift_score_equals_positive_covariance_form():
    belief = posterior((
        ("s1", {"a", "b"}, .30),
        ("s1", {"a"}, .15),
        ("s2", {"b", "c"}, .25),
        ("s2", set(), .30),
    ))
    weights = {"a": 1.0, "b": 2.0, "c": 3.0}
    for node in belief.candidates:
        assert positive_uplift_score(belief, node, belief.candidates, weights) == \
            pytest.approx(positive_covariance_score(
                belief, node, belief.candidates, weights
            ), abs=1e-12)


def test_covariance_form_selects_same_node_as_frozen_implementation():
    belief = posterior((
        ("s1", {"a", "b"}, .35),
        ("s1", {"a"}, .10),
        ("s2", {"c"}, .30),
        ("s2", set(), .25),
    ))
    weights = {"a": 1.0, "b": 3.0, "c": 1.0}
    frozen = risk_choice(belief, belief.candidates, weights)
    covariance = min(
        belief.candidates,
        key=lambda node: (-positive_covariance_score(
            belief, node, belief.candidates, weights
        ), node),
    )
    assert covariance == frozen


def test_support_correction_identity_is_exact_before_monte_carlo():
    target = {"s1": .91, "s2": .08, "s3": .01}
    proposal = {"s1": .82, "s2": .13, "s3": .05}
    feature = {"s1": .2, "s2": .7, "s3": 1.0}

    target_expectation = sum(target[s] * feature[s] for s in target)
    importance_expectation = sum(
        proposal[s] * (target[s] / proposal[s]) * feature[s]
        for s in target
    )
    expected_weight = sum(
        proposal[s] * (target[s] / proposal[s]) for s in target
    )

    assert importance_expectation == pytest.approx(target_expectation, abs=1e-12)
    assert expected_weight == pytest.approx(1.0, abs=1e-12)
    assert sum(proposal[s] * feature[s] for s in target) != \
        pytest.approx(target_expectation, abs=1e-12)


def test_total_variation_score_bound_and_margin_certificate_hold():
    exact = posterior((
        ("s1", {"a", "b"}, .40),
        ("s1", {"a"}, .20),
        ("s2", {"c"}, .25),
        ("s2", set(), .15),
    ))
    approximate = posterior((
        ("s1", {"a", "b"}, .39),
        ("s1", {"a"}, .21),
        ("s2", {"c"}, .24),
        ("s2", set(), .16),
    ))
    weights = {"a": 1.0, "b": 2.0, "c": 1.0}
    delta = finite_total_variation(
        world_distribution(exact), world_distribution(approximate)
    )
    radius = score_stability_radius(sum(weights.values()), delta)
    errors = [abs(
        positive_covariance_score(exact, node, exact.candidates, weights)
        - positive_covariance_score(approximate, node, approximate.candidates, weights)
    ) for node in exact.candidates]
    assert max(errors) <= radius + 1e-12

    exact_scores = sorted(
        (positive_covariance_score(exact, node, exact.candidates, weights), node)
        for node in exact.candidates
    )
    margin = exact_scores[-1][0] - exact_scores[-2][0]
    if margin > 2.0 * radius:
        assert exact_scores[-1][1] == max(
            approximate.candidates,
            key=lambda node: positive_covariance_score(
                approximate, node, approximate.candidates, weights
            ),
        )


def test_affine_support_proposal_has_declared_importance_ratio_bound():
    source_count = 3
    floor = .05
    bound = support_proposal_ratio_bound(source_count, floor)
    assert bound == pytest.approx(1.0 / .90)

    # Check the complete one-dimensional simplex edge at fine resolution; the
    # analytic proof establishes the continuum result.
    for offset in range(1001):
        probability = offset / 1000
        proposal = floor + (1.0 - source_count * floor) * probability
        ratio = probability / proposal
        assert ratio <= bound + 1e-12


def test_uniform_snis_bound_shrinks_with_particles_and_grows_with_union():
    small = uniform_snis_absolute_error(2048, 172, 1.0 / .90, .05)
    more_particles = uniform_snis_absolute_error(8192, 172, 1.0 / .90, .05)
    more_events = uniform_snis_absolute_error(2048, 20_000, 1.0 / .90, .05)
    assert more_particles == pytest.approx(small / 2.0)
    assert more_events > small


def test_conditional_error_exposes_rare_history_instability():
    absolute = .01
    common = conditional_snis_moment_error(absolute, .50)
    rare = conditional_snis_moment_error(absolute, .05)
    assert rare > common
    with pytest.raises(ValueError, match="below history probability"):
        conditional_snis_moment_error(.05, .05)


def test_trajectory_certificate_counts_binary_histories_and_moments():
    certificate = sc_dcta_trajectory_certificate(
        particle_count=10_000_000,
        candidate_count=3,
        replay_budget=4,
        total_harm_weight=6.0,
        maximum_importance_ratio=1.0 / .90,
        minimum_history_probability=.10,
        failure_probability=.05,
    )
    assert binary_policy_history_count(4) == 15
    assert certificate["history_count"] == 15
    assert certificate["moments_per_history"] == 6  # 3 marginals + 3 pairs
    assert certificate["union_event_count"] == 15 * 7
    assert certificate["conditional_moment_error"] > 0.0
    assert certificate["required_score_margin"] == pytest.approx(
        2.0 * certificate["uniform_score_error"]
    )
    assert certificate["confidence"] == pytest.approx(.95)


def expected_sc_utility(belief, truth, budget):
    weights = {node: 1.0 for node in belief.candidates}
    return sum(
        world.weight * run_latent_policy(
            belief, world, budget, method="prob_dcta", weights=weights
        ).weighted_utility
        for world in truth.worlds
    )


def test_single_view_closed_form_matches_exact_bellman_recursion():
    for branches in range(2, 10):
        for budget in range(1, branches + 1):
            assert single_view_discovery_dp(branches, budget) == pytest.approx(
                single_view_optimal_discoveries(branches, budget)
            )


def test_exact_sc_dcta_realizes_joint_and_single_view_separation():
    size = 5
    budget = 3
    descendants = budget
    joint = orthogonal_partition_posterior(
        size, descendants, observed_row=2, observed_column=4
    )
    graph_only = orthogonal_partition_posterior(
        size, descendants, observed_row=2
    )
    content_only = orthogonal_partition_posterior(
        size, descendants, observed_column=4
    )

    assert expected_sc_utility(joint, joint, budget) == pytest.approx(budget)
    expected_single = single_view_optimal_discoveries(size, budget)
    assert expected_sc_utility(graph_only, graph_only, budget) == \
        pytest.approx(expected_single)
    assert expected_sc_utility(content_only, content_only, budget) == \
        pytest.approx(expected_single)
    assert budget > expected_single


def test_early_hard_source_collapse_has_quadratic_ambiguity_penalty():
    size = 4
    budget = 3
    truth = orthogonal_partition_posterior(size, budget)
    collapsed = truth.restrict_source("s_0_0")
    expected = expected_sc_utility(collapsed, truth, budget)
    assert expected == pytest.approx(budget / (size * size))


def test_noisy_joint_condition_retains_strict_advantage():
    size = 10
    budget = 4
    joint_lower = noisy_joint_discovery_lower_bound(budget, .05, .05)
    single_upper = single_view_optimal_discoveries(size, budget)
    assert joint_lower == pytest.approx(3.6)
    assert single_upper == pytest.approx(1.0)
    assert joint_lower > single_upper


def test_single_view_positive_localization_requires_linear_branch_search():
    assert single_view_positive_localization_probability(20, 1) == .05
    assert single_view_positive_localization_probability(20, 18) == .90
    assert single_view_positive_localization_probability(20, 25) == 1.0


def test_stochastic_joint_sc_dcta_obtains_b_theta():
    size = 4
    budget = 3
    theta = .60
    joint = stochastic_orthogonal_partition_posterior(
        size, budget, theta, observed_row=1, observed_column=3
    )
    assert expected_sc_utility(joint, joint, budget) == pytest.approx(
        stochastic_joint_expected_discoveries(budget, theta)
    )


def test_stochastic_single_view_sc_dcta_is_below_branch_oracle_bound():
    size = 5
    budget = 3
    theta = .55
    graph_only = stochastic_orthogonal_partition_posterior(
        size, budget, theta, observed_row=2
    )
    content_only = stochastic_orthogonal_partition_posterior(
        size, budget, theta, observed_column=1
    )
    oracle = stochastic_single_view_oracle_upper_bound(size, budget, theta)
    assert expected_sc_utility(graph_only, graph_only, budget) <= oracle + 1e-12
    assert expected_sc_utility(content_only, content_only, budget) <= oracle + 1e-12
    assert stochastic_joint_expected_discoveries(budget, theta) > oracle


def test_stochastic_oracle_bound_matches_scaled_bellman_value():
    for branches in range(2, 9):
        for budget in range(1, branches + 1):
            for theta in (.15, .50, .90, 1.0):
                assert stochastic_single_view_oracle_upper_bound(
                    branches, budget, theta
                ) == pytest.approx(
                    theta * single_view_discovery_dp(branches, budget)
                )


def test_stochastic_extension_reduces_to_deterministic_theorem_at_theta_one():
    size = 4
    budget = 3
    deterministic = orthogonal_partition_posterior(
        size, budget, observed_row=0
    )
    stochastic = stochastic_orthogonal_partition_posterior(
        size, budget, 1.0, observed_row=0
    )
    assert expected_sc_utility(stochastic, stochastic, budget) == pytest.approx(
        expected_sc_utility(deterministic, deterministic, budget)
    )


def test_stochastic_localization_probability_separation():
    size = 10
    budget = 4
    theta = .40
    joint = stochastic_joint_positive_probability(budget, theta)
    single_oracle = stochastic_single_view_oracle_positive_upper_bound(
        size, budget, theta
    )
    assert joint == pytest.approx(1.0 - .60 ** 4)
    assert single_oracle == pytest.approx(sum(
        1.0 - .60 ** remaining for remaining in range(1, budget + 1)
    ) / size)
    assert joint > single_oracle


def test_stochastic_hard_source_collapse_retains_quadratic_penalty():
    size = 3
    budget = 2
    theta = .65
    truth = stochastic_orthogonal_partition_posterior(size, budget, theta)
    collapsed = truth.restrict_source("s_0_0")
    expected = expected_sc_utility(collapsed, truth, budget)
    assert expected == pytest.approx(budget * theta / (size * size))
