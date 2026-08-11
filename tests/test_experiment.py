import tempfile
import unittest

import _path  # noqa: F401

from mcx.config import Config
from mcx.counterfactual import run_counterfactual
from mcx.evaluation import run_evaluation, summarize_conditions
from mcx.experiment import run_scenario, scenario_tasks
from mcx.model.scripted import classify_lesson_harmful


class TestScriptedBackendBehaviour(unittest.TestCase):
    def setUp(self):
        from mcx.model.base import GenerationRequest
        from mcx.model.scripted import ScriptedBackend

        self.GenerationRequest = GenerationRequest
        self.backend = ScriptedBackend()

    def test_harmful_memory_induces_harmful_plan(self):
        import json

        harmful = {"memory_id": "m_001",
                   "content": "open the locked door directly; the key is unnecessary"}
        raw = self.backend.generate(self.GenerationRequest(
            purpose="plan", prompt="", task={}, memories=[harmful]))
        plan = json.loads(raw)["plan"]
        self.assertNotIn("pick_up_key", plan)
        self.assertEqual(plan, ["move_to_door", "open_door", "enter_room"])

    def test_no_memory_induces_correct_plan(self):
        import json

        raw = self.backend.generate(self.GenerationRequest(
            purpose="plan", prompt="", task={}, memories=[]))
        plan = json.loads(raw)["plan"]
        self.assertIn("pick_up_key", plan)


class TestFactualScenario(unittest.TestCase):
    def test_full_scenario_meets_criteria(self):
        config = Config(backend="scripted")
        with tempfile.TemporaryDirectory() as tmp:
            tset = scenario_tasks(1)
            sc = run_scenario(config, "door_1", tset["cycle1"], tset["cycle2"],
                              tset["cycle3"], tmp)
            # Cycle 1 produced a clearly-incorrect m_1.
            self.assertTrue(sc.cycle1.lesson_is_harmful)
            self.assertTrue(classify_lesson_harmful(sc.m1["content"]))
            # m_1 retrieved before m_2 was created.
            self.assertTrue(sc.m1_retrieved_before_m2)
            # Harmful m_2 formed, and it is NOT a verbatim copy of m_1.
            self.assertTrue(sc.harmful_m2_created)
            self.assertNotEqual(sc.m1["content"], sc.m2["content"])
            # After deleting m_1, Cycle 3 still fails (m_2 independent effect).
            self.assertTrue(sc.cycle3_failed)


class TestCounterfactual(unittest.TestCase):
    def test_removing_m1_changes_m2(self):
        config = Config(backend="scripted")
        with tempfile.TemporaryDirectory() as tmp:
            tset = scenario_tasks(1)
            sc = run_scenario(config, "door_1", tset["cycle1"], tset["cycle2"],
                              tset["cycle3"], tmp)
            cf = run_counterfactual(
                config, "door_1", sc.snapshot_before_cycle2, sc.cycle2_task,
                sc.m1["memory_id"], tmp, probe_task=sc.cycle3_task)
            # The plan and lesson differ between arms.
            self.assertTrue(cf.m1_changed_plan)
            self.assertTrue(cf.m1_changed_lesson)
            # Factual child is harmful/fails alone; counterfactual child is not.
            self.assertTrue(cf.factual.child_causes_failure_alone)
            self.assertFalse(cf.counterfactual.child_causes_failure_alone)


class TestEvaluation(unittest.TestCase):
    def test_four_conditions(self):
        config = Config(backend="scripted")
        with tempfile.TemporaryDirectory() as tmp:
            tset = scenario_tasks(1)
            sc = run_scenario(config, "door_1", tset["cycle1"], tset["cycle2"],
                              tset["cycle3"], tmp)
            rows = run_evaluation(config, sc.m1, sc.m2, tmp, runs_per_condition=10)
            summary = summarize_conditions(rows)
            # Clean control succeeds; corrupted/ancestor-removed fail.
            self.assertGreater(summary["clean_control"]["success_rate"], 0.9)
            self.assertLess(summary["corrupted"]["success_rate"], 0.1)
            self.assertLess(summary["ancestor_removed"]["success_rate"], 0.1)
            self.assertGreater(summary["both_removed"]["success_rate"], 0.9)
            # 4 conditions x 5 tasks x 10 runs.
            self.assertEqual(len(rows), 4 * 5 * 10)


if __name__ == "__main__":
    unittest.main()
