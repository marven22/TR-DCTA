import json
from pathlib import Path

import pytest

from mcx.metaworld_scalability import extend_harm_weights, scale_archive


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not (ROOT / "results/prob_dcta_metaworld_development_public_mask_consistent.json").is_file(),
    reason="requires the external MetaWorld ledger bundle",
)


def fixture():
    public = json.loads((ROOT / "results/prob_dcta_metaworld_development_public_mask_consistent.json").read_text(encoding="utf-8"))
    private = json.loads((ROOT / "results/prob_dcta_metaworld_development_private_mask_consistent.json").read_text(encoding="utf-8"))
    observable = json.loads((ROOT / "results/metaworld_recovery_development_observable.json").read_text(encoding="utf-8"))
    recovery_private = json.loads((ROOT / "results/metaworld_recovery_development_private.json").read_text(encoding="utf-8"))
    archive = next(row for row in public["archives"] if float(row["provenance_missing_rate"]) == .25)
    truth = next(row for row in private["archives"] if row["archive_id"] == archive["archive_id"])
    obs = next(row for row in observable["archives"] if row["archive_id"] == archive["archive_id"])
    rec = next(row for row in recovery_private["archives"] if row["archive_id"] == archive["archive_id"])
    return archive, truth, obs, rec


def test_scaling_is_nested_and_preserves_original_archive():
    archive, truth, obs, rec = fixture()
    small = scale_archive(
        archive, truth, obs["clean_memories"], rec["clean_policy_by_memory"],
        rec["corrupted_policy_by_memory"], rec["success_by_policy"], 50,
    )
    large = scale_archive(
        archive, truth, obs["clean_memories"], rec["clean_policy_by_memory"],
        rec["corrupted_policy_by_memory"], rec["success_by_policy"], 100,
    )
    assert len(small.archive["candidate_ids"]) == 50
    assert len(large.archive["candidate_ids"]) == 100
    assert large.archive["candidate_ids"][:50] == small.archive["candidate_ids"]
    for node in archive["candidate_ids"]:
        assert small.archive["memories"][node] == archive["memories"][node]
    assert small.affected_ids == frozenset(truth["affected_ids"])
    assert not (set(small.distractor_ids) & small.affected_ids)


def test_every_added_distractor_is_verified_target_successful_and_causally_plausible():
    archive, truth, obs, rec = fixture()
    scaled = scale_archive(
        archive, truth, obs["clean_memories"], rec["clean_policy_by_memory"],
        rec["corrupted_policy_by_memory"], rec["success_by_policy"], 200,
    )
    assert all(scaled.success_by_policy[scaled.policy_by_memory[node]]
               for node in scaled.distractor_ids)
    assert len(scaled.distractor_true_edges) == 179
    assert set(scaled.distractor_true_edges) == (
        set(scaled.distractor_observed_edges) | set(scaled.distractor_latent_edges)
    )


def test_harm_weights_for_original_candidates_do_not_change_with_scale():
    archive, truth, obs, rec = fixture()
    small = scale_archive(
        archive, truth, obs["clean_memories"], rec["clean_policy_by_memory"],
        rec["corrupted_policy_by_memory"], rec["success_by_policy"], 50,
    )
    large = scale_archive(
        archive, truth, obs["clean_memories"], rec["clean_policy_by_memory"],
        rec["corrupted_policy_by_memory"], rec["success_by_policy"], 200,
    )
    small_weights = extend_harm_weights(archive, small)
    large_weights = extend_harm_weights(archive, large)
    assert all(small_weights[node] == large_weights[node]
               for node in archive["candidate_ids"])
