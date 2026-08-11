import unittest

from mcx.confidence_aware_dcta import (
    confidence_aware_decision, expected_risk_policy_utility,
    run_confidence_aware_dcta,
)
from mcx.prob_dcta_benchmark import (
    LatentSourcePosterior, LatentSourceWorld, run_latent_policy,
)


class ConfidenceAwareDCTATests(unittest.TestCase):
    def posterior(self):
        return LatentSourcePosterior(
            ("a", "b", "c"), ("s1", "s2"), (
                LatentSourceWorld("s1", frozenset({"a", "b"}), .55),
                LatentSourceWorld("s1", frozenset({"a"}), .15),
                LatentSourceWorld("s2", frozenset({"c"}), .30),
            ),
        )

    def test_expected_value_matches_world_enumeration(self):
        posterior = self.posterior(); weights = {"a": 1.0, "b": 2.0, "c": 3.0}
        for mode, method in (("hard", "top1_dcta"), ("probabilistic", "prob_dcta")):
            expected = expected_risk_policy_utility(posterior, 2, mode=mode, weights=weights)
            enumerated = sum(
                world.weight * run_latent_policy(
                    posterior, world, 2, method=method, weights=weights,
                ).weighted_utility
                for world in posterior.worlds
            )
            self.assertAlmostEqual(expected, enumerated)

    def test_selector_chooses_larger_expected_value(self):
        posterior = self.posterior(); weights = {"a": 1.0, "b": 2.0, "c": 3.0}
        decision = confidence_aware_decision(posterior, 2, weights)
        self.assertEqual(
            decision.mode,
            "hard" if decision.hard_expected_utility >= decision.probabilistic_expected_utility
            else "probabilistic",
        )

    def test_run_matches_selected_constituent(self):
        posterior = self.posterior(); weights = {"a": 1.0, "b": 2.0, "c": 3.0}
        truth = posterior.worlds[0]
        result = run_confidence_aware_dcta(posterior, truth, 2, weights=weights)
        method = "top1_dcta" if result.decision.mode == "hard" else "prob_dcta"
        expected = run_latent_policy(posterior, truth, 2, method=method, weights=weights)
        self.assertEqual(result.policy_outcome.replayed_ids, expected.replayed_ids)


if __name__ == "__main__":
    unittest.main()

