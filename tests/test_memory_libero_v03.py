import unittest

from mcx.memory_libero_v03 import (
    branch_belief, build_archive, discovery_case, fit_evidence,
    is_strict_record, mask_edges,
)


def _record(name="fixture", split="development"):
    def memory(policy, lesson):
        return {
            "recommended_policy_id": policy, "lesson": lesson,
            "cited_memory_ids": [], "expected_outcome": "task completed",
        }
    affected = []
    for depth in range(1, 4):
        affected.append({
            "memory_id": f"a{depth}",
            "factual": {"parsed": memory("donor", f"reuse a broad routine cautiously at stage {depth}")},
            "counterfactual": {"parsed": memory("native", f"use the exact demonstrated routine at stage {depth}")},
        })
    clean = []
    for branch in range(3):
        clean.append({
            "memories": [
                {"memory_id": f"c{branch}_{depth}", "generation": {"parsed": memory(
                    f"clean{branch}", f"preserve exact target constraints in clean stage {depth}"
                )}}
                for depth in range(1, 4)
            ]
        })
    return {
        "archive_id": name, "suite": "libero_fixture", "split": split,
        "target": {"target_language": "place the object in the basket"},
        "native_policy_id": "native", "donor_policy_id": "donor",
        "invalid_source": {"memory_id": "source", **memory(
            "donor", "a broad procedure transfers without adapting target constraints"
        )},
        "corrected_source": {"memory_id": "source", **memory(
            "native", "use the exact target demonstration and preserve constraints"
        )},
        "affected_branch": affected, "clean_branches": clean,
    }


class TestMemoryLiberoV03(unittest.TestCase):
    def test_strict_adapter_hides_policy_handles(self):
        record = _record()
        self.assertTrue(is_strict_record(record))
        archive = build_archive(record)
        case = discovery_case(archive, archive.true_edges)
        for memory in case.memories:
            self.assertNotIn("donor", memory.content)
            self.assertNotIn("native", memory.content)

    def test_continuous_belief_normalizes(self):
        archives = [build_archive(_record("one")), build_archive(_record("two"))]
        evidence = fit_evidence(archives)
        self.assertGreaterEqual(evidence.affected_variance, 0.25)
        self.assertGreaterEqual(evidence.clean_variance, 0.25)
        belief = branch_belief(archives[0], archives[0].true_edges, evidence, 0.8, 0.1)
        self.assertAlmostEqual(sum(world.weight for world in belief.worlds), 1.0)

    def test_deleted_mask_forces_source_edge_missing(self):
        archive = build_archive(_record())
        direct = (archive.source_id, archive.branch_ids[0][0])
        self.assertNotIn(direct, mask_edges(archive, "deleted", 0))
        self.assertNotIn(direct, mask_edges(archive, "deleted_spurious", 0))


if __name__ == "__main__":
    unittest.main()
