"""Frozen V3 retrieval-stress test over the exact V2 memory artifact."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple

from .memoryarena_pilot import (
    DATASET_ID,
    DATASET_SPLIT,
    EntityPilotRunner,
    _normalize_entity,
    _reference_entity,
    _safe_response_entity,
)
from .memoryarena_v2 import (
    CHAIN_A_INDEX,
    CHAIN_B_INDEX,
    DATASET_CONFIG,
    _content_hash,
    _session,
    token_jaccard,
)
from .model.base import ModelBackend


V2_PROTOCOL = "memoryarena-causal-repair/v2-frozen"
EXPECTED_CHAIN_HASHES = {
    "chain_a": "5a3bc537ef74f417f135c1895e34625da91f30b3d3d8d271301c303c8720b0e5",
    "chain_b": "fae820579d223d5e6679f91885d29a596424a07784bcb4c26470298661a76ba0",
}
POLICIES = (
    "all_visible",
    "semantic_top1",
    "semantic_top2",
    "recency_top1",
    "source_expired_all",
    "consolidation_only",
)


def load_and_validate_v2(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        result = json.load(handle)
    if result.get("protocol_version") != V2_PROTOCOL:
        raise ValueError("input is not the frozen V2 result")
    dataset = result.get("dataset", {})
    if (
        dataset.get("id") != DATASET_ID
        or dataset.get("config") != DATASET_CONFIG
        or dataset.get("split") != DATASET_SPLIT
    ):
        raise ValueError("V2 dataset identity does not match V3 protocol")
    for chain_name, expected_hash in EXPECTED_CHAIN_HASHES.items():
        if dataset.get(chain_name, {}).get("sha256") != expected_hash:
            raise ValueError(f"V2 {chain_name} hash does not match frozen input")
    memories = result.get("memories", {})
    for branch in ("corrupted", "corrected"):
        if set(memories.get(branch, {})) != {"m1", "m2", "m3", "m4"}:
            raise ValueError(f"V2 {branch} branch has unexpected memory IDs")
    construction = result.get("construction", {})
    if construction.get("m2_parent_ids_clean") != [] or construction.get(
        "m2_parent_ids_corrupted"
    ) != []:
        raise ValueError("V2 artifact does not contain the frozen hidden dependency")
    if set(construction.get("m4_parent_ids_clean", [])) != {"m2", "m3"}:
        raise ValueError("V2 corrected m4 has unexpected parents")
    if set(construction.get("m4_parent_ids_corrupted", [])) != {"m2", "m3"}:
        raise ValueError("V2 corrupted m4 has unexpected parents")
    if result.get("discovery", {}).get("paired_intervention", {}).get(
        "predicted_ids"
    ) != ["m2", "m4"]:
        raise ValueError("V2 paired intervention set differs from frozen input")
    return result


def build_v3_archives(v2: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    bad, clean = v2["memories"]["corrupted"], v2["memories"]["corrected"]
    return {
        "source_corrected_only": [clean["m1"], bad["m2"], clean["m3"], bad["m4"]],
        "semantic_deletion": [clean["m1"], clean["m3"], bad["m4"]],
        "full_repair": [clean["m1"], clean["m2"], clean["m3"], clean["m4"]],
    }


def retrieve(
    archive: Sequence[Dict[str, Any]], query: str, policy: str
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    if policy not in POLICIES:
        raise ValueError(f"unknown retrieval policy: {policy}")
    scores = {m["memory_id"]: token_jaccard(query, m["content"]) for m in archive}
    if policy == "all_visible":
        selected = list(archive)
    elif policy.startswith("semantic_top"):
        k = int(policy.removeprefix("semantic_top"))
        indexed = list(enumerate(archive))
        ranked = sorted(
            indexed,
            key=lambda pair: (scores[pair[1]["memory_id"]], pair[0]),
            reverse=True,
        )
        selected = [memory for _, memory in ranked[:k]]
    elif policy == "recency_top1":
        selected = list(reversed(archive[-1:]))
    elif policy == "source_expired_all":
        selected = [m for m in archive if m["memory_id"] != "m1"]
    else:
        selected = [m for m in archive if m["memory_id"] == "m4"]
    return selected, scores


def _archive_fingerprint(archive: Sequence[Dict[str, Any]]) -> str:
    return json.dumps(archive, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def run_memoryarena_v3(backend: ModelBackend, v2: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate stale-memory re-emergence under frozen retrieval policies."""
    from datasets import load_dataset

    dataset = load_dataset(DATASET_ID, DATASET_CONFIG, split=DATASET_SPLIT)
    chain_a, chain_b = dict(dataset[CHAIN_A_INDEX]), dict(dataset[CHAIN_B_INDEX])
    if _content_hash(chain_a) != EXPECTED_CHAIN_HASHES["chain_a"]:
        raise ValueError("live chain A differs from the frozen dataset artifact")
    if _content_hash(chain_b) != EXPECTED_CHAIN_HASHES["chain_b"]:
        raise ValueError("live chain B differs from the frozen dataset artifact")
    expected = {
        "a": _reference_entity(chain_a["answers"][0]),
        "b": _reference_entity(chain_b["answers"][0]),
    }
    sessions = {
        "a": _session(chain_a, len(chain_a["questions"]) - 1, "a"),
        "b": _session(chain_b, len(chain_b["questions"]) - 1, "b"),
    }
    archives = build_v3_archives(v2)
    runner = EntityPilotRunner(backend)
    cells: Dict[str, Dict[str, Any]] = {}
    for condition, archive in archives.items():
        cells[condition] = {}
        for policy in POLICIES:
            cells[condition][policy] = {}
            for target in ("a", "b"):
                selected, scores = retrieve(archive, sessions[target]["question"], policy)
                answer = runner.answer(
                    f"v3_{condition}_{policy}_{target}", sessions[target], selected
                )
                entity = _safe_response_entity(answer)
                cells[condition][policy][target] = {
                    "correct": _normalize_entity(entity)
                    == _normalize_entity(expected[target]),
                    "entity": entity,
                    "selected_memory_ids": [m["memory_id"] for m in selected],
                    "similarity_scores": scores,
                    "answer": answer,
                }

    robustness = {}
    for condition in archives:
        robustness[condition] = {}
        for target in ("a", "b"):
            correct_count = sum(
                cells[condition][policy][target]["correct"] for policy in POLICIES
            )
            robustness[condition][target] = {
                "correct_policies": correct_count,
                "total_policies": len(POLICIES),
                "accuracy": correct_count / len(POLICIES),
            }

    clean = v2["memories"]["corrected"]
    bad = v2["memories"]["corrupted"]
    selective_archive = [clean["m1"], clean["m2"], bad["m3"], clean["m4"]]
    full_archive = archives["full_repair"]
    selective_matches_full_bytes = (
        _archive_fingerprint(selective_archive) == _archive_fingerprint(full_archive)
    )
    v2_conditions = v2["conditions"]
    selective_cost = v2_conditions["selective_causal_replay"]["replayed_later_records"]
    full_cost = v2_conditions["full_corrected_replay"]["replayed_later_records"]
    stress_policies = [p for p in POLICIES if p != "all_visible"]
    criteria = {
        "v2_masking_replicated": cells["source_corrected_only"]["all_visible"]["a"]["correct"],
        "stale_corruption_reemerges": any(
            not cells["source_corrected_only"][policy]["a"]["correct"]
            for policy in stress_policies
        ),
        "full_repair_correct_on_all_a_policies": all(
            cells["full_repair"][policy]["a"]["correct"] for policy in POLICIES
        ),
        "full_repair_correct_on_all_b_policies": all(
            cells["full_repair"][policy]["b"]["correct"] for policy in POLICIES
        ),
        "full_repair_more_robust_than_source_correction": (
            robustness["full_repair"]["a"]["accuracy"]
            > robustness["source_corrected_only"]["a"]["accuracy"]
        ),
        "selective_archive_matches_full_repair_bytes": selective_matches_full_bytes,
        "selective_replay_cost_is_lower": selective_cost < full_cost,
    }
    criteria["reemergence_mechanism_demonstrated"] = all(criteria.values())
    return {
        "protocol_version": "memoryarena-retrieval-stress/v3-frozen",
        "source_v2": {
            "protocol_version": v2["protocol_version"],
            "created_at_utc": v2.get("run", {}).get("created_at_utc"),
            "dataset": v2["dataset"],
        },
        "retrieval_policies": list(POLICIES),
        "condition_aliases": {
            "recorded_lineage": "source_corrected_only",
            "selective_causal_replay": "full_repair",
            "full_corrected_replay": "full_repair",
        },
        "replay_costs": {"selective_causal_replay": selective_cost, "full_corrected_replay": full_cost},
        "expected_entities": expected,
        "cells": cells,
        "robustness": robustness,
        "criteria": criteria,
        "calls": [call.as_dict() for call in runner.calls],
    }
