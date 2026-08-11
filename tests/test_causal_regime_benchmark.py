import unittest

from mcx.causal_regime_benchmark import (
    expected_outcomes, frozen_instances, run_policy, tempered_posterior,
)


class CausalRegimeBenchmarkTests(unittest.TestCase):
    def test_frozen_factorial_is_complete_and_normalized(self):
        instances = frozen_instances()
        self.assertEqual(len(instances), 20)
        self.assertEqual(
            {instance.regime for instance in instances},
            {"chain_screening", "exclusive_branches", "noisy_or_merge",
             "heterogeneous", "independent_control"},
        )
        for instance in instances:
            self.assertAlmostEqual(
                sum(world.weight for world in instance.posterior.worlds), 1.0
            )
            self.assertLessEqual(len(instance.posterior.candidates), 9)
            self.assertTrue(all(world.weight > 0 for world in instance.posterior.worlds))

    def test_policies_respect_budget_and_truth(self):
        instance = frozen_instances()[0]
        for world in instance.posterior.worlds:
            outcome = run_policy(
                instance.posterior, world.affected_ids, instance.budget,
                update="full", acquisition="risk", weights=instance.harm_weights,
            )
            self.assertEqual(len(outcome.replayed_ids), instance.budget)
            self.assertEqual(len(set(outcome.replayed_ids)), instance.budget)
            self.assertEqual(
                outcome.discoveries,
                len(set(outcome.replayed_ids) & world.affected_ids),
            )

    def test_independent_control_has_no_update_advantage(self):
        controls = [instance for instance in frozen_instances()
                    if instance.regime == "independent_control"]
        for instance in controls:
            outcomes = expected_outcomes(instance)
            self.assertAlmostEqual(
                outcomes["dcta_probability"]["expected_discoveries"],
                outcomes["positive_only_probability"]["expected_discoveries"],
            )
            self.assertAlmostEqual(
                outcomes["dcta_risk"]["expected_weighted_utility"],
                outcomes["positive_only_risk"]["expected_weighted_utility"],
            )

    def test_exact_oracle_upper_bounds_implemented_risk_policies(self):
        for instance in frozen_instances():
            outcomes = expected_outcomes(instance)
            oracle = outcomes["exact_bayes_oracle"]["expected_weighted_utility"]
            for method in ("positive_only_risk", "dcta_risk"):
                self.assertLessEqual(
                    outcomes[method]["expected_weighted_utility"], oracle + 1e-9
                )

    def test_tempering_preserves_support_and_normalization(self):
        posterior = frozen_instances()[0].posterior
        for temperature in (.7, .85, 1.0, 1.15, 1.3):
            tempered = tempered_posterior(posterior, temperature)
            self.assertAlmostEqual(sum(world.weight for world in tempered.worlds), 1.0)
            self.assertEqual(
                {world.affected_ids for world in tempered.worlds},
                {world.affected_ids for world in posterior.worlds},
            )


if __name__ == "__main__":
    unittest.main()
