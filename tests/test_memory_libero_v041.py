import unittest

from mcx.memory_libero_v041 import (
    FrontierParameters, V041Archive, counterfactual_delta, discovery_case,
    frontier_replay,
)
from mcx.risk_aware_acis import LogisticCalibrator


class TestMemoryLiberoV041(unittest.TestCase):
    def archive(self):
        memories = {
            "s": {"lesson": "reuse broad wrong routine"},
            "a": {"lesson": "reuse broad routine"},
            "b": {"lesson": "continue broad routine"},
            "c": {"lesson": "verified independent routine"},
        }
        counterfactuals = {
            "a": {"lesson": "use exact verified routine"},
            "b": {"lesson": "continue exact verified routine"},
            "c": {"lesson": "verified independent routine"},
        }
        return V041Archive(
            "fixture", "fixture", "development", "s", ("a", "b", "c"),
            frozenset({("s", "a"), ("a", "b"), ("s", "c")}),
            memories, counterfactuals, {"s": 0, "a": 1, "c": 2, "b": 3},
            frozenset({"a", "b"}), frozenset({"a", "c"}), "task", None,
        )

    def test_counterfactual_delta_and_hidden_case(self):
        archive = self.archive()
        self.assertGreater(counterfactual_delta(archive, "a"), 0)
        case = discovery_case(archive)
        self.assertEqual(case.affected_ids, frozenset({"a", "b"}))
        self.assertNotIn("exact verified", " ".join(m.content for m in case.memories))

    def test_frontier_replay_is_budgeted(self):
        archive = self.archive()
        calibrator = LogisticCalibrator(-1, 1, 0, 1)
        replayed = frontier_replay(
            archive, calibrator, 2, FrontierParameters(4, .7, .5, .25)
        )
        self.assertEqual(len(replayed), 2)
        self.assertEqual(len(set(replayed)), 2)


if __name__ == "__main__":
    unittest.main()
