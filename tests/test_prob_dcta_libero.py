import json
from pathlib import Path
import unittest

from mcx.directional_transition import LocalTransitionParameters
from mcx.prob_dcta_libero import (
    build_composite_ledgers, build_joint_posterior, canonical_hash,
)


class ProbDCTALiberoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path("results/memory_libero_external_v1_generation.json")
        cls.generation = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def test_composite_public_private_separation_and_counts(self):
        if self.generation is None:
            self.skipTest("external generation artifact unavailable")
        public, private = build_composite_ledgers(self.generation, "abc")
        self.assertEqual(public["archive_count"], 1005)
        self.assertEqual(private["archive_count"], 1005)
        self.assertEqual(private["public_payload_sha256"], canonical_hash(public))
        row = public["archives"][0]
        labels = private["archives"][0]
        self.assertNotIn("active_source_id", row)
        self.assertNotIn("affected_ids", row)
        self.assertNotIn("recommended_policy_id", json.dumps(row["memories"]))
        self.assertIn("active_source_id", labels)
        self.assertEqual(len(row["source_ids"]), 3)
        self.assertEqual(len(row["candidate_ids"]), 9)

    def test_joint_posterior_is_normalized_and_truth_supported(self):
        if self.generation is None:
            self.skipTest("external generation artifact unavailable")
        public, private = build_composite_ledgers(self.generation, "abc")
        params = LocalTransitionParameters(.08, 1.0, -.72, 1.42, 0.0, .1, 105)
        for public_row, private_row in zip(public["archives"][:15], private["archives"][:15]):
            posterior = build_joint_posterior(public_row, params)
            self.assertAlmostEqual(sum(world.weight for world in posterior.worlds), 1.0)
            self.assertTrue(any(
                world.source_id == private_row["active_source_id"]
                and world.affected_ids == frozenset(private_row["affected_ids"])
                for world in posterior.worlds
            ))


if __name__ == "__main__":
    unittest.main()
