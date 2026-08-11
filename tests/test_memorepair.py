import unittest

import _path  # noqa: F401

from mcx.memorepair import (
    Artifact,
    Candidate,
    affected_cascade,
    maximum_predecessor_closure,
    plan_repair,
)


class TestMemoRepair(unittest.TestCase):
    def test_cascade_uses_only_directed_influence_reachability(self):
        edges = {("s", "a"), ("a", "b"), ("x", "y")}
        self.assertEqual(affected_cascade({"s"}, edges), {"s", "a", "b"})

    def test_min_cut_enforces_predecessor_closure(self):
        candidates = {
            "a": Candidate("a", "recompute", (), True, 0.0, 1.0),
            "b": Candidate("b", "regen", ("a",), True, 2.0, 1.0),
        }
        self.assertEqual(maximum_predecessor_closure(candidates, 0.3), {"a", "b"})

    def test_min_cut_rejects_profitable_dependent_of_non_executable_node(self):
        candidates = {
            "a": Candidate("a", "recompute", (), False, 1.0, 1.0),
            "b": Candidate("b", "regen", ("a",), True, 100.0, 1.0),
        }
        self.assertEqual(maximum_predecessor_closure(candidates, 0.3), set())

    def test_validation_failure_blocks_dependent_publication(self):
        artifacts = {
            "s": Artifact("s"),
            "a": Artifact("a"),
            "b": Artifact("b", kind="summary"),
        }
        plan = plan_repair(
            artifacts, {("s", "a"), ("a", "b")}, {"s"},
            validation={"a": False, "b": True},
        )
        self.assertEqual(plan.selected, {"a", "b"})
        self.assertEqual(plan.republished, set())
        self.assertEqual(plan.validation_failed, {"a", "b"})

    def test_missing_root_edge_hides_entire_cascade(self):
        artifacts = {node: Artifact(node) for node in ("s", "a", "b")}
        plan = plan_repair(artifacts, {("a", "b")}, {"s"})
        self.assertEqual(plan.cascade, {"s"})
        self.assertEqual(plan.selected, set())


if __name__ == "__main__":
    unittest.main()
