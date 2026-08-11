from itertools import combinations

from mcx.prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld
from mcx.prob_dcta_benchmark import run_latent_policy
from mcx.terminal_recovery_dcta import (
    run_terminal_recovery_dcta, terminal_quarantine_decision,
)


def posterior() -> LatentSourcePosterior:
    return LatentSourcePosterior(
        ("a", "b", "c", "d"), ("s1", "s2"), (
            LatentSourceWorld("s1", frozenset({"a", "b"}), 0.45),
            LatentSourceWorld("s1", frozenset({"a"}), 0.15),
            LatentSourceWorld("s2", frozenset({"c", "d"}), 0.40),
        ),
    )


def test_terminal_decision_matches_exhaustive_recovery_probability() -> None:
    belief = posterior()
    weights = {node: 1.0 for node in belief.candidates}
    decision = terminal_quarantine_decision(belief, weights, 2)
    scores = {}
    for chosen in combinations(belief.candidates, 2):
        scores[chosen] = sum(world.weight for world in belief.worlds
                             if world.affected_ids <= set(chosen))
    assert decision.quarantined_ids == ("a", "b")
    assert decision.value.recovery_probability == max(scores.values()) == 0.60


def test_terminal_recovery_rollout_replays_exact_budget_and_recovers() -> None:
    belief = posterior()
    truth = belief.worlds[0]
    outcome = run_terminal_recovery_dcta(
        belief, truth, 2, weights={node: 1.0 for node in belief.candidates},
        quarantine_capacity=2,
    )
    assert len(outcome.replayed_ids) == 2
    assert len(set(outcome.replayed_ids)) == 2
    assert truth.affected_ids <= set(outcome.terminal_decision.quarantined_ids)


def test_rollout_model_expected_recovery_dominates_base_dcta() -> None:
    belief = posterior()
    weights = {node: 1.0 for node in belief.candidates}
    rollout_value = 0.0
    base_value = 0.0
    for truth in belief.worlds:
        rollout = run_terminal_recovery_dcta(
            belief, truth, 1, weights=weights, quarantine_capacity=2,
        )
        base = run_latent_policy(
            belief, truth, 1, method="prob_dcta", weights=weights,
        )
        base_decision = terminal_quarantine_decision(
            base.final_posterior, weights, 2,
        )
        rollout_value += truth.weight * float(
            truth.affected_ids <= set(rollout.terminal_decision.quarantined_ids))
        base_value += truth.weight * float(
            truth.affected_ids <= set(base_decision.quarantined_ids))
    assert rollout_value >= base_value
