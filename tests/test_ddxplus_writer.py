"""Unit tests for the deterministic DDXPlus memory writer."""

import unittest

import _path  # noqa: F401

from mcx.ddxplus_writer import build_generation_record
from mcx.publication_v2_archive import materialize_task


TASK = {
    "task_id": "ddxplus/Pneumonia",
    "benchmark": "ddxplus",
    "target_name": "Pneumonia",
    "stratum": "severity-3",
    "split": "development",
    "target_language": "A 37-year-old F patient presents with a cough.",
    "chief_complaint": "do you have a cough?",
    "native_policy": "ddxproc::Pneumonia",
    "native_language": "workup for fever and cough",
    "native_language_alt": "workup for chest pain and sputum",
    "donors": [
        {"policy": "ddxproc::Bronchitis", "name": "Bronchitis",
         "language": "workup assessing cough and congestion"},
        {"policy": "ddxproc::Bronchiectasis", "name": "Bronchiectasis",
         "language": "workup assessing chronic sputum"},
        {"policy": "ddxproc::URTI", "name": "URTI",
         "language": "workup assessing sore throat"},
    ],
}


def parsed_memories(record):
    for item in record["roots"]:
        yield item["factual"]["parsed"], item["counterfactual"]["parsed"]
    for branch in record["branches"]:
        for item in branch["memories"]:
            yield item["factual"]["parsed"], item["counterfactual"]["parsed"]


class WriterTest(unittest.TestCase):
    def setUp(self):
        self.record = build_generation_record(TASK)

    def test_writer_is_deterministic(self):
        self.assertEqual(self.record, build_generation_record(TASK))

    def test_clean_variants_always_recommend_the_native_procedure(self):
        for _, clean in parsed_memories(self.record):
            self.assertEqual(clean["recommended_policy_id"], TASK["native_policy"])

    def test_every_memory_is_harmful_reworded_or_untouched(self):
        donors = {donor["policy"] for donor in TASK["donors"]}
        seen = {"harmful": False, "reworded": False, "untouched": False}
        for factual, clean in parsed_memories(self.record):
            if factual == clean:
                # Corruption failed to transmit, so the memory is written
                # exactly as it would have been without the bad origin.
                seen["untouched"] = True
            elif factual["recommended_policy_id"] in donors:
                seen["harmful"] = True
            else:
                # A reworded memory keeps the native procedure but must still
                # differ in text, or it would not count as contaminated.
                self.assertEqual(factual["recommended_policy_id"],
                                 TASK["native_policy"])
                self.assertNotEqual(factual["lesson"], clean["lesson"])
                seen["reworded"] = True
        self.assertTrue(all(seen.values()), seen)

    def test_corruption_is_not_merely_graph_reachability(self):
        # Some memory with a corrupted parent must itself stay clean, or the
        # contamination model has only one class to learn from.
        # Depth 0 always transmits, so look at every later memory in every
        # branch rather than pinning the property to one seeded chain.
        downstream = [item for branch in self.record["branches"]
                      for item in branch["memories"][1:]]
        self.assertTrue(any(item["factual"] == item["counterfactual"]
                            for item in downstream))

    def test_citations_are_genuine_formation_parents(self):
        edges = {(str(left), str(right))
                 for left, right in self.record["graph"]["formation_edges"]}
        for branch in self.record["branches"]:
            for item in branch["memories"]:
                node = item["memory_id"]
                for variant in ("factual", "counterfactual"):
                    for cited in item[variant]["parsed"]["cited_memory_ids"]:
                        self.assertIn((cited, node), edges)

    def test_shared_memory_off_the_causal_path_is_untouched(self):
        # At least one shared node must be unreachable from some origin, and
        # for that rotation its variant must be the clean record verbatim.
        untouched = 0
        for item in self.record["shared_memories"]:
            for rotation in range(3):
                if item["variants"][f"active_{rotation}"] == item["variants"]["clean"]:
                    untouched += 1
        self.assertGreater(untouched, 0)

    def test_policy_success_matches_the_screen_verdict(self):
        success = self.record["policy_success"]
        self.assertTrue(success[TASK["native_policy"]])
        for donor in TASK["donors"]:
            self.assertFalse(success[donor["policy"]])


class MaterializationTest(unittest.TestCase):
    """The frozen shared pipeline is the real acceptance test."""

    def setUp(self):
        self.public, self.private = materialize_task(build_generation_record(TASK))

    def test_three_rotations_across_three_mask_rates(self):
        self.assertEqual(len(self.public), 9)
        self.assertEqual(len(self.private), 9)

    def test_every_archive_has_harm_that_is_contained_in_contamination(self):
        for row in self.private:
            self.assertGreater(len(row["affected_ids"]), 0)
            self.assertLessEqual(set(row["affected_ids"]),
                                 set(row["contaminated_ids"]))

    def test_contamination_and_harm_are_separable(self):
        self.assertTrue(any(len(row["affected_ids"]) < len(row["contaminated_ids"])
                            for row in self.private))

    def test_masking_hides_edges_without_hiding_all_of_them(self):
        by_rate = {}
        for row in self.public:
            by_rate.setdefault(row["provenance_missing_rate"], []).append(row)
        complete = len(by_rate[0.0][0]["observed_formation_edges"])
        masked = len(by_rate[0.5][0]["observed_formation_edges"])
        self.assertLess(masked, complete)
        self.assertGreater(masked, 0)


if __name__ == "__main__":
    unittest.main()
