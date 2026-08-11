import unittest

from mcx.prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld
from mcx.causal_regime_benchmark import exact_weighted_policy_value
from mcx.publication_v2_oracle import ExactBayesReplayPlanner, hindsight_selection


class PublicationV2OracleTests(unittest.TestCase):
    def posterior(self):
        return LatentSourcePosterior(
            ("a", "b"), ("s1", "s2"), (
                LatentSourceWorld("s1", frozenset({"a"}), 0.75),
                LatentSourceWorld("s2", frozenset({"b"}), 0.25),
            ),
        )

    def test_hindsight_enumeration_matches_scalable_solution(self):
        weights = {"a": 1.0, "b": 2.0, "c": 3.0}
        truth = frozenset({"a", "c"})
        exact = hindsight_selection(tuple(weights), truth, 2, weights, enumerate_subsets=True)
        fast = hindsight_selection(tuple(weights), truth, 2, weights)
        self.assertEqual(set(exact), {"a", "c"})
        self.assertEqual(set(fast), {"a", "c"})

    def test_exact_planner_maximizes_expected_reward(self):
        planner = ExactBayesReplayPlanner(self.posterior(), {"a": 1.0, "b": 2.0})
        # Querying b has expected immediate utility .5 versus .75 for a; with
        # one replay the higher-weight, lower-probability item is optimal.
        self.assertAlmostEqual(planner.expected_value(1), 0.75)
        outcome = planner.run(frozenset({"b"}), 1)
        self.assertEqual(outcome.replayed_ids, ("a",))
        self.assertEqual(outcome.realized_weighted_utility, 0.0)

    def test_adaptive_two_step_value(self):
        planner = ExactBayesReplayPlanner(self.posterior(), {"a": 1.0, "b": 2.0})
        self.assertAlmostEqual(planner.expected_value(2), 1.25)
        self.assertAlmostEqual(
            planner.expected_value(2),
            exact_weighted_policy_value(self.posterior(), 2, {"a": 1.0, "b": 2.0}),
        )
        outcome = planner.run(frozenset({"a"}), 2)
        self.assertEqual(set(outcome.replayed_ids), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
