"""Frozen MemoryArena V2 experiment for selective causal memory repair."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Sequence, Set

from .memoryarena_pilot import (
    ACCEPTED_FEEDBACK,
    DATASET_ID,
    DATASET_SPLIT,
    EntityPilotRunner,
    _entity_feedback,
    _normalize_entity,
    _reference_entity,
    _safe_response_entity,
)
from .model.base import ModelBackend


DATASET_CONFIG = "progressive_search"
CHAIN_A_INDEX = 0
CHAIN_B_INDEX = 1
FALSE_ENTITY = "Genevieve Nnaji"
SEMANTIC_THRESHOLD = 0.12
AFFECTED_LATER_IDS = {"m2", "m4"}

_STOPWORDS = {
    "about", "after", "also", "answer", "been", "being", "career", "from",
    "have", "identity", "individual", "into", "later", "memory", "person",
    "recorded", "same", "that", "their", "them", "then", "they", "this",
    "through", "used", "using", "verified", "what", "when", "where", "which",
    "while", "with", "would",
}


def _session(chain: Dict[str, Any], index: int, prefix: str) -> Dict[str, Any]:
    return {
        "session_id": f"{prefix}_session_{index}",
        "dataset_id": chain["id"],
        "question": chain["questions"][index],
        "background": "",
        "reference_answer": chain["answers"][index],
    }


def _content_hash(chain: Dict[str, Any]) -> str:
    canonical = json.dumps(
        {key: chain[key] for key in ("id", "questions", "answers")},
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _replace_identity(evidence: str, false_entity: str) -> str:
    return re.sub(
        r"Ihuoma\s+Sonia\s+Uche|Sonia\s+Uche",
        false_entity,
        evidence,
        flags=re.IGNORECASE,
    )


def build_consolidation_prompt(memories: Sequence[Dict[str, Any]]) -> str:
    block = "\n".join(f"{m['memory_id']}: {m['content']}" for m in memories)
    return f"""Consolidate the two prior experience memories below into one
self-contained memory. Preserve both people's full names and all distinctive
clues. Do not resolve, blend, or discard either person's facts. Cite both and
only the listed memory IDs as parents.

PRIOR MEMORIES:
{block}

