import unittest

from mcx.memaudit import (
    HarmfulEvent,
    MemAuditParameters,
    consistency_anomaly_scores,
    counterfactual_memory_influence,
    memaudit_rank,
    minmax_normalize,
)


class MemAuditTests(unittest.TestCase):
    def test_counterfactual_influence_aggregates_only_retrieved_memories(self):
        events = (
            HarmfulEvent("e1", 1.0, ("a", "b")),
            HarmfulEvent("e2", 1.0, ("b",)),
        )
        after = {("e1", "a"): 0.0, ("e1", "b"): 0.5, ("e2", "b"): 0.0}
        scores, calls = counterfactual_memory_influence(
            ("a", "b", "c"), events,
            lambda event, memory_id: after[event.event_id, memory_id],
        )
        self.assertEqual(scores, {"a": 1.0, "b": 1.5, "c": 0.0})
        self.assertEqual(calls, 3)

    def test_consistency_anomaly_is_weighted_neighbor_sum(self):
        similarities = {frozenset(("a", "b")): 0.8,
                        frozenset(("a", "c")): 0.5}
        contradictions = {frozenset(("a", "b")): 0.75,
                          frozenset(("a", "c")): 0.2}
        scores = consistency_anomaly_scores(
            ("a", "b", "c"), {"a": ("b", "c")},
            lambda left, right: similarities[frozenset((left, right))],
            lambda left, right: contradictions[frozenset((left, right))],
        )
        self.assertAlmostEqual(scores["a"], 0.8 * 0.75 + 0.5 * 0.2)
        self.assertEqual(scores["b"], 0.0)
        self.assertEqual(scores["c"], 0.0)

    def test_minmax_normalization_and_constant_signal(self):
        self.assertEqual(minmax_normalize({"a": 2.0, "b": 4.0, "c": 3.0}),
                         {"a": 0.0, "b": 1.0, "c": 0.5})
        self.assertEqual(minmax_normalize({"a": 7.0, "b": 7.0}),
                         {"a": 0.0, "b": 0.0})

    def test_fusion_uses_paper_default_alpha_and_deterministic_ties(self):
        event = HarmfulEvent("e", 1.0, ("a", "b"))
        counterfactual = {"a": 0.0, "b": 1.0}
        contradiction = {frozenset(("a", "c")): 0.0,
                         frozenset(("b", "c")): 1.0}
        ranking, calls = memaudit_rank(
            ("a", "b", "c"), (event,),
            lambda _, memory_id: counterfactual[memory_id],
            {"a": ("c",), "b": ("c",), "c": ()},
            lambda _left, _right: 1.0,
            lambda left, right: contradiction[frozenset((left, right))],
            MemAuditParameters(),
        )
        self.assertEqual(calls, 2)
        self.assertEqual([score.memory_id for score in ranking], ["a", "b", "c"])
        self.assertAlmostEqual(ranking[0].detoxification_score, 0.6)
        self.assertAlmostEqual(ranking[1].detoxification_score, 0.4)

    def test_invalid_alpha_and_unknown_event_memory_fail(self):
        with self.assertRaises(ValueError):
            MemAuditParameters(alpha=1.1)
        with self.assertRaises(ValueError):
            counterfactual_memory_influence(
                ("a",), (HarmfulEvent("e", 1.0, ("missing",)),),
                lambda _event, _memory_id: 0.0,
            )


if __name__ == "__main__":
    unittest.main()
