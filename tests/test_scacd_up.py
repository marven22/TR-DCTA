import unittest

import _path  # noqa: F401

from mcx.scacd_up import (
    FiniteCascadeBelief,
    LatentWorld,
    branch_posterior_under_parameters,
    build_branch_instance,
    build_multicascade_instance,
    exact_policy_value,
    run_belief_policy,
    multicascade_posterior_under_parameters,
    multicascade_posterior_integrated_channel,
)


class TestSCACDUP(unittest.TestCase):
    def test_belief_normalizes_and_conditions(self):
        belief = FiniteCascadeBelief(
            ("a", "b"),
            (
                LatentWorld("left", frozenset(("a",)), 3.0),
                LatentWorld("right", frozenset(("b",)), 1.0),
            ),
        )
        self.assertAlmostEqual(belief.probability("a"), 0.75)
        self.assertEqual(belief.condition((0, 1), "a", 1), (0,))
        self.assertEqual(belief.condition((0, 1), "a", 0), (1,))

    def test_exact_oracle_values_information_from_both_outcomes(self):
        belief = FiniteCascadeBelief(
            ("a", "b", "c"),
            (
                LatentWorld("pair", frozenset(("a", "b")), 0.6),
                LatentWorld("single", frozenset(("c",)), 0.4),
            ),
        )
        value, first = exact_policy_value(belief, 2)
        self.assertAlmostEqual(value, 1.6)
        self.assertEqual(first, "a")

    def test_sampled_branch_instance_is_valid_and_posterior_normalized(self):
        instance = build_branch_instance(seed=7)
        instance.case.validate()
        self.assertAlmostEqual(
            sum(world.weight for world in instance.belief.worlds), 1.0
        )
        self.assertEqual(len(instance.case.affected_ids), 3)

    def test_posterior_can_be_recomputed_under_misspecified_provenance(self):
        instance = build_branch_instance(seed=13)
        plugin = branch_posterior_under_parameters(instance, q=0.99, r=0.01)
        self.assertAlmostEqual(sum(world.weight for world in plugin.worlds), 1.0)
        self.assertEqual(plugin.candidates, instance.belief.candidates)

    def test_policy_never_reads_more_than_budget(self):
        instance = build_branch_instance(seed=11)
        for horizon in (1, 2, None):
            result = run_belief_policy(
                instance.belief, instance.true_world, 3, horizon=horizon
            )
            self.assertEqual(len(result.replayed_ids), 3)
            self.assertTrue(result.discovered_ids.issubset(instance.case.affected_ids))

    def test_multicascade_instance_matches_its_true_world(self):
        instance = build_multicascade_instance(seed=19)
        instance.case.validate()
        self.assertEqual(
            instance.belief.worlds[instance.true_world].affected_ids,
            instance.case.affected_ids,
        )
        self.assertGreaterEqual(sum(depth > 0 for depth in instance.true_depths), 1)

    def test_multicascade_plugin_posterior_is_normalized(self):
        instance = build_multicascade_instance(seed=23)
        plugin = multicascade_posterior_under_parameters(instance, q=0.99, r=0.01)
        self.assertAlmostEqual(sum(world.weight for world in plugin.worlds), 1.0)

    def test_integrated_channel_posterior_is_normalized(self):
        instance = build_multicascade_instance(seed=29)
        integrated = multicascade_posterior_integrated_channel(
            instance, q_alpha=2.0, q_beta=1.0, r_alpha=1.0, r_beta=4.0
        )
        self.assertAlmostEqual(sum(world.weight for world in integrated.worlds), 1.0)
        self.assertEqual(integrated.candidates, instance.belief.candidates)


if __name__ == "__main__":
    unittest.main()
