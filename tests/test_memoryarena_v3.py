import unittest

import _path  # noqa: F401

from mcx.memoryarena_v3 import POLICIES, build_v3_archives, retrieve


def memory(memory_id, content):
    return {"memory_id": memory_id, "content": content, "parent_memory_ids": []}


class TestMemoryArenaV3(unittest.TestCase):
    def setUp(self):
        self.archive = [
            memory("m1", "Sonia audition university"),
            memory("m2", "Sonia audition"),
            memory("m3", "Tulsidas football Olympics"),
            memory("m4", "Sonia audition and Tulsidas football"),
        ]

    def test_all_frozen_policies_are_implemented(self):
        for policy in POLICIES:
            selected, scores = retrieve(self.archive, "Sonia audition", policy)
            self.assertIsInstance(selected, list)
            self.assertEqual(set(scores), {"m1", "m2", "m3", "m4"})

    def test_semantic_top1_and_top2_rank_by_similarity(self):
        selected, _ = retrieve(self.archive, "Sonia audition", "semantic_top1")
        self.assertEqual([m["memory_id"] for m in selected], ["m2"])
        selected, _ = retrieve(self.archive, "Sonia audition", "semantic_top2")
        self.assertEqual([m["memory_id"] for m in selected], ["m2", "m1"])

    def test_lifecycle_policies(self):
        recent, _ = retrieve(self.archive, "anything", "recency_top1")
        expired, _ = retrieve(self.archive, "anything", "source_expired_all")
        consolidated, _ = retrieve(self.archive, "anything", "consolidation_only")
        self.assertEqual([m["memory_id"] for m in recent], ["m4"])
        self.assertEqual([m["memory_id"] for m in expired], ["m2", "m3", "m4"])
        self.assertEqual([m["memory_id"] for m in consolidated], ["m4"])

    def test_archive_conditions_use_fixed_branches(self):
        bad = {mid: memory(mid, f"bad-{mid}") for mid in ("m1", "m2", "m3", "m4")}
        clean = {mid: memory(mid, f"clean-{mid}") for mid in ("m1", "m2", "m3", "m4")}
        archives = build_v3_archives({"memories": {"corrupted": bad, "corrected": clean}})
        self.assertEqual(
            [m["content"] for m in archives["source_corrected_only"]],
            ["clean-m1", "bad-m2", "clean-m3", "bad-m4"],
        )
        self.assertEqual(
            [m["memory_id"] for m in archives["semantic_deletion"]],
            ["m1", "m3", "m4"],
        )
        self.assertTrue(
            all(m["content"].startswith("clean-") for m in archives["full_repair"])
        )


if __name__ == "__main__":
    unittest.main()
