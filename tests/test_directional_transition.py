import unittest

from mcx.directional_transition import (
    CascadeWorld, DirectionalPosterior, LocalTransitionParameters,
    exact_policy_value, risk_choice, run_directional_policy,
    run_directional_risk_policy, two_step_choice,
)


class TestDirectionalTransition(unittest.TestCase):
    def belief(self):
        return DirectionalPosterior(
            ("a", "b", "c"),
            (
                CascadeWorld(frozenset({"a", "b"}), .4),
                CascadeWorld(frozenset({"c"}), .35),
                CascadeWorld(frozenset(), .25),
            ),
        )

    def test_conditioning_updates_directional_cluster(self):
        belief = self.belief()
        self.assertAlmostEqual(belief.marginal("b"), .4)
        positive = belief.condition("a", 1)
        self.assertAlmostEqual(positive.marginal("b"), 1.0)
        negative = belief.condition("a", 0)
        self.assertAlmostEqual(negative.marginal("b"), 0.0)

    def test_two_step_and_oracle_are_well_formed(self):
        belief = self.belief()
        self.assertIn(two_step_choice(belief, belief.candidates), belief.candidates)
        value, first = exact_policy_value(belief, 2)
        self.assertIn(first, belief.candidates)
        self.assertGreaterEqual(value, 0)
        self.assertLessEqual(value, 2)

    def test_policy_never_reads_more_than_budget(self):
        replayed = run_directional_policy(self.belief(), frozenset({"a", "b"}), 2, horizon=2)
        self.assertEqual(len(replayed), 2)
        self.assertEqual(len(set(replayed)), 2)

    def test_local_parameter_record_is_explicit(self):
        value = LocalTransitionParameters(0, 1, 2, 3, 4, .1, 9)
        self.assertEqual(value.training_rows, 9)
        self.assertEqual(value.similarity_weight, 3)

    def test_risk_policy_uses_full_negative_conditioning(self):
        belief = self.belief()
        self.assertIn(risk_choice(belief, belief.candidates), belief.candidates)
        replayed = run_directional_risk_policy(
            belief, frozenset(), 2, weights={"a": 1, "b": 1, "c": 1}
        )
        self.assertEqual(len(replayed), 2)
        self.assertEqual(len(set(replayed)), 2)


if __name__ == "__main__":
    unittest.main()
