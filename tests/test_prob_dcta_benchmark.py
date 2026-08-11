import unittest

from mcx.prob_dcta_benchmark import (
    build_latent_posterior, evaluate_instance, frozen_prob_dcta_instances,
    run_latent_policy,
)


class ProbDCTABenchmarkTests(unittest.TestCase):
    def test_factorial_is_complete_and_normalized(self):
        instances = frozen_prob_dcta_instances()
        self.assertEqual(len(instances), 60)
        self.assertEqual(
            {instance.confidence for instance in instances},
            {"known", "high", "medium", "uniform", "wrong60"},
        )
        for instance in instances:
            self.assertAlmostEqual(sum(world.weight for world in instance.truth.worlds), 1.0)
            self.assertAlmostEqual(sum(world.weight for world in instance.belief.worlds), 1.0)
            self.assertEqual(len(instance.truth.candidates), 9)

    def test_replay_updates_origin_probability(self):
        posterior = build_latent_posterior({"sa": .6, "sb": .2, "sc": .2}, level=0)
        negative = posterior.condition("a1", 0)
        positive = posterior.condition("a1", 1)
        self.assertLess(negative.source_probabilities()["sa"], .6)
        self.assertAlmostEqual(positive.source_probabilities()["sa"], 1.0)

    def test_all_methods_respect_budget(self):
        instance = frozen_prob_dcta_instances()[1]
        world = instance.truth.worlds[0]
        for method in ("static_risk", "positive_only_risk", "top1_dcta", "source_ig",
                       "source_then_dcta", "ens", "prob_dcta"):
            outcome = run_latent_policy(
                instance.belief, world, instance.budget,
                method=method, weights=instance.harm_weights,
            )
            self.assertEqual(len(outcome.replayed_ids), instance.budget)
            self.assertEqual(len(set(outcome.replayed_ids)), instance.budget)

    def test_ens_respects_budget_larger_than_half_the_pool(self):
        instance = frozen_prob_dcta_instances()[1]
        outcome = run_latent_policy(
            instance.belief, instance.truth.worlds[0], 6,
            method="ens", weights=instance.harm_weights,
        )
        self.assertEqual(len(outcome.replayed_ids), 6)
        self.assertEqual(len(set(outcome.replayed_ids)), 6)

    def test_known_origin_reduces_exactly_to_top1_dcta(self):
        for instance in frozen_prob_dcta_instances():
            if instance.confidence != "known":
                continue
            outcomes = evaluate_instance(instance)
            for metric in ("expected_weighted_utility", "expected_discoveries",
                           "expected_harm_recall"):
                self.assertAlmostEqual(
                    outcomes["prob_dcta"][metric], outcomes["top1_dcta"][metric]
                )

    def test_oracle_upper_bounds_implemented_methods(self):
        for instance in frozen_prob_dcta_instances():
            outcomes = evaluate_instance(instance)
            oracle = outcomes["exact_bayes_oracle"]["expected_weighted_utility"]
            for method in ("top1_dcta", "source_ig", "source_then_dcta", "ens", "prob_dcta"):
                self.assertLessEqual(outcomes[method]["expected_weighted_utility"], oracle + 1e-9)


if __name__ == "__main__":
    unittest.main()
