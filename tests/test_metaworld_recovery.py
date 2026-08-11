from mcx.metaworld_recovery import (
    aggregate_recovery, first_survivor, forced_exposure_ranking,
    quarantined_ids, selected_success, task_variant_maps,
)


def record(policy, lesson):
    return {"parsed": {"recommended_policy_id": policy, "lesson": lesson,
                       "expected_outcome": lesson, "cited_memory_ids": []}}


def test_task_variant_maps_tracks_active_branch_and_shared_variant():
    generated = {
        "graph": {"branch_ids": [["a"], ["b"], ["c"]],
                  "candidate_ids": ["a", "b", "c", "z"]},
        "branches": [
            {"memories": [{"memory_id": "a", "factual": record("bad-a", "fa"),
                            "counterfactual": record("good", "ca")}]},
            {"memories": [{"memory_id": "b", "factual": record("bad-b", "fb"),
                            "counterfactual": record("good", "cb")}]},
            {"memories": [{"memory_id": "c", "factual": record("bad-c", "fc"),
                            "counterfactual": record("good", "cc")}]},
        ],
        "shared_memories": [{"memory_id": "z", "variants": {
            "active_0": record("bad-a", "za"),
            "active_1": record("bad-b", "zb"),
            "active_2": record("bad-c", "zc"),
            "clean": record("good", "clean-z"),
        }}],
    }
    corrupt, clean, corrupt_policy, clean_policy = task_variant_maps(generated, 1)
    assert corrupt_policy == {"a": "good", "b": "bad-b", "c": "good", "z": "bad-b"}
    assert set(clean_policy.values()) == {"good"}
    assert corrupt["b"]["lesson"] == "fb"
    assert clean["b"]["lesson"] == "cb"
    assert corrupt["z"]["lesson"] == "zb"


def test_quarantine_and_behavioral_metrics():
    assert quarantined_ids(["a", "b", "c"], ["b", "d"]) == ("b",)
    assert selected_success("a", {"a": "native"}, {"native": True})
    assert aggregate_recovery(.2, .6, 1.0) == .49999999999999994
    assert aggregate_recovery(1.0, 1.0, 1.0) is None


def test_forced_exposure_uses_shared_anchor_and_semantic_fallback():
    ranking = forced_exposure_ranking(
        "bad", ["good-old", "bad", "good-new"],
        {"good-old": .7, "bad": .1, "good-new": .7},
        {"good-old": 1, "bad": 2, "good-new": 3},
    )
    assert ranking == ("bad", "good-old", "good-new")
    assert first_survivor(ranking, []) == "bad"
    assert first_survivor(ranking, ["bad"]) == "good-old"
