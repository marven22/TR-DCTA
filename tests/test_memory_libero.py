import unittest

from mcx.memory_libero import (
    branch_belief, build_archive, clue, discovery_case, mask_edges,
    possible_chronological_edges,
)


def _memory(policy, cited):
    return {
        "recommended_policy_id": policy,
        "lesson": f"reuse {policy} to grasp the black bowl and place it on the plate",
        "cited_memory_ids": cited,
        "expected_outcome": "bowl on plate",
    }


def fixture_record():
    archive_id = "fixture_archive"
    affected = []
    for depth in range(1, 4):
        memory_id = f"affected_{depth}"
        affected.append({
            "memory_id": memory_id,
            "factual": {"parsed": _memory("donor", ["source" if depth == 1 else f"affected_{depth-1}"])},
            "counterfactual": {"parsed": _memory("native", ["source" if depth == 1 else f"affected_{depth-1}"])},
        })
    clean = []
    for branch in range(1, 4):
        memories = []
        for depth in range(1, 4):
            memories.append({
                "memory_id": f"clean_{branch}_{depth}",
                "generation": {"parsed": _memory(f"clean_policy_{branch}", [])},
            })
        clean.append({
            "branch": branch, "task_language": f"clean task {branch}",
            "memories": memories,
        })
    return {
        "archive_id": archive_id,
        "target": {"target_language": "target task"},
        "native_policy_id": "native", "donor_policy_id": "donor",
        "invalid_source": {"memory_id": "source", **_memory("donor", [])},
        "corrected_source": {"memory_id": "source", **_memory("native", [])},
        "affected_branch": affected, "clean_branches": clean,
    }


class TestMemoryLibero(unittest.TestCase):
    def setUp(self):
        self.archive = build_archive(fixture_record())

    def test_adapter_anonymizes_branch_revealing_ids(self):
        self.assertEqual(len(self.archive.memories), 13)
        self.assertEqual(len(self.archive.true_edges), 9)
        for node in self.archive.memories:
            self.assertTrue(node.startswith("m_"))
            self.assertNotIn("affected", node)
            self.assertNotIn("clean", node)

    def test_deleted_mask_is_deterministic_and_never_restores_direct_edge(self):
        left = mask_edges(self.archive, "deleted", 4)
        right = mask_edges(self.archive, "deleted", 4)
        direct = (self.archive.source_id, self.archive.branch_ids[0][0])
        self.assertEqual(left, right)
        self.assertNotIn(direct, left)

    def test_spurious_edges_are_false_chronological_edges(self):
        deleted = mask_edges(self.archive, "deleted", 2)
        noisy = mask_edges(self.archive, "deleted_spurious", 2)
        additions = noisy - deleted
        self.assertEqual(len(additions), 2)
        self.assertTrue(additions.isdisjoint(self.archive.true_edges))
        self.assertTrue(additions.issubset(possible_chronological_edges(self.archive)))

    def test_belief_normalizes_and_case_has_only_masked_parents(self):
        edges = mask_edges(self.archive, "deleted_spurious", 1)
        belief = branch_belief(self.archive, edges, 0.5, 0.03, 0.8, 0.2)
        self.assertAlmostEqual(sum(world.weight for world in belief.worlds), 1.0)
        case = discovery_case(self.archive, edges)
        observed = {
            (parent, memory.memory_id)
            for memory in case.memories for parent in memory.parent_memory_ids
        }
        self.assertEqual(observed, set(edges))


if __name__ == "__main__":
    unittest.main()
