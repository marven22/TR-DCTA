"""Unit tests for the model-backed DDXPlus memory writer."""

import json
import unittest

import _path  # noqa: F401

from mcx.ddxplus_qwen_writer import (
    GenerationRejected, build_prompt, forbidden_terms, generate_texts,
    ordered_slots, parse_response, redact,
)
from mcx.ddxplus_writer import assemble_record, build_generation_record, plan_record
from mcx.publication_v2_archive import materialize_task
from test_ddxplus_writer import TASK


def stub(reply):
    def generate(prompt):
        return reply(prompt) if callable(reply) else reply
    return generate


def echo_generate(prompt):
    """Return valid JSON that echoes the procedure the plan asked for."""
    section = prompt.split("PROCEDURE THIS ENTRY RECOMMENDS", 1)[1]
    language = section.split("\n", 2)[1].strip()
    return json.dumps({"lesson": f"Use the {language} here.",
                       "expected_outcome": "It should reach a conclusion."})


class ParseTest(unittest.TestCase):
    def test_accepts_plain_and_fenced_json(self):
        payload = '{"lesson": "a", "expected_outcome": "b"}'
        self.assertEqual(parse_response(payload, ()), ("a", "b"))
        self.assertEqual(parse_response(f"```json\n{payload}\n```", ()), ("a", "b"))

    def test_rejects_wrong_shape_or_empty_fields(self):
        for bad in ('not json', '{"lesson": "a"}', '{"lesson": "", "expected_outcome": "b"}',
                    '{"lesson": "a", "expected_outcome": "b", "extra": 1}'):
            with self.assertRaises(GenerationRejected):
                parse_response(bad, ())

    def test_rejects_text_naming_a_condition(self):
        payload = '{"lesson": "This is Pneumonia.", "expected_outcome": "b"}'
        with self.assertRaises(GenerationRejected):
            parse_response(payload, ("Pneumonia",))

    def test_rejects_overlong_text(self):
        payload = json.dumps({"lesson": "x" * 500, "expected_outcome": "b"})
        with self.assertRaises(GenerationRejected):
            parse_response(payload, ())

    def test_redaction_removes_condition_names(self):
        self.assertEqual(redact("suspect Pneumonia now", ("Pneumonia",)),
                         "suspect the condition now")


class PromptTest(unittest.TestCase):
    def setUp(self):
        self.plan = plan_record(TASK)

    def test_prompt_frame_is_identical_for_harmful_and_safe_memories(self):
        donors = {donor["policy"] for donor in TASK["donors"]}
        harmful = next(s for s in self.plan["slots"]
                       if s["policy"] in donors and not s["copy_of"])
        safe = next(s for s in self.plan["slots"]
                    if s["policy"] == TASK["native_policy"] and not s["copy_of"])
        first = build_prompt(self.plan, harmful, None)
        second = build_prompt(self.plan, safe, None)
        # The only permitted difference is the named procedure.
        self.assertNotEqual(first, second)
        self.assertEqual(first.replace(str(harmful["language"]), "X"),
                         second.replace(str(safe["language"]), "X"))

    def test_forbidden_terms_cover_the_pathology_and_its_donors(self):
        terms = set(forbidden_terms(TASK))
        self.assertIn("Pneumonia", terms)
        self.assertIn("Bronchitis", terms)

    def test_slots_are_ordered_so_parents_are_written_first(self):
        created = self.plan["graph"]["created_at"]
        times = [created[str(slot["memory_id"])] for slot in ordered_slots(self.plan)]
        self.assertEqual(times, sorted(times))


class GenerationTest(unittest.TestCase):
    def setUp(self):
        self.plan = plan_record(TASK)

    def test_generated_archive_materializes_like_the_template_archive(self):
        texts, incidents, _ = generate_texts(
            self.plan, echo_generate, forbidden=forbidden_terms(TASK))
        self.assertEqual(incidents, [])
        record = assemble_record(self.plan, texts, "ddxplus-qwen-v1")
        public, private = materialize_task(record)
        template_public, template_private = materialize_task(
            build_generation_record(TASK))
        # Identical structure and labels; only the prose differs.
        self.assertEqual([row["archive_id"] for row in public],
                         [row["archive_id"] for row in template_public])
        self.assertEqual([row["affected_ids"] for row in private],
                         [row["affected_ids"] for row in template_private])
        self.assertNotEqual([row["memories"] for row in public],
                            [row["memories"] for row in template_public])

    def test_a_rejected_response_is_retried(self):
        calls = []

        def flaky(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                return "not json at all"
            return echo_generate(prompt)

        texts, incidents, _ = generate_texts(
            self.plan, flaky, forbidden=forbidden_terms(TASK), attempts=2)
        self.assertTrue(texts)
        self.assertEqual(len(incidents), 1)
        self.assertIn("not JSON", incidents[0]["reason"])

    def test_cache_is_reused_only_when_the_prompt_is_unchanged(self):
        cache = {}
        _, _, reused = generate_texts(self.plan, echo_generate,
                                      forbidden=forbidden_terms(TASK), cache=cache)
        self.assertEqual(reused, 0)
        self.assertTrue(cache)
        _, _, reused = generate_texts(self.plan, echo_generate,
                                      forbidden=forbidden_terms(TASK), cache=cache)
        self.assertEqual(reused, len(cache))
        # A stale entry whose prompt has changed must not be reused.
        key = next(iter(cache))
        cache[key] = {**cache[key], "prompt_sha256": "0" * 16}
        _, _, reused = generate_texts(self.plan, echo_generate,
                                      forbidden=forbidden_terms(TASK), cache=cache)
        self.assertEqual(reused, len(cache) - 1)

    def test_unusable_responses_raise_rather_than_corrupt_the_archive(self):
        with self.assertRaises(GenerationRejected):
            generate_texts(self.plan, stub("still not json"),
                           forbidden=forbidden_terms(TASK), attempts=2)

    def test_parent_wording_is_offered_to_descendants(self):
        seen = []

        def recording(prompt):
            seen.append(prompt)
            return echo_generate(prompt)

        generate_texts(self.plan, recording, forbidden=forbidden_terms(TASK))
        with_parent = [p for p in seen if "(this is the earliest entry" not in p]
        self.assertTrue(with_parent)
        self.assertIn("Use the", with_parent[-1])


if __name__ == "__main__":
    unittest.main()