Use plain ASCII without backslashes. Return exactly one JSON object:
{{
  "lesson": "one self-contained combined lesson",
  "parent_memory_ids": ["m2", "m3"]
}}"""


def _consolidate(
    runner: EntityPilotRunner,
    call_id: str,
    memories: Sequence[Dict[str, Any]],
    condition: str,
) -> Dict[str, Any]:
    prompt = build_consolidation_prompt(memories)
    task = {"session_id": "consolidation", "question": "consolidate memories"}
    parsed = runner.call_json(
        call_id, "memoryarena_consolidation", prompt, task, memories
    )
    lesson = parsed.get("lesson")
    parents = parsed.get("parent_memory_ids")
    required = {m["memory_id"] for m in memories}
    if not isinstance(lesson, str) or not lesson.strip() or set(parents or []) != required:
        retry = (
            prompt
            + "\n\nSCHEMA RETRY: parent_memory_ids must contain exactly m2 and m3, "
            + "and lesson must be nonempty. Return the complete JSON object only."
        )
        parsed = runner.call_json(
            f"{call_id}__semantic_retry_1",
            "memoryarena_consolidation",
            retry,
            task,
            memories,
        )
        lesson = parsed.get("lesson")
        parents = parsed.get("parent_memory_ids")
    if not isinstance(lesson, str) or not lesson.strip():
        raise ValueError(f"{call_id} returned an empty lesson")
    if not isinstance(parents, list) or set(parents) != required:
        raise ValueError(f"{call_id} returned invalid parents: {parents!r}")
    return {
        "memory_id": "m4",
        "content": lesson.strip(),
        "parent_memory_ids": parents,
        "source_session": "consolidation",
        "condition": condition,
    }


def recorded_descendants(
    memories: Sequence[Dict[str, Any]], source_ids: Iterable[str]
) -> Set[str]:
    """Return nodes reachable from source IDs through recorded parent links."""
    reached = set(source_ids)
    descendants: Set[str] = set()
    changed = True
    while changed:
        changed = False
        for memory in memories:
            memory_id = memory["memory_id"]
            parents = set(memory.get("parent_memory_ids", []))
            if memory_id not in reached and parents & reached:
                reached.add(memory_id)
                descendants.add(memory_id)
                changed = True
    return descendants


def semantic_tokens(text: str) -> Set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 4 and token not in _STOPWORDS
    }


def token_jaccard(left: str, right: str) -> float:
    a, b = semantic_tokens(left), semantic_tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def discovery_metrics(predicted: Set[str], expected: Set[str]) -> Dict[str, Any]:
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 1.0
    return {
        "predicted_ids": sorted(predicted),
        "expected_ids": sorted(expected),
        "precision": precision,
        "recall": recall,
    }


def _memory_by_id(memories: Sequence[Dict[str, Any]], memory_id: str) -> Dict[str, Any]:
    return next(memory for memory in memories if memory["memory_id"] == memory_id)


def _contains_entity(memory: Dict[str, Any], entity: str) -> bool:
    return _normalize_entity(entity) in _normalize_entity(memory["content"])


def _evaluate_condition(
    runner: EntityPilotRunner,
    name: str,
    archive: Sequence[Dict[str, Any]],
    eval_a: Dict[str, Any],
    eval_b: Dict[str, Any],
    expected_a: str,
    expected_b: str,
    original_m3: Dict[str, Any],
    replayed_later_records: int,
) -> Dict[str, Any]:
    answer_a = runner.answer(f"eval_{name}_a", eval_a, archive)
    answer_b = runner.answer(f"eval_{name}_b", eval_b, archive)
    entity_a = _safe_response_entity(answer_a)
    entity_b = _safe_response_entity(answer_b)
    mixed = next((m for m in archive if m["memory_id"] == "m4"), None)
    return {
        "chain_a": {
            "correct": _normalize_entity(entity_a) == _normalize_entity(expected_a),
            "entity": entity_a,
            "answer": answer_a,
        },
        "chain_b": {
            "correct": _normalize_entity(entity_b) == _normalize_entity(expected_b),
            "entity": entity_b,
            "answer": answer_b,
        },
        "archive_memory_ids": [m["memory_id"] for m in archive],
        "archive_size": len(archive),
        "false_entity_present": any(_contains_entity(m, FALSE_ENTITY) for m in archive),
        "m3_preserved_exactly": any(m == original_m3 for m in archive),
        "mixed_memory_retains_b": bool(mixed and _contains_entity(mixed, expected_b)),
        "mixed_memory_excludes_false_a": bool(
            mixed and not _contains_entity(mixed, FALSE_ENTITY)
        ),
        "replayed_later_records": replayed_later_records,
    }


def run_memoryarena_v2(backend: ModelBackend) -> Dict[str, Any]:
    """Run the frozen V2 hidden-dependency and preservation experiment."""
    from datasets import load_dataset

    dataset = load_dataset(DATASET_ID, DATASET_CONFIG, split=DATASET_SPLIT)
    chain_a, chain_b = dict(dataset[CHAIN_A_INDEX]), dict(dataset[CHAIN_B_INDEX])
    entities_a = {_normalize_entity(_reference_entity(x)) for x in chain_a["answers"]}
    entities_b = {_normalize_entity(_reference_entity(x)) for x in chain_b["answers"]}
    if entities_a != {"ihuoma sonia uche"}:
        raise ValueError(f"pinned chain A changed: {sorted(entities_a)}")
    if entities_b != {"tulsidas balaram"}:
        raise ValueError(f"pinned chain B changed: {sorted(entities_b)}")
    expected_a = _reference_entity(chain_a["answers"][0])
    expected_b = _reference_entity(chain_b["answers"][0])
    a0, a1, eval_a = (
        _session(chain_a, 0, "a"),
        _session(chain_a, 1, "a"),
        _session(chain_a, len(chain_a["questions"]) - 1, "a"),
    )
    b0 = _session(chain_b, 0, "b")
    eval_b = _session(chain_b, len(chain_b["questions"]) - 1, "b")
    runner = EntityPilotRunner(backend)

    initial_a = runner.answer("a0_initial_answer", a0, [])
    clean_m1 = runner.reflect(
        "clean_m1_write", a0, initial_a,
        _entity_feedback(expected_a, chain_a["answers"][0]),
        [], "m1", "corrected",
    )
    corrupted_evidence = _replace_identity(chain_a["answers"][0], FALSE_ENTITY)
    bad_m1 = runner.reflect(
        "bad_m1_write", a0, initial_a,
        _entity_feedback(FALSE_ENTITY, corrupted_evidence),
        [], "m1", "corrupted",
    )

    clean_a1 = runner.answer("clean_a1_answer", a1, [clean_m1])
    clean_m2 = runner.reflect(
        "clean_m2_hidden_write", a1, clean_a1, ACCEPTED_FEEDBACK,
        [], "m2", "corrected_replay",
    )
    bad_a1 = runner.answer("bad_a1_answer", a1, [bad_m1])
    bad_m2 = runner.reflect(
        "bad_m2_hidden_write", a1, bad_a1, ACCEPTED_FEEDBACK,
        [], "m2", "corrupted",
    )
    if clean_m2["parent_memory_ids"] or bad_m2["parent_memory_ids"]:
        raise AssertionError("hidden descendant unexpectedly recorded a parent")

    initial_b = runner.answer("b0_initial_answer", b0, [])
    m3 = runner.reflect(
        "m3_independent_write", b0, initial_b,
        _entity_feedback(expected_b, chain_b["answers"][0]),
        [], "m3", "independent_valid",
    )
    clean_m4 = _consolidate(runner, "clean_m4_write", [clean_m2, m3], "corrected_replay")
    bad_m4 = _consolidate(runner, "bad_m4_write", [bad_m2, m3], "corrupted")

    bad_history = [bad_m1, bad_m2, m3, bad_m4]
    clean_history = [clean_m1, clean_m2, m3, clean_m4]
    lineage_ids = recorded_descendants(bad_history, {"m1"})
    similarities = {
        memory["memory_id"]: token_jaccard(bad_m1["content"], memory["content"])
        for memory in bad_history[1:]
    }
    semantic_ids = {
        memory_id for memory_id, score in similarities.items()
        if score >= SEMANTIC_THRESHOLD
    }
    intervention_ids = {
        memory_id
        for memory_id in ("m2", "m3", "m4")
        if _memory_by_id(bad_history, memory_id)["content"]
        != _memory_by_id(clean_history, memory_id)["content"]
    }

    corrected_by_id = {m["memory_id"]: m for m in clean_history}
    selective_history = [clean_m1]
    for memory in bad_history[1:]:
        selective_history.append(
            corrected_by_id[memory["memory_id"]]
            if memory["memory_id"] in intervention_ids
            else memory
        )
    conditions_archives = {
        "no_repair": bad_history,
        "source_deleted": bad_history[1:],
        "source_corrected_only": [clean_m1, *bad_history[1:]],
        "recorded_lineage": [
            clean_m1,
            *(m for m in bad_history[1:] if m["memory_id"] not in lineage_ids),
        ],
        "semantic_deletion": [
            clean_m1,
            *(m for m in bad_history[1:] if m["memory_id"] not in semantic_ids),
        ],
        "temporal_rollback": [],
        "full_corrected_replay": clean_history,
        "selective_causal_replay": selective_history,
    }
    replay_costs = {
        "no_repair": 0,
        "source_deleted": 0,
        "source_corrected_only": 0,
        "recorded_lineage": 0,
        "semantic_deletion": 0,
        "temporal_rollback": 0,
        "full_corrected_replay": 3,
        "selective_causal_replay": len(intervention_ids),
    }
    conditions = {
        name: _evaluate_condition(
            runner, name, archive, eval_a, eval_b, expected_a, expected_b, m3,
            replay_costs[name],
        )
        for name, archive in conditions_archives.items()
    }
    oracle = conditions["full_corrected_replay"]
    for result in conditions.values():
        result["behavior_matches_full_replay"] = (
            result["chain_a"]["correct"] == oracle["chain_a"]["correct"]
            and result["chain_b"]["correct"] == oracle["chain_b"]["correct"]
            and _normalize_entity(result["chain_a"]["entity"])
            == _normalize_entity(oracle["chain_a"]["entity"])
            and _normalize_entity(result["chain_b"]["entity"])
            == _normalize_entity(oracle["chain_b"]["entity"])
        )

    criteria = {
        "corruption_changes_a1_behavior": (
            _normalize_entity(_safe_response_entity(clean_a1))
            != _normalize_entity(_safe_response_entity(bad_a1))
        ),
        "hidden_m2_harmful_after_m1_removed": not conditions["source_deleted"]["chain_a"]["correct"],
        "source_correction_leaves_residual_error": not conditions["source_corrected_only"]["chain_a"]["correct"],
        "recorded_lineage_leaves_residual_error": not conditions["recorded_lineage"]["chain_a"]["correct"],
        "selective_matches_full_replay": conditions["selective_causal_replay"]["behavior_matches_full_replay"],
        "selective_retains_m3_exactly": conditions["selective_causal_replay"]["m3_preserved_exactly"],
        "selective_replays_less_than_full": replay_costs["selective_causal_replay"] < replay_costs["full_corrected_replay"],
        "temporal_rollback_loses_chain_b": not conditions["temporal_rollback"]["chain_b"]["correct"],
    }
    criteria["mechanism_demonstrated"] = all(criteria.values())

    return {
        "protocol_version": "memoryarena-causal-repair/v2-frozen",
        "dataset": {
            "id": DATASET_ID,
            "config": DATASET_CONFIG,
            "split": DATASET_SPLIT,
            "chain_a": {"index": CHAIN_A_INDEX, "id": chain_a["id"], "sha256": _content_hash(chain_a)},
            "chain_b": {"index": CHAIN_B_INDEX, "id": chain_b["id"], "sha256": _content_hash(chain_b)},
        },
        "entities": {"chain_a": expected_a, "chain_b": expected_b, "false": FALSE_ENTITY},
        "construction": {
            "ground_truth_affected_later_ids": sorted(AFFECTED_LATER_IDS),
            "m2_parent_ids_clean": clean_m2["parent_memory_ids"],
            "m2_parent_ids_corrupted": bad_m2["parent_memory_ids"],
            "m4_parent_ids_clean": clean_m4["parent_memory_ids"],
            "m4_parent_ids_corrupted": bad_m4["parent_memory_ids"],
        },
        "discovery": {
            "recorded_lineage": discovery_metrics(lineage_ids, AFFECTED_LATER_IDS),
            "semantic_deletion": {
                **discovery_metrics(semantic_ids, AFFECTED_LATER_IDS),
                "threshold": SEMANTIC_THRESHOLD,
                "similarities": similarities,
            },
            "paired_intervention": discovery_metrics(intervention_ids, AFFECTED_LATER_IDS),
        },
        "memories": {
            "corrupted": {m["memory_id"]: m for m in bad_history},
            "corrected": {m["memory_id"]: m for m in clean_history},
        },
        "session_a1": {"clean_answer": clean_a1, "corrupted_answer": bad_a1},
        "conditions": conditions,
        "criteria": criteria,
        "calls": [call.as_dict() for call in runner.calls],
    }
