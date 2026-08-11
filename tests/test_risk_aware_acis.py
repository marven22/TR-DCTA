import unittest

import _path  # noqa: F401

from mcx.memoryarena_v6 import DiscoveryCase, ObservableMemory
from mcx.risk_aware_acis import (
    LogisticCalibrator,
    adaptive_three_signal_replay,
    fit_monotone_logistic,
    oracle_prefix_training_rows,
    three_signals,
)


def fixture_case():
    return DiscoveryCase(
        "risk-fixture",
        "s",
        (
            ObservableMemory("s", "refund source", 0, (), "", (), "handle refund"),
            ObservableMemory("d", "refund clean", 1, (), "", (), "write refund"),
            ObservableMemory("a", "refund coded policy", 2, (), "", ("s",), "handle refund"),
            ObservableMemory("b", "workflow", 3, ("a",), "", (), "make workflow"),
        ),
        frozenset(("a", "b")),
    )


class TestRiskAwareACIS(unittest.TestCase):
    def test_three_signals_use_only_observable_anchor_relationships(self):
        signals = three_signals(fixture_case(), "a", {"s"})
        self.assertEqual(signals.provenance, 1.0)
        self.assertEqual(signals.formation_task, 1.0)
        self.assertGreater(signals.content, 0.0)

    def test_training_rows_include_both_classes(self):
        rows = oracle_prefix_training_rows(fixture_case())
        labels = {key[-1] for key in rows}
        self.assertEqual(labels, {0, 1})

    def test_logistic_slopes_are_monotone(self):
        rows = {
            (0.0, 0.0, 0.0, 0): 20,
            (1.0, 1.0, 1.0, 1): 20,
        }
        model = fit_monotone_logistic(rows)
        self.assertGreaterEqual(model.provenance_weight, 0.0)
        self.assertGreaterEqual(model.formation_task_weight, 0.0)
        self.assertGreaterEqual(model.content_weight, 0.0)
        self.assertGreater(
            model.probability(three_signals(fixture_case(), "a", {"s"})),
            model.probability(three_signals(fixture_case(), "d", {"s"})),
        )

    def test_risk_replay_reads_label_only_for_chosen_candidate(self):
        model = LogisticCalibrator(-2.0, 2.0, 1.0, 1.0)
        result = adaptive_three_signal_replay(
            fixture_case(), 2, "acis_risk", model
        )
        self.assertEqual(len(result["replayed_ids"]), 2)
        self.assertTrue(set(result["repaired_ids"]).issubset({"a", "b"}))

    def test_impact_only_prefers_gateway_to_later_candidate(self):
        case = DiscoveryCase(
            "impact-gateway",
            "s",
            (
                ObservableMemory("s", "source", 0),
                ObservableMemory("isolated", "alpha", 1),
                ObservableMemory("gateway", "beta", 2),
                ObservableMemory("child", "gamma", 3, ("gateway",)),
            ),
            frozenset(("gateway", "child")),
        )
        model = LogisticCalibrator(-2.0, 4.0, 0.0, 0.0)
        result = adaptive_three_signal_replay(
            case, 1, "acis_impact", model
        )
        self.assertEqual(result["replayed_ids"], ["gateway"])


if __name__ == "__main__":
    unittest.main()
