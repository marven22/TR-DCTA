import unittest

from mcx.memaudit_libero import (
    memory_text,
    parse_selected_memory,
    policy_harm,
    retrieve_by_similarity,
    selection_prompt,
    symmetric_knn,
)


class MemAuditLiberoTests(unittest.TestCase):
    def setUp(self):
        self.memories = {
            "a": {"lesson": "use a", "expected_outcome": "done",
                  "recommended_policy_id": "native"},
            "b": {"lesson": "use b", "expected_outcome": "failed",
                  "recommended_policy_id": "donor"},
            "c": {"lesson": "use c", "expected_outcome": "done",
                  "recommended_policy_id": "native"},
        }

    def test_observable_text_and_prompt_hide_policy_ids(self):
        self.assertEqual(memory_text(self.memories["a"]),
                         "Lesson: use a\nExpected outcome: done")
        prompt = selection_prompt("do task", ("a", "b"), self.memories)
        self.assertIn("use a", prompt)
        self.assertNotIn("native", prompt)
        self.assertNotIn("donor", prompt)

    def test_retrieval_exclusion_and_ties(self):
        result = retrieve_by_similarity(
            ("a", "b", "c"), {"a": .8, "b": .8, "c": .9},
            {"a": 1, "b": 0, "c": 2}, 2, excluded=("c",),
        )
        self.assertEqual(result, ("b", "a"))

    def test_parse_exact_json_and_fence(self):
        self.assertEqual(parse_selected_memory('{"memory_id":"a"}', ("a",)), "a")
        self.assertEqual(parse_selected_memory('```json\n{"memory_id":"a"}\n```', ("a",)), "a")
        with self.assertRaises(ValueError):
            parse_selected_memory('{"memory_id":"missing"}', ("a",))

    def test_knn_and_binary_policy_harm(self):
        similarities = {
            ("a", "b"): .9, ("a", "c"): .2,
            ("b", "a"): .9, ("b", "c"): .7,
            ("c", "a"): .2, ("c", "b"): .7,
        }
        graph = symmetric_knn(("a", "b", "c"), similarities, 1)
        self.assertEqual(graph, {"a": ("b",), "b": ("a",), "c": ("b",)})
        outcomes = {"native": True, "donor": False}
        self.assertEqual(policy_harm("a", self.memories, outcomes), 0.0)
        self.assertEqual(policy_harm("b", self.memories, outcomes), 1.0)


if __name__ == "__main__":
    unittest.main()
