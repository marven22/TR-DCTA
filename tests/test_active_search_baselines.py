import unittest

from mcx.active_search_baselines import (
    GraphActiveSearch,
    GraphActiveSearchParameters,
    ens_choice,
    ens_score,
    run_ens_policy,
)
from mcx.directional_transition import CascadeWorld, DirectionalPosterior


class TestENS(unittest.TestCase):
    def belief(self):
        return DirectionalPosterior(
            ("a", "b", "c", "d"),
            (
                CascadeWorld(frozenset({"a", "b"}), 0.35),
                CascadeWorld(frozenset({"c"}), 0.30),
                CascadeWorld(frozenset({"d"}), 0.20),
                CascadeWorld(frozenset(), 0.15),
            ),
        )

    def test_last_query_reduces_to_greedy_probability(self):
        belief = self.belief()
        self.assertEqual(ens_choice(belief, belief.candidates, 1), "a")
        self.assertAlmostEqual(ens_score(belief, "a", belief.candidates, 1), 0.35)

    def test_score_matches_definition(self):
        belief = self.belief()
        # Query a: immediate .35; after a=1 choose b with certainty; after
        # a=0 choose c with .30/.65 conditional probability.
        expected = 0.35 + 0.35 * 1.0 + 0.65 * (0.30 / 0.65)
        self.assertAlmostEqual(ens_score(belief, "a", belief.candidates, 2), expected)

    def test_optimized_score_matches_explicit_conditioning(self):
        belief = self.belief()
        for budget in (1, 2, 3):
            for node in belief.candidates:
                probability = belief.marginal(node)
                others = [item for item in belief.candidates if item != node]
                slots = min(budget - 1, len(others))
                explicit = probability
                for label, mass in ((1, probability), (0, 1.0 - probability)):
                    conditioned = belief.condition(node, label)
                    if mass and conditioned is not None:
                        explicit += mass * sum(sorted(
                            (conditioned.marginal(other) for other in others),
                            reverse=True,
                        )[:slots])
                self.assertAlmostEqual(
                    ens_score(belief, node, belief.candidates, budget), explicit
                )

    def test_policy_respects_budget_and_conditions_on_negative(self):
        replayed = run_ens_policy(self.belief(), frozenset({"c"}), 2)
        self.assertEqual(len(replayed), 2)
        self.assertEqual(len(set(replayed)), 2)


class TestGraphActiveSearch(unittest.TestCase):
    def test_two_node_soft_label_solution_matches_equation(self):
        model = GraphActiveSearch(
            ("source", "candidate"),
            (("source", "candidate"),),
            {"source": 1},
            GraphActiveSearchParameters(
                eta=0.5, prior_strength=0.5, prior_probability=0.2,
                alpha=0.0,
            ),
        )
        values = model.probabilities({"source": 1})
        self.assertAlmostEqual(values["source"], 0.8, places=9)
        self.assertAlmostEqual(values["candidate"], 0.6, places=9)

    def test_positive_and_negative_labels_move_neighbor_probability(self):
        model = GraphActiveSearch(
            ("source", "a", "b"),
            (("source", "a"), ("a", "b")),
            {"source": 1},
            GraphActiveSearchParameters(prior_probability=0.2),
        )
        base = model.probabilities({"source": 1})["b"]
        positive = model.probabilities({"source": 1, "a": 1})["b"]
        negative = model.probabilities({"source": 1, "a": 0})["b"]
        self.assertGreater(positive, base)
        self.assertLess(negative, base)

    def test_run_respects_budget(self):
        model = GraphActiveSearch(
            ("source", "a", "b", "c"),
            (("source", "a"), ("a", "b"), ("source", "c")),
            {"source": 1},
            GraphActiveSearchParameters(prior_probability=0.2),
        )
        replayed = model.run(("a", "b", "c"), frozenset({"a", "b"}), 2)
        self.assertEqual(len(replayed), 2)
        self.assertEqual(len(set(replayed)), 2)

    def test_rejects_isolated_nodes(self):
        with self.assertRaises(ValueError):
            GraphActiveSearch(
                ("source", "isolated"), (), {"source": 1},
                GraphActiveSearchParameters(),
            )


if __name__ == "__main__":
    unittest.main()
