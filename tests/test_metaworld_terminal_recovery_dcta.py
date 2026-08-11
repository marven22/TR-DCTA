from mcx.metaworld_terminal_recovery_dcta import run_metaworld_terminal_recovery_dcta
from mcx.prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld


def test_confirmed_quarantine_and_rollout_dominance() -> None:
    posterior = LatentSourcePosterior(
        ("a", "b", "c"), ("s1", "s2"), (
            LatentSourceWorld("s1", frozenset({"a", "b"}), .55),
            LatentSourceWorld("s2", frozenset({"c"}), .45),
        ))
    truth = posterior.worlds[0]

    def utility(affected: frozenset[str], removed: frozenset[str]) -> tuple[float, float]:
        fraction = len(affected & removed) / len(affected)
        return fraction, fraction

    outcome = run_metaworld_terminal_recovery_dcta(
        posterior, truth, 2, weights={node: 1.0 for node in posterior.candidates},
        utility=utility)
    assert len(outcome.replayed_ids) == 2
    assert set(outcome.quarantined_ids) <= set(outcome.replayed_ids)
    assert set(outcome.quarantined_ids) <= truth.affected_ids
    assert outcome.root_rollout_value.recovery >= outcome.root_base_value.recovery - 1e-12
