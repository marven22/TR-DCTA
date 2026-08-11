import json
import unittest

import _path  # noqa: F401

from mcx.validation import validate_lesson, validate_plan


class TestPlanValidation(unittest.TestCase):
    def test_valid_plan(self):
        raw = json.dumps({"plan": ["move_to_key", "pick_up_key"], "memory_ids_used": ["m_001"]})
        r = validate_plan(raw, ["m_001"])
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.value["plan"], ["move_to_key", "pick_up_key"])

    def test_invalid_json(self):
        r = validate_plan("not json at all", [])
        self.assertFalse(r.ok)

    def test_json_in_code_fence(self):
        raw = "```json\n" + json.dumps({"plan": ["open_door"], "memory_ids_used": []}) + "\n```"
        r = validate_plan(raw, [])
        self.assertTrue(r.ok, r.errors)

    def test_disallowed_action(self):
        raw = json.dumps({"plan": ["teleport"], "memory_ids_used": []})
        r = validate_plan(raw, [])
        self.assertFalse(r.ok)
        self.assertTrue(any("disallowed" in e for e in r.errors))

    def test_unknown_memory_id(self):
        raw = json.dumps({"plan": ["open_door"], "memory_ids_used": ["m_999"]})
        r = validate_plan(raw, ["m_001"])
        self.assertFalse(r.ok)
        self.assertTrue(any("unknown ids" in e for e in r.errors))

    def test_unexpected_field(self):
        raw = json.dumps({"plan": ["open_door"], "memory_ids_used": [], "extra": 1})
        r = validate_plan(raw, [])
        self.assertFalse(r.ok)
        self.assertTrue(any("unexpected fields" in e for e in r.errors))

    def test_missing_field(self):
        raw = json.dumps({"plan": ["open_door"]})
        r = validate_plan(raw, [])
        self.assertFalse(r.ok)


class TestLessonValidation(unittest.TestCase):
    def test_valid_lesson(self):
        raw = json.dumps({"lesson": "always collect the key", "parent_memory_ids": ["m_001"]})
        r = validate_lesson(raw, ["m_001"])
        self.assertTrue(r.ok, r.errors)

    def test_empty_lesson_rejected(self):
        raw = json.dumps({"lesson": "   ", "parent_memory_ids": []})
        r = validate_lesson(raw, [])
        self.assertFalse(r.ok)

    def test_unknown_parent_is_tolerated(self):
        # A lesson's declared parent ids are a self-reported lineage claim, not
        # a hard constraint (the experiment records the TRUE retrieved parents
        # separately). An unknown declared id must NOT invalidate the lesson;
        # it is surfaced as a non-fatal note.
        raw = json.dumps({"lesson": "x", "parent_memory_ids": ["m_404"]})
        r = validate_lesson(raw, ["m_001"])
        self.assertTrue(r.ok)
        self.assertEqual(r.value["parent_memory_ids"], ["m_404"])
        self.assertTrue(r.errors)  # non-fatal note recorded

    def test_empty_parents_ok(self):
        raw = json.dumps({"lesson": "always collect the key", "parent_memory_ids": []})
        r = validate_lesson(raw, [])
        self.assertTrue(r.ok, r.errors)


if __name__ == "__main__":
    unittest.main()
