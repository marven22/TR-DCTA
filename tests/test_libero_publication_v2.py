import json
from pathlib import Path
import unittest

from mcx.libero_publication_v2 import donor_order, feasibility_gate, validate_manifest


class LiberoPublicationV2Tests(unittest.TestCase):
    def manifest(self):
        return json.loads(Path("configs/prob_dcta_libero_v2_heldout_manifest.json").read_text())

    def test_manifest_is_exact_and_frozen(self):
        validate_manifest(self.manifest())

    def test_donor_order_is_deterministic_and_excludes_target(self):
        first = donor_order("libero_90", 21, 90)
        self.assertEqual(first, donor_order("libero_90", 21, 90))
        self.assertEqual(len(first), 89)
        self.assertNotIn(21, first)

    def test_feasibility_gate_enforces_size_and_diversity(self):
        manifest = self.manifest()
        diverse = ([{"suite": "libero_90"}] * 16
                   + [{"suite": "libero_spatial"}] * 4
                   + [{"suite": "libero_object"}] * 4)
        self.assertTrue(feasibility_gate(diverse, manifest)["passed"])
        concentrated = [{"suite": "libero_90"}] * 24
        self.assertFalse(feasibility_gate(concentrated, manifest)["passed"])


if __name__ == "__main__":
    unittest.main()
