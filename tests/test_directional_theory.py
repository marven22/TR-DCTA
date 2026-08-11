import unittest

from mcx.directional_transition import CascadeWorld, DirectionalPosterior


def chain_posterior(p: float, theta: float) -> DirectionalPosterior:
    return DirectionalPosterior(
        candidates=("a", "b"),
        worlds=(
            CascadeWorld(frozenset(), 1.0 - p),
            CascadeWorld(frozenset({"a"}), p * (1.0 - theta)),
            CascadeWorld(frozenset({"a", "b"}), p * theta),
        )
    ).normalize()


class DirectionalTheoryTests(unittest.TestCase):
    def test_chain_directional_screening_and_amplification(self) -> None:
        posterior = chain_posterior(p=0.4, theta=0.5)

        self.assertAlmostEqual(posterior.marginal("b"), 0.2)
        self.assertAlmostEqual(posterior.condition("a", True).marginal("b"), 0.5)
        self.assertAlmostEqual(posterior.condition("a", False).marginal("b"), 0.0)

    def test_positive_observation_violates_adaptive_diminishing_returns(self) -> None:
        posterior = chain_posterior(p=0.4, theta=0.5)

        before = posterior.marginal("b")
        after_positive_parent = posterior.condition("a", True).marginal("b")

        self.assertGreater(after_positive_parent, before)

    def test_true_marginal_loss_is_bounded_by_twice_calibration_error(self) -> None:
        true = {"a": 0.51, "b": 0.49, "c": 0.20}
        estimated = {"a": 0.46, "b": 0.54, "c": 0.20}
        epsilon = max(abs(estimated[key] - true[key]) for key in true)

        selected = max(estimated, key=estimated.get)
        optimal = max(true, key=true.get)

        self.assertLessEqual(true[optimal] - true[selected], 2.0 * epsilon)


if __name__ == "__main__":
    unittest.main()
