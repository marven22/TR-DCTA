import unittest

import _path  # noqa: F401

from mcx.memoryarena_v6 import (
    DiscoveryCase,
    ObservableMemory,
    adaptive_replay,
    build_task_matched_cases,
    discovery_metrics,
    extract_question_from_prompt,
    mask_observable_edges,
    mask_edges_with_forced_hidden_direct,
    recorded_descendants,
    static_ranking,
)


def fixture_case():
    return DiscoveryCase(
        case_id="fixture",
        source_id="m1",
        memories=(
            ObservableMemory("m1", "red rule unsafe", 0),
            ObservableMemory("d1", "independent astronomy", 1),
            ObservableMemory("m2", "red rule generalized", 2),
            ObservableMemory("d2", "independent cooking", 3),
            ObservableMemory("m4", "mixed lesson", 4, ("m2", "d2")),
        ),
        affected_ids=frozenset(("m2", "m4")),
    )


class TestMemoryArenaV6(unittest.TestCase):
    def test_recorded_descendants_does_not_invent_hidden_edge(self):
        case = fixture_case()
        self.assertEqual(recorded_descendants(case.memories, "m1"), set())
        self.assertEqual(static_ranking(case, "lineage"), [])
        self.assertEqual(static_ranking(case, "exposure"), [])

    def test_static_ranking_is_label_blind(self):
        original = fixture_case()
        relabeled = DiscoveryCase(
            original.case_id,
            original.source_id,
            original.memories,
            frozenset(("d1",)),
        )
        self.assertEqual(
            static_ranking(original, "hybrid"),
            static_ranking(relabeled, "hybrid"),
        )

    def test_adaptive_replay_expands_from_confirmed_parent(self):
        result = adaptive_replay(fixture_case(), budget=2)
        self.assertEqual(result["replayed_ids"], ["m2", "m4"])
        self.assertEqual(result["repaired_ids"], ["m2", "m4"])

    def test_exposure_is_observable_not_a_causal_label(self):
        case = DiscoveryCase(
            case_id="exposure",
            source_id="m1",
            memories=(
                ObservableMemory("m1", "source", 0),
                ObservableMemory("d1", "closer text", 1),
                ObservableMemory("m2", "unrelated wording", 2, (), "", ("m1",)),
                ObservableMemory("m3", "downstream", 3, ("m2",)),
            ),
            affected_ids=frozenset(("m2", "m3")),
        )
        result = adaptive_replay(case, budget=2, use_exposure=True)
        self.assertEqual(result["replayed_ids"], ["m2", "m3"])

    def test_validation_repairs_no_false_positives(self):
        case = fixture_case()
        result = adaptive_replay(case, budget=4)
        metrics = discovery_metrics(result["repaired_ids"], case.affected_ids)
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["collateral_rate"], 0.0)

    def test_case_rejects_duplicate_ids(self):
        case = DiscoveryCase(
            "bad", "m1",
            (ObservableMemory("m1", "a", 0), ObservableMemory("m1", "b", 1)),
            frozenset(),
        )
        with self.assertRaises(ValueError):
            case.validate()

    def test_mask_is_deterministic_and_reports_realized_missingness(self):
        case = DiscoveryCase(
            "mask", "m1",
            (
                ObservableMemory("m1", "source", 0),
                ObservableMemory("m2", "child", 1, (), "", ("m1",)),
                ObservableMemory("m3", "next", 2, ("m2",), "", ("m2",)),
                ObservableMemory("m4", "mixed", 3, ("m2",), "", ("m3",)),
            ),
            frozenset(("m2", "m3")),
        )
        masked, metadata = mask_observable_edges(case, 0.75, 0)
        masked_again, metadata_again = mask_observable_edges(case, 0.75, 0)
        self.assertEqual(metadata["total_edge_records"], 5)
        self.assertEqual(metadata, metadata_again)
        self.assertEqual(masked, masked_again)
        self.assertGreaterEqual(metadata["missing_fraction_realized"], 0.0)
        self.assertLessEqual(metadata["missing_fraction_realized"], 1.0)
        masked.validate()

    def test_question_extraction_excludes_answer_and_feedback(self):
        prompt = "prefix\nQUESTION:\nWho did this?\n\nYOUR ANSWER:\nsecret\n\nFEEDBACK:\nlabel"
        self.assertEqual(extract_question_from_prompt(prompt), "Who did this?")

    def test_hidden_direct_mask_always_removes_direct_edge(self):
        case = DiscoveryCase(
            "hidden", "m1",
            (
                ObservableMemory("m1", "source", 0, (), "", (), "task one"),
                ObservableMemory("m2", "child", 1, (), "", ("m1",), "task two"),
                ObservableMemory("m3", "next", 2, ("m2",), "", ("m2",), "task three"),
            ),
            frozenset(("m2", "m3")),
        )
        for seed in range(10):
            masked, metadata = mask_edges_with_forced_hidden_direct(case, 0.75, seed)
            m2 = next(memory for memory in masked.memories if memory.memory_id == "m2")
            self.assertNotIn("m1", m2.exposed_memory_ids)
            self.assertEqual(metadata["forced_hidden_edge"], ["m2", "exposure", "m1"])

    def test_trajectory_ranking_does_not_use_origin_or_labels(self):
        original = DiscoveryCase(
            "trajectory", "s",
            (
                ObservableMemory("s", "source", 0, (), "secret-a", (), "find an actor"),
                ObservableMemory("x", "other", 1, (), "secret-b", (), "find an actor"),
                ObservableMemory("y", "other", 2, (), "secret-c", (), "solve an equation"),
            ),
            frozenset(("x",)),
        )
        altered = DiscoveryCase(
            "trajectory", "s",
            tuple(
                ObservableMemory(
                    memory.memory_id, memory.content, memory.created_at,
                    memory.parent_memory_ids, "changed", memory.exposed_memory_ids,
                    memory.formation_context,
                )
                for memory in original.memories
            ),
            frozenset(("y",)),
        )
        self.assertEqual(
            static_ranking(original, "trajectory"),
            static_ranking(altered, "trajectory"),
        )


if __name__ == "__main__":
    unittest.main()
