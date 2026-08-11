import unittest

from mcx.memory_libero_v04 import (
    REGIMES, adaptive_branch_replay, build_archive, discovery_case,
    fit_branch_model, is_strict_record, paired_prompt_invariant,
)


def _memory(policy, lesson):
    return {"recommended_policy_id": policy, "lesson": lesson,
            "cited_memory_ids": [], "expected_outcome": "done"}


def _record(name="fixture", split="development"):
    branches = []
    labels = ((1, 1, 1), (0, 0, 0), (0, 1, 0), (1, 0, 0))
    for b, (regime, branch_labels) in enumerate(zip(REGIMES, labels)):
        memories = []
        for d, label in enumerate(branch_labels, 1):
            factual_policy, counterfactual_policy = ("bad", "good") if label else ("good", "good")
            memories.append({
                "memory_id": f"b{b}d{d}",
                "factual": {"prompt": 'instruction\n{"retrieved_memories":[{"lesson":"bad"}],"task":"same"}',
                            "parsed": _memory(factual_policy, f"source-like branch {b} depth {d}")},
                "counterfactual": {"prompt": 'instruction\n{"retrieved_memories":[{"lesson":"good"}],"task":"same"}',
                                   "parsed": _memory(counterfactual_policy, f"correct branch {b} depth {d}")},
            })
        branches.append({"branch": b + 1, "regime": regime, "memories": memories})
    return {
        "archive_id": name, "suite": "libero_fixture", "split": split,
        "target": {"target_language": "put the mug away"},
        "invalid_source": {"memory_id": "source", **_memory("bad", "reuse the wrong procedure")},
        "corrected_source": {"memory_id": "source", **_memory("good", "use the verified procedure")},
        "policy_success": {"bad": False, "good": True},
        "regimes": list(REGIMES), "branches": branches,
    }


class TestMemoryLiberoV04(unittest.TestCase):
    def test_functional_labels_are_paired_outcome_changes(self):
        record = _record()
        self.assertTrue(is_strict_record(record))
        archive = build_archive(record)
        self.assertEqual(len(archive.affected_ids), 5)
        self.assertTrue(any(0 < sum(n in archive.affected_ids for n in b) < 3
                            for b in archive.branch_ids))

    def test_discovery_features_hide_private_handles_and_counterfactuals(self):
        archive = build_archive(_record())
        case = discovery_case(archive)
        rendered = " ".join(m.content for m in case.memories)
        self.assertNotIn("bad", rendered)
        self.assertNotIn("good", rendered)
        self.assertEqual(len(case.memories), 13)

    def test_adaptive_branch_replay_is_budgeted(self):
        archives = [build_archive(_record("a")), build_archive(_record("b"))]
        model = fit_branch_model(archives)
        replayed, scores = adaptive_branch_replay(archives[0], model, 3)
        self.assertEqual(len(replayed), 3)
        self.assertEqual(len(set(replayed)), 3)
        self.assertEqual(set(replayed), set(scores))

    def test_pair_invariant_rejects_non_memory_confound(self):
        item = _record()["branches"][0]["memories"][0]
        self.assertTrue(paired_prompt_invariant(item))
        item["counterfactual"]["prompt"] = (
            'instruction\n{"retrieved_memories":[{"lesson":"good"}],"task":"changed"}'
        )
        self.assertFalse(paired_prompt_invariant(item))


if __name__ == "__main__":
    unittest.main()
