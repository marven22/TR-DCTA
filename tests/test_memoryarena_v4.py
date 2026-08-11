import unittest

import _path  # noqa: F401

from mcx.memoryarena_v4 import (
    ATTACK_TYPES,
    FAMILIES,
    aggregate_v4,
    replace_target_identity,
    unit_specs,
    wilson_interval,
)


class TestMemoryArenaV4(unittest.TestCase):
    def test_frozen_factorial_has_eight_unique_units(self):
        specs = unit_specs()
        self.assertEqual(len(specs), len(FAMILIES) * len(ATTACK_TYPES))
        self.assertEqual(len({spec["unit_id"] for spec in specs}), 8)

    def test_identity_replacement_includes_trailing_alias(self):
        evidence = "Ihuoma Sonia Uche is also called Sonia Uche."
        replaced = replace_target_identity(evidence, "Ihuoma Sonia Uche", "Cory Monteith")
        self.assertEqual(replaced, "Cory Monteith is also called Cory Monteith.")

    def test_identity_replacement_escapes_punctuation(self):
        evidence = "A. Person appeared. A. Person returned."
        replaced = replace_target_identity(evidence, "A. Person", "B Person")
        self.assertEqual(replaced, "B Person appeared. B Person returned.")

    def test_wilson_interval_bounds(self):
        interval = wilson_interval(6, 8)
        self.assertEqual(interval["estimate"], 0.75)
        self.assertGreaterEqual(interval["lower"], 0.0)
        self.assertLessEqual(interval["upper"], 1.0)

    def test_aggregate_requires_all_units(self):
        with self.assertRaises(ValueError):
            aggregate_v4([])


if __name__ == "__main__":
    unittest.main()
