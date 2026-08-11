import json
from pathlib import Path
import unittest

from mcx.prob_dcta_libero_baselines import run_prior_weighted_acis_risk
from mcx.risk_aware_acis import LogisticCalibrator


class ProbDCTALiberoBaselineTests(unittest.TestCase):
    def test_prior_weighted_acis_is_budgeted_and_adaptive(self):
        path = Path("results/prob_dcta_libero_multi_origin_v1_public.json")
        private_path = Path("results/prob_dcta_libero_multi_origin_v1_private.json")
        if not path.exists() or not private_path.exists():
            self.skipTest("multi-origin ledgers unavailable")
        public = json.loads(path.read_text(encoding="utf-8"))["archives"][0]
        private = json.loads(private_path.read_text(encoding="utf-8"))["archives"][0]
        calibrator = LogisticCalibrator(-1.0, 1.0, 1.0, 1.0)
        replayed = run_prior_weighted_acis_risk(
            public, frozenset(private["affected_ids"]), 4, calibrator
        )
        self.assertEqual(len(replayed), 4)
        self.assertEqual(len(set(replayed)), 4)
        self.assertTrue(set(replayed).issubset(public["candidate_ids"]))


if __name__ == "__main__":
    unittest.main()

