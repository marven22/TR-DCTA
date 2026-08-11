import unittest

import _path  # noqa: F401

from mcx.memoryarena_v5 import (
    CANDIDATES,
    EXPECTED_HASHES,
    PHASE2_ATTACKS,
    PHASE2_ELIGIBLE_IDS,
    SCREEN_TARGET,
    aggregate_screen,
    strip_lineage_metadata,
)


class TestMemoryArenaV5(unittest.TestCase):
    def test_candidate_pool_is_frozen_and_unique(self):
        self.assertEqual(len(CANDIDATES), 30)
        self.assertEqual(len({x.candidate_id for x in CANDIDATES}), 30)
        self.assertEqual(len({x.target_index for x in CANDIDATES}), 30)
        self.assertEqual(SCREEN_TARGET, 20)

    def test_all_candidate_rows_have_hashes(self):
        required = {
            index
            for candidate in CANDIDATES
            for index in (
                candidate.target_index,
                candidate.donor_index,
                candidate.independent_index,
            )
        }
        self.assertEqual(required, set(EXPECTED_HASHES))

    def test_screen_aggregate_preserves_failed_candidates(self):
        screens = [
            {
                "candidate_id": "candidate_01",
                "ordinal": 1,
                "criteria": {"eligible": True, "clean_gate": True},
            },
            {
                "candidate_id": "candidate_02",
                "ordinal": 2,
                "criteria": {"eligible": False, "clean_gate": False},
            },
        ]
        result = aggregate_screen(screens)
        self.assertEqual(result["screened_count"], 2)
        self.assertEqual(result["eligible_count"], 1)
        self.assertEqual(result["screened_candidate_ids"], ["candidate_01", "candidate_02"])
        self.assertEqual(result["criterion_pass_counts"]["clean_gate"], 1)

    def test_hidden_writer_answer_has_no_lineage_metadata(self):
        answer = {
            "entity": "Example Person",
            "reasoning": "from retrieved evidence",
            "memory_ids_used": ["m1"],
        }
        sanitized = strip_lineage_metadata(answer)
        self.assertNotIn("memory_ids_used", sanitized)
        self.assertEqual(sanitized["entity"], "Example Person")

    def test_phase2_population_and_factorial_are_frozen(self):
        self.assertEqual(len(PHASE2_ELIGIBLE_IDS), 15)
        self.assertEqual(len(set(PHASE2_ELIGIBLE_IDS)), 15)
        self.assertEqual(PHASE2_ATTACKS, ("evidence_substitution", "evidence_swap"))


if __name__ == "__main__":
    unittest.main()
