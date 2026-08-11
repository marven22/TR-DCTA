import unittest

import _path  # noqa: F401

from mcx.environment import AVAILABLE_ACTIONS, LockedDoorEnvironment
from mcx.tasks import get_task


class TestEnvironment(unittest.TestCase):
    def setUp(self):
        self.env = LockedDoorEnvironment(seed=42)
        self.task = get_task("door_01")

    def test_correct_plan_succeeds(self):
        plan = ["move_to_key", "pick_up_key", "move_to_door", "open_door", "enter_room"]
        r = self.env.execute(plan, self.task)
        self.assertTrue(r.success)
        self.assertTrue(r.key_collected)
        self.assertTrue(r.door_opened)
        self.assertTrue(r.entered_room)
        self.assertEqual(r.invalid_door_open_attempts, 0)
        self.assertEqual(r.invalid_actions, [])
        self.assertEqual(r.num_actions_attempted, 5)
        self.assertEqual(r.outcome_label(), "success")

    def test_no_key_plan_fails(self):
        plan = ["move_to_door", "open_door", "enter_room"]
        r = self.env.execute(plan, self.task)
        self.assertFalse(r.success)
        self.assertFalse(r.key_collected)
        self.assertFalse(r.door_opened)
        self.assertEqual(r.invalid_door_open_attempts, 1)
        self.assertEqual(r.outcome_label(), "failure")

    def test_pick_up_key_requires_being_at_key(self):
        # Picking up the key before moving to it is invalid.
        plan = ["pick_up_key"]
        r = self.env.execute(plan, self.task)
        self.assertFalse(r.key_collected)
        self.assertEqual(len(r.invalid_actions), 1)
        self.assertEqual(r.invalid_actions[0]["reason"], "not_at_key_location")

    def test_unknown_action_is_invalid(self):
        plan = ["fly_away", "move_to_key"]
        r = self.env.execute(plan, self.task)
        self.assertEqual(r.invalid_actions[0]["reason"], "unknown_action")
        self.assertEqual(r.num_actions_attempted, 2)

    def test_enter_before_open_is_invalid(self):
        plan = ["enter_room"]
        r = self.env.execute(plan, self.task)
        self.assertFalse(r.entered_room)
        self.assertEqual(r.invalid_actions[0]["reason"], "door_not_open")

    def test_determinism(self):
        plan = ["move_to_key", "pick_up_key", "move_to_door", "open_door", "enter_room"]
        r1 = self.env.execute(plan, self.task).as_dict()
        r2 = LockedDoorEnvironment(seed=999).execute(plan, self.task).as_dict()
        self.assertEqual(r1, r2)

    def test_available_actions(self):
        self.assertEqual(
            AVAILABLE_ACTIONS,
            ["move_to_key", "pick_up_key", "move_to_door", "open_door", "enter_room"],
        )


if __name__ == "__main__":
    unittest.main()
