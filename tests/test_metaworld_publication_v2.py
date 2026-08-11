import json
from pathlib import Path
import unittest

from mcx.metaworld_publication_v2 import (
    action_is_valid, donor_order, task_language, validate_config,
)


class MetaWorldPublicationV2Tests(unittest.TestCase):
    def config(self):
        return json.loads(Path("configs/prob_dcta_metaworld_v2_screen.json").read_text())

    def test_config_is_frozen(self):
        validate_config(self.config())

    def test_donor_order_is_deterministic(self):
        tasks = ("reach-v3", "push-v3", "pick-place-v3")
        self.assertEqual(donor_order("reach-v3", tasks), donor_order("reach-v3", tasks))
        self.assertNotIn("reach-v3", donor_order("reach-v3", tasks))

    def test_language_and_action_validation(self):
        self.assertEqual(task_language("pick-place-wall-v3"), "pick place wall")
        self.assertTrue(action_is_valid((0, 1, 2, 3)))
        self.assertFalse(action_is_valid((0, 1, 2)))
        self.assertFalse(action_is_valid((0, 1, 2, float("nan"))))


if __name__ == "__main__":
    unittest.main()
