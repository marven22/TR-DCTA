import unittest

from mcx.publication_v2_posterior import (
    CascadeParameters, sample_importance_posterior, support_proposal,
)
from mcx.publication_v2_source import SourceEstimator


class SupportCorrectedPosteriorTests(unittest.TestCase):
    def test_proposal_preserves_support_without_changing_target(self):
        target = {"a": .99, "b": .009, "c": .001}
        proposal = support_proposal(target, .05)
        self.assertAlmostEqual(sum(proposal.values()), 1.0)
        self.assertEqual(target, {"a": .99, "b": .009, "c": .001})
        self.assertGreaterEqual(min(proposal.values()), .05)
        self.assertAlmostEqual(proposal["a"], .8915)

    def test_uniform_target_remains_uniform(self):
        target = {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}
        self.assertEqual(support_proposal(target, .05), target)

    def test_invalid_floor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid source-proposal floor"):
            support_proposal({"a": .5, "b": .5}, .5)

    def test_importance_sampler_recovers_target_source_marginal(self):
        archive = {
            "source_ids": ["s1", "s2", "s3"], "candidate_ids": ["m1"],
            "created_at": {"s1": 0, "s2": 1, "s3": 2, "m1": 3},
            "observed_formation_edges": [["s1", "m1"], ["s2", "m1"], ["s3", "m1"]],
            "latent_edge_candidates": [], "target_language": "target",
            "memories": {
                "s1": {"lesson": "one"}, "s2": {"lesson": "two"},
                "s3": {"lesson": "three"}, "m1": {"lesson": "child", "cited_memory_ids": []},
            },
        }
        contamination = SourceEstimator((0.0,) * 5, (1.0,) * 5, (-35.0,) + (0.0,) * 5)
        emission = SourceEstimator((0.0,) * 6, (1.0,) * 6, (0.0,) + (0.0,) * 6)
        parameters = CascadeParameters(contamination, emission, .5)
        target = {"s1": .99, "s2": .009, "s3": .001}
        posterior, diagnostics = sample_importance_posterior(
            archive, target, support_proposal(target, .05), parameters, 6000, 7,
        )
        recovered = posterior.source_probabilities()
        self.assertAlmostEqual(recovered["s1"], target["s1"], delta=.005)
        self.assertAlmostEqual(recovered["s2"], target["s2"], delta=.003)
        self.assertGreater(diagnostics.effective_sample_size, 5000)


if __name__ == "__main__":
    unittest.main()
