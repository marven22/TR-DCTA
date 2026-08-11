import unittest

from mcx.memory_libero_external import join_archive


class MemoryLiberoExternalTests(unittest.TestCase):
    def test_public_private_join_is_explicit(self):
        public = {
            "archive_id": "a", "suite": "libero_90", "split": "external_test",
            "source_id": "s", "candidate_ids": ["x", "y"],
            "formation_edges": [["s", "x"], ["x", "y"]],
            "memories": {"s": {"lesson": "source"}, "x": {"lesson": "x"},
                         "y": {"lesson": "y"}},
            "created_at": {"s": 0, "x": 1, "y": 2},
            "direct_gateways": ["x"], "target_language": "do task",
        }
        archive = join_archive(public, {"archive_id": "a", "affected_ids": ["x"]})
        self.assertEqual(archive.affected_ids, frozenset({"x"}))
        self.assertEqual(archive.true_edges, frozenset({("s", "x"), ("x", "y")}))

    def test_join_rejects_unknown_private_candidate(self):
        public = {
            "archive_id": "a", "suite": "libero_90", "split": "external_test",
            "source_id": "s", "candidate_ids": ["x"],
            "formation_edges": [["s", "x"]],
            "memories": {"s": {}, "x": {}}, "created_at": {"s": 0, "x": 1},
            "direct_gateways": ["x"], "target_language": "task",
        }
        with self.assertRaises(ValueError):
            join_archive(public, {"archive_id": "a", "affected_ids": ["z"]})


if __name__ == "__main__":
    unittest.main()
