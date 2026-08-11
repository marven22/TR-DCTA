import unittest

import _path  # noqa: F401

from mcx.archive import MemoryArchive
from mcx.tasks import get_task


def _mem(mid, content, created_at=0):
    return {
        "memory_id": mid,
        "content": content,
        "source_cycle": "c",
        "source_task": "t",
        "retrieved_parent_ids": [],
        "true_outcome": "failure",
        "feedback_given": "success",
        "created_at": created_at,
    }


class TestArchive(unittest.TestCase):
    def test_add_and_get(self):
        a = MemoryArchive()
        a.add_memory(_mem("m_001", "collect the key first then open the door"))
        self.assertIn("m_001", a)
        self.assertEqual(a.get("m_001")["memory_id"], "m_001")
        self.assertEqual(len(a), 1)

    def test_duplicate_id_rejected(self):
        a = MemoryArchive()
        a.add_memory(_mem("m_001", "x"))
        with self.assertRaises(ValueError):
            a.add_memory(_mem("m_001", "y"))

    def test_remove(self):
        a = MemoryArchive([_mem("m_001", "x")])
        self.assertTrue(a.remove_memory("m_001"))
        self.assertFalse(a.remove_memory("m_001"))
        self.assertEqual(len(a), 0)

    def test_retrieval_keyword_match(self):
        a = MemoryArchive([
            _mem("m_001", "opening a locked door directly is effective", 1),
            _mem("m_002", "cooking pasta requires boiling water thoroughly", 2),
        ])
        task = get_task("door_01")
        retrieved = a.retrieve_memories(task, top_k=3)
        ids = [m["memory_id"] for m in retrieved]
        self.assertIn("m_001", ids)
        # Unrelated memory should not be retrieved (no keyword overlap).
        self.assertNotIn("m_002", ids)

    def test_retrieval_recency_tiebreak(self):
        a = MemoryArchive([
            _mem("m_001", "locked door key open", 1),
            _mem("m_002", "locked door key open", 5),
        ])
        task = get_task("door_02")
        retrieved = a.retrieve_memories(task, top_k=1)
        self.assertEqual(retrieved[0]["memory_id"], "m_002")

    def test_save_restore_snapshot(self):
        a = MemoryArchive([_mem("m_001", "x")])
        snap = a.save_archive()
        a.add_memory(_mem("m_002", "y"))
        self.assertEqual(len(a), 2)
        a.restore_archive(snap)
        self.assertEqual(a.ids(), ["m_001"])

    def test_snapshot_is_deep_copy(self):
        a = MemoryArchive([_mem("m_001", "x")])
        snap = a.save_archive()
        snap[0]["content"] = "mutated"
        self.assertEqual(a.get("m_001")["content"], "x")


if __name__ == "__main__":
    unittest.main()
