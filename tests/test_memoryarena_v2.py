import unittest

import _path  # noqa: F401

from mcx.memoryarena_v2 import (
    discovery_metrics,
    recorded_descendants,
    semantic_tokens,
    token_jaccard,
)


class TestMemoryArenaV2(unittest.TestCase):
    def test_hidden_dependency_is_not_in_recorded_lineage(self):
        memories = [
            {"memory_id": "m1", "parent_memory_ids": []},
            {"memory_id": "m2", "parent_memory_ids": []},
            {"memory_id": "m3", "parent_memory_ids": []},
            {"memory_id": "m4", "parent_memory_ids": ["m2", "m3"]},
        ]
        self.assertEqual(recorded_descendants(memories, {"m1"}), set())

    def test_recorded_lineage_finds_visible_transitive_descendants(self):
        memories = [
            {"memory_id": "m1", "parent_memory_ids": []},
            {"memory_id": "m2", "parent_memory_ids": ["m1"]},
            {"memory_id": "m4", "parent_memory_ids": ["m2"]},
        ]
        self.assertEqual(recorded_descendants(memories, {"m1"}), {"m2", "m4"})

    def test_semantic_similarity_is_deterministic_and_ignores_stopwords(self):
        self.assertEqual(semantic_tokens("This memory is about Sonia's audition"), {"sonia", "audition"})
        self.assertGreater(token_jaccard("Sonia audition university", "Sonia university"), 0.5)
        self.assertEqual(token_jaccard("Sonia audition", "Tulsidas Olympics"), 0.0)

    def test_discovery_metrics(self):
        metrics = discovery_metrics({"m2", "m3"}, {"m2", "m4"})
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)


if __name__ == "__main__":
    unittest.main()
