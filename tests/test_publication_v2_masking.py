import unittest

from mcx.publication_v2_masking import assert_mask_consistent, mask_hidden_citations


class PublicationV2MaskingTests(unittest.TestCase):
    def test_hidden_edge_citation_is_removed(self):
        archive = {
            "observed_formation_edges": [["a", "c"]],
            "memories": {
                "c": {"lesson": "x", "cited_memory_ids": ["a", "b"]},
            },
        }
        masked, count = mask_hidden_citations(archive)
        self.assertEqual(masked["memories"]["c"]["cited_memory_ids"], ["a"])
        self.assertEqual(count, 1)
        self.assertEqual(archive["memories"]["c"]["cited_memory_ids"], ["a", "b"])
        assert_mask_consistent(masked)

    def test_inconsistent_archive_is_rejected(self):
        archive = {
            "observed_formation_edges": [],
            "memories": {"c": {"cited_memory_ids": ["a"]}},
        }
        with self.assertRaisesRegex(ValueError, "citation reveals hidden edge"):
            assert_mask_consistent(archive)


if __name__ == "__main__":
    unittest.main()

