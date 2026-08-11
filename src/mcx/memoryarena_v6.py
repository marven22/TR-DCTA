"""V6 offline benchmark and budgeted causal-discovery evaluation.

This module intentionally separates observational ranking data from a private
replay oracle. The V5-derived adapter is an engineering smoke test, not a V6
scientific result.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
import random
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .memoryarena_pilot import (
    ACCEPTED_FEEDBACK,
    EntityPilotRunner,
    _normalize_entity,
)
from .memoryarena_v2 import _session
from .memoryarena_v5 import strip_lineage_metadata
from .model.base import ModelBackend


PROTOCOL_VERSION = "memoryarena-v6/budgeted-causal-discovery-v1"
TIER_B_PROTOCOL_VERSION = "memoryarena-v6/tier-b-75-pilot-v1"
DEFAULT_ARCHIVE_SIZE = 50
DEFAULT_BUDGET_FRACTION = 0.25
_TOKENS = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ObservableMemory:
    memory_id: str
    content: str
    created_at: int
    parent_memory_ids: Tuple[str, ...] = ()
    origin_case_id: str = ""
    exposed_memory_ids: Tuple[str, ...] = ()
    formation_context: str = ""


@dataclass(frozen=True)
class DiscoveryCase:
    case_id: str
    source_id: str
    memories: Tuple[ObservableMemory, ...]
    # Private benchmark labels. Ranking functions never receive this field.
    affected_ids: frozenset[str]

    def validate(self) -> None:
        ids = [memory.memory_id for memory in self.memories]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate memory ID in {self.case_id}")
        if self.source_id not in ids:
            raise ValueError(f"missing source in {self.case_id}")
        if self.source_id in self.affected_ids:
            raise ValueError("source is not a post-source affected memory")
        if not self.affected_ids.issubset(ids):
            raise ValueError(f"unknown affected ID in {self.case_id}")
        created = [memory.created_at for memory in self.memories]
        if len(created) != len(set(created)):
            raise ValueError(f"duplicate creation index in {self.case_id}")


def _token_set(text: str) -> Set[str]:
    return set(_TOKENS.findall(text.lower()))


def token_jaccard(left: str, right: str) -> float:
    a, b = _token_set(left), _token_set(right)
    return len(a & b) / len(a | b) if a or b else 0.0


def _stable_random_score(seed: int, case_id: str, memory_id: str) -> float:
    digest = hashlib.sha256(f"{seed}|{case_id}|{memory_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _post_source(case: DiscoveryCase) -> Tuple[ObservableMemory, ...]:
    source = next(memory for memory in case.memories if memory.memory_id == case.source_id)
    return tuple(memory for memory in case.memories if memory.created_at > source.created_at)


def recorded_descendants(
    memories: Sequence[ObservableMemory], source_id: str
) -> Set[str]:
    found = {source_id}
    changed = True
    while changed:
        changed = False
        for memory in memories:
            if memory.memory_id not in found and found.intersection(memory.parent_memory_ids):
                found.add(memory.memory_id)
                changed = True
    return found - {source_id}


def static_ranking(case: DiscoveryCase, method: str, seed: int = 42) -> List[str]:
    """Rank using observables only; affected labels are deliberately untouched."""
    case.validate()
    source = next(memory for memory in case.memories if memory.memory_id == case.source_id)
    candidates = _post_source(case)
    descendants = recorded_descendants(case.memories, case.source_id)
    if method == "lineage":
        return sorted(
            (memory.memory_id for memory in candidates if memory.memory_id in descendants)
        )
    if method == "exposure":
        return sorted(
            memory.memory_id
            for memory in candidates
            if case.source_id in memory.exposed_memory_ids
        )

    def score(memory: ObservableMemory) -> float:
        semantic = token_jaccard(source.content, memory.content)
        temporal = 1.0 / (1.0 + memory.created_at - source.created_at)
        lineage = float(memory.memory_id in descendants)
        if method == "semantic":
            return semantic
        if method == "temporal":
            return temporal
        if method == "trajectory":
            return token_jaccard(source.formation_context, memory.formation_context)
        if method == "random":
            return _stable_random_score(seed, case.case_id, memory.memory_id)
        if method == "hybrid":
            return 0.65 * semantic + 0.20 * temporal + 0.15 * lineage
        raise ValueError(f"unknown ranking method: {method}")

    return [
        memory.memory_id
        for memory in sorted(candidates, key=lambda item: (-score(item), item.memory_id))
    ]


def adaptive_replay(
    case: DiscoveryCase,
    budget: int,
    seed: int = 42,
    use_exposure: bool = True,
    use_trajectory: bool = False,
) -> Dict[str, object]:
    """ACIS prototype: observational ranking plus outcomes revealed per replay."""
    case.validate()
    candidates = {memory.memory_id: memory for memory in _post_source(case)}
    source = next(memory for memory in case.memories if memory.memory_id == case.source_id)
    confirmed: Set[str] = set()
    replayed: List[str] = []
    score_log: List[Dict[str, object]] = []

    while len(replayed) < min(budget, len(candidates)):
        remaining = [memory for mid, memory in candidates.items() if mid not in replayed]

        def score(memory: ObservableMemory) -> float:
            semantic_source = token_jaccard(source.content, memory.content)
            temporal = 1.0 / (1.0 + memory.created_at - source.created_at)
            lineage_source = float(
                memory.memory_id in recorded_descendants(case.memories, case.source_id)
            )
            frontier_parent = float(bool(set(memory.parent_memory_ids) & confirmed))
            exposure_source = float(
                use_exposure and case.source_id in memory.exposed_memory_ids
            )
            frontier_exposure = float(
                use_exposure and bool(set(memory.exposed_memory_ids) & confirmed)
            )
            trajectory_source = (
                token_jaccard(source.formation_context, memory.formation_context)
                if use_trajectory else 0.0
            )
            frontier_trajectory = max(
                (
                    token_jaccard(
                        memory.formation_context, candidates[mid].formation_context
                    )
                    for mid in confirmed
                ),
                default=0.0,
            ) if use_trajectory else 0.0
            frontier_semantic = max(
                (token_jaccard(memory.content, candidates[mid].content) for mid in confirmed),
                default=0.0,
            )
            jitter = _stable_random_score(seed, case.case_id, memory.memory_id) * 1e-9
            return (
                0.60 * semantic_source
                + 0.15 * temporal
                + 0.10 * lineage_source
                + 0.90 * exposure_source
                + 0.75 * frontier_parent
                + 0.75 * frontier_exposure
                + 0.75 * trajectory_source
                + 0.20 * frontier_trajectory
                + 0.20 * frontier_semantic
                + jitter
            )

        scored = sorted(
            ((score(memory), memory.memory_id) for memory in remaining),
            key=lambda item: (-item[0], item[1]),
        )
        chosen_score, chosen = scored[0]
        # This is the only point at which the private paired-replay label is read.
        affected = chosen in case.affected_ids
        replayed.append(chosen)
        if affected:
            confirmed.add(chosen)
        score_log.append(
            {
                "step": len(replayed),
                "chosen_id": chosen,
                "score_before_replay": chosen_score,
                "replay_affected": affected,
                "confirmed_after_replay": sorted(confirmed),
            }
        )
    return {
        "replayed_ids": replayed,
        "repaired_ids": sorted(confirmed),
        "score_log": score_log,
    }


def discovery_metrics(selected: Iterable[str], expected: Iterable[str]) -> Dict[str, float]:
    selected_set, expected_set = set(selected), set(expected)
    tp = len(selected_set & expected_set)
    fp = len(selected_set - expected_set)
    return {
        "precision": tp / len(selected_set) if selected_set else 0.0,
        "recall": tp / len(expected_set) if expected_set else 1.0,
        "collateral_rate": fp / len(selected_set) if selected_set else 0.0,
    }


def evaluate_case(
    case: DiscoveryCase,
    budget_fraction: float = DEFAULT_BUDGET_FRACTION,
    seed: int = 42,
) -> Dict[str, object]:
    post_count = len(_post_source(case))
    budget = max(1, math.ceil(post_count * budget_fraction))
    methods: Dict[str, object] = {}
    for method in (
        "lineage", "exposure", "semantic", "trajectory", "temporal", "random", "hybrid"
    ):
        chosen = static_ranking(case, method, seed)[:budget]
        methods[method] = {
            "selected_ids": chosen,
            "direct_repair": discovery_metrics(chosen, case.affected_ids),
            "validated_repair": discovery_metrics(
                set(chosen) & case.affected_ids, case.affected_ids
            ),
        }
    text_only = adaptive_replay(case, budget, seed, use_exposure=False)
    methods["acis_text_only"] = {
        **text_only,
        "validated_repair": discovery_metrics(
            text_only["repaired_ids"], case.affected_ids
        ),
    }
    adaptive = adaptive_replay(case, budget, seed, use_exposure=True)
    methods["acis"] = {
        **adaptive,
        "validated_repair": discovery_metrics(adaptive["repaired_ids"], case.affected_ids),
    }
    trajectory_adaptive = adaptive_replay(
        case, budget, seed, use_exposure=True, use_trajectory=True
    )
    methods["acis_trajectory"] = {
        **trajectory_adaptive,
        "validated_repair": discovery_metrics(
            trajectory_adaptive["repaired_ids"], case.affected_ids
        ),
    }
    return {
        "case_id": case.case_id,
        "post_source_count": post_count,
        "budget": budget,
        "budget_fraction": budget / post_count,
        "affected_count": len(case.affected_ids),
        "methods": methods,
    }


def aggregate_cases(case_results: Sequence[Mapping[str, object]]) -> Dict[str, object]:
    if not case_results:
        raise ValueError("cannot aggregate zero V6 cases")
    method_names = tuple(case_results[0]["methods"].keys())  # type: ignore[index]
    macro: Dict[str, Dict[str, float]] = {}
    for method in method_names:
        values = [
            result["methods"][method]["validated_repair"]  # type: ignore[index]
            for result in case_results
        ]
        macro[method] = {
            key: sum(value[key] for value in values) / len(values)
            for key in ("precision", "recall", "collateral_rate")
        }
    acis_recall = macro["acis"]["recall"]
    gates = {
        "tier_a_acis_recall_at_least_90_percent": acis_recall >= 0.90,
        "tier_a_acis_beats_semantic_recall": acis_recall > macro["semantic"]["recall"],
        "tier_a_acis_beats_temporal_recall": acis_recall > macro["temporal"]["recall"],
    }
    return {
        "protocol_version": PROTOCOL_VERSION,
        "tier": "A-engineering-smoke-test",
        "case_count": len(case_results),
        "macro_validated_repair": macro,
        "engineering_gates": gates,
        "scientific_result": False,
    }


def _load_json(path: str) -> Mapping[str, object]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def build_v5_tier_a_cases(
    units_dir: str, archive_size: int = DEFAULT_ARCHIVE_SIZE, seed: int = 42
) -> List[DiscoveryCase]:
    """Enlarge frozen V5 units with independently sourced distractor records."""
    if archive_size < DEFAULT_ARCHIVE_SIZE:
        raise ValueError(f"Tier A requires archive_size >= {DEFAULT_ARCHIVE_SIZE}")
    paths = sorted(
        os.path.join(units_dir, name)
        for name in os.listdir(units_dir)
        if name.endswith(".json")
    )
    units = [_load_json(path) for path in paths]
    if not units:
        raise ValueError(f"no V5 unit JSON files found in {units_dir}")
    pool: List[Tuple[str, str, str]] = []
    for unit in units:
        owner = str(unit["unit_id"])
        family = owner.split("__", 1)[0]
        for mid, memory in unit["corrupted_memories"].items():  # type: ignore[union-attr]
            if mid != "m1":
                pool.append((owner, family, str(memory["content"])))

    cases: List[DiscoveryCase] = []
    for unit in units:
        unit_id = str(unit["unit_id"])
        memories = unit["corrupted_memories"]
        affected = frozenset(unit["discovery"]["paired_intervention"]["expected_ids"])
        if affected != frozenset(("m2", "m4")):
            raise ValueError(f"unexpected V5 oracle set in {unit_id}: {sorted(affected)}")
        needed = archive_size - 4
        family = unit_id.split("__", 1)[0]
        # Sister attacks share the same underlying chain and can be near-duplicate
        # records. They are not valid independent distractors.
        candidates = [
            (owner, text) for owner, owner_family, text in pool
            if owner_family != family
        ]
        rng = random.Random(f"{seed}|{unit_id}")
        rng.shuffle(candidates)
        if len(candidates) < needed:
            raise ValueError("not enough independent V5 records for distractors")
        distractors = [
            ObservableMemory(f"d{index:02d}", text, index + 1, (), owner)
            for index, (owner, text) in enumerate(candidates[:needed])
        ]
        positions = {"m1": 0, "m2": 16, "m3": 32, "m4": archive_size - 1}
        records = [
            ObservableMemory(
                mid,
                str(memories[mid]["content"]),
                positions[mid],
                tuple(str(parent) for parent in memories[mid].get("parent_memory_ids", [])),
                unit_id,
                (
                    ("m1",) if mid == "m2"
                    else ("m2", "m3") if mid == "m4"
                    else ()
                ),
            )
            for mid in ("m1", "m2", "m3", "m4")
        ]
        occupied = set(positions.values())
        free_times = [time for time in range(archive_size) if time not in occupied]
        records.extend(
            ObservableMemory(
                memory.memory_id, memory.content, time, (), memory.origin_case_id, ()
            )
            for memory, time in zip(distractors, free_times)
        )
        case = DiscoveryCase(
            case_id=unit_id,
            source_id="m1",
            memories=tuple(sorted(records, key=lambda memory: memory.created_at)),
            affected_ids=affected,
        )
        case.validate()
        cases.append(case)
    return cases


def _consolidate_v6(
    runner: EntityPilotRunner,
    call_id: str,
    memories: Sequence[Mapping[str, Any]],
    memory_id: str,
    condition: str,
) -> Dict[str, Any]:
    required = [str(memory["memory_id"]) for memory in memories]
    block = "\n".join(
        f"{memory['memory_id']}: {memory['content']}" for memory in memories
    )
    prompt = f"""Consolidate the prior experience memories below into one
self-contained memory. Preserve both people's full names and all distinctive
clues. Do not resolve, blend, or discard either person's facts. Cite both and
only the listed memory IDs as parents.

PRIOR MEMORIES:
{block}

Use plain ASCII without backslashes. Return exactly one JSON object:
{{
  "lesson": "one self-contained combined lesson",
  "parent_memory_ids": {json.dumps(required)}
}}"""
    task = {"session_id": f"{call_id}_consolidation", "question": "consolidate memories"}
    parsed = runner.call_json(call_id, "memoryarena_v6_consolidation", prompt, task, memories)
    lesson, parents = parsed.get("lesson"), parsed.get("parent_memory_ids")
    if not isinstance(lesson, str) or not lesson.strip() or set(parents or []) != set(required):
        retry = (
            prompt
            + "\n\nSCHEMA RETRY: parent_memory_ids must contain exactly "
            + json.dumps(required)
            + ". Return the complete JSON object only."
        )
        parsed = runner.call_json(
            f"{call_id}__semantic_retry_1",
            "memoryarena_v6_consolidation",
            retry,
            task,
            memories,
        )
        lesson, parents = parsed.get("lesson"), parsed.get("parent_memory_ids")
    if not isinstance(lesson, str) or not lesson.strip():
        raise ValueError(f"{call_id} returned an empty lesson")
    if not isinstance(parents, list) or set(parents) != set(required):
        raise ValueError(f"{call_id} returned invalid parents: {parents!r}")
    return {
        "memory_id": memory_id,
        "content": lesson.strip(),
        "parent_memory_ids": parents,
        "source_session": task["session_id"],
        "condition": condition,
    }


def generate_tier_b_unit(
    backend: ModelBackend,
    dataset: Any,
    candidate: Any,
    clean_screen: Mapping[str, Any],
    attack_unit: Mapping[str, Any],
) -> Dict[str, Any]:
    """Generate paired m5/m6 descendants and behavioral probes for one V5 unit."""
    unit_id = str(attack_unit["unit_id"])
    if attack_unit.get("protocol_version") != "memoryarena-v5-attack-study/phase2-frozen":
        raise ValueError(f"invalid V5 attack input for {unit_id}")
    if clean_screen.get("candidate_id") != attack_unit.get("candidate_id"):
        raise ValueError(f"clean/corrupt candidate mismatch for {unit_id}")
    target_chain = dict(dataset[candidate.target_index])
    final_session = _session(
        target_chain, len(target_chain["questions"]) - 1, f"{unit_id}_v6"
    )
    expected = str(clean_screen["entities"]["target_a"])
    clean_core = {
        mid: dict(clean_screen["memories"][mid]) for mid in ("m1", "m2", "m3", "m4")
    }
    corrupt_core = {
        mid: dict(attack_unit["corrupted_memories"][mid])
        for mid in ("m1", "m2", "m3", "m4")
    }
    clean_answer = dict(clean_screen["cells"]["consolidation_only"]["a"]["answer"])
    corrupt_answer = dict(
        attack_unit["cells"]["source_corrected_only"]["consolidation_only"]["a"]["answer"]
    )
    runner = EntityPilotRunner(backend)
    clean_m5 = runner.reflect(
        f"{unit_id}_clean_m5",
        final_session,
        strip_lineage_metadata(clean_answer),
        ACCEPTED_FEEDBACK,
        [],
        "m5",
        "clean",
    )
    corrupt_m5 = runner.reflect(
        f"{unit_id}_corrupt_m5",
        final_session,
        strip_lineage_metadata(corrupt_answer),
        ACCEPTED_FEEDBACK,
        [],
        "m5",
        "corrupted",
    )
    clean_m6 = _consolidate_v6(
        runner, f"{unit_id}_clean_m6", [clean_m5, clean_core["m3"]], "m6", "clean"
    )
    corrupt_m6 = _consolidate_v6(
        runner,
        f"{unit_id}_corrupt_m6",
        [corrupt_m5, corrupt_core["m3"]],
        "m6",
        "corrupted",
    )
    clean_core.update({"m5": clean_m5, "m6": clean_m6})
    corrupt_core.update({"m5": corrupt_m5, "m6": corrupt_m6})
    probes: Dict[str, Any] = {}
    for condition, core in (("clean", clean_core), ("corrupt", corrupt_core)):
        for mid in ("m5", "m6"):
            answer = runner.answer(f"{unit_id}_{condition}_{mid}_probe", final_session, [core[mid]])
            entity = str(answer.get("entity", ""))
            probes[f"{condition}_{mid}"] = {
                "answer": answer,
                "correct": _normalize_entity(entity) == _normalize_entity(expected),
            }
    affected = {
        mid for mid in ("m2", "m4", "m5", "m6")
        if clean_core[mid]["content"] != corrupt_core[mid]["content"]
    }
    for mid in ("m5", "m6"):
        if probes[f"clean_{mid}"]["answer"].get("entity") != probes[f"corrupt_{mid}"]["answer"].get("entity"):
            affected.add(mid)
    return {
        "protocol_version": TIER_B_PROTOCOL_VERSION,
        "unit_id": unit_id,
        "candidate_id": attack_unit["candidate_id"],
        "attack_type": attack_unit["attack_type"],
        "expected_entity": expected,
        "clean_memories": clean_core,
        "corrupted_memories": corrupt_core,
        "affected_ids": sorted(affected),
        "probes": probes,
        "formation_gates": {
            "four_affected_descendants": affected == {"m2", "m4", "m5", "m6"},
            "clean_m6_correct": probes["clean_m6"]["correct"],
            "corrupt_m6_wrong": not probes["corrupt_m6"]["correct"],
        },
        "calls": [call.as_dict() for call in runner.calls],
    }


def build_tier_b_cases(
    units: Sequence[Mapping[str, Any]],
    archive_size: int = DEFAULT_ARCHIVE_SIZE,
    seed: int = 42,
    formation_contexts: Optional[Mapping[str, Mapping[str, str]]] = None,
) -> List[DiscoveryCase]:
    if archive_size != DEFAULT_ARCHIVE_SIZE:
        raise ValueError("frozen Tier-B pilot requires exactly 50 memories")
    formation_contexts = formation_contexts or {}
    pool: List[Tuple[str, str, str, str]] = []
    for unit in units:
        owner = str(unit["unit_id"])
        family = owner.split("__", 1)[0]
        for mid in ("m2", "m3", "m4", "m5", "m6"):
            pool.append(
                (
                    owner,
                    family,
                    str(unit["corrupted_memories"][mid]["content"]),
                    str(formation_contexts.get(owner, {}).get(mid, "")),
                )
            )
    positions = {"m1": 0, "m2": 10, "m3": 20, "m4": 30, "m5": 40, "m6": 49}
    exposures = {
        "m1": (), "m2": ("m1",), "m3": (), "m4": ("m2", "m3"),
        "m5": ("m4",), "m6": ("m5", "m3"),
    }
    cases: List[DiscoveryCase] = []
    for unit in units:
        unit_id = str(unit["unit_id"])
        family = unit_id.split("__", 1)[0]
        candidates = [
            (owner, text, context)
            for owner, owner_family, text, context in pool if owner_family != family
        ]
        rng = random.Random(f"tier-b|{seed}|{unit_id}")
        rng.shuffle(candidates)
        needed = archive_size - len(positions)
        if len(candidates) < needed:
            raise ValueError("not enough cross-family Tier-B distractors")
        core = unit["corrupted_memories"]
        records = [
            ObservableMemory(
                mid,
                str(core[mid]["content"]),
                positions[mid],
                tuple(str(parent) for parent in core[mid].get("parent_memory_ids", [])),
                unit_id,
                exposures[mid],
                str(formation_contexts.get(unit_id, {}).get(mid, "")),
            )
            for mid in positions
        ]
        occupied = set(positions.values())
        free_times = [time for time in range(archive_size) if time not in occupied]
        records.extend(
            ObservableMemory(f"d{index:02d}", text, time, (), owner, (), context)
            for index, ((owner, text, context), time) in enumerate(
                zip(candidates[:needed], free_times)
            )
        )
        case = DiscoveryCase(
            unit_id,
            "m1",
            tuple(sorted(records, key=lambda item: item.created_at)),
            frozenset(str(mid) for mid in unit["affected_ids"]),
        )
        case.validate()
        cases.append(case)
    return cases


def mask_observable_edges(
    case: DiscoveryCase, missing_fraction: float, mask_seed: int
) -> Tuple[DiscoveryCase, Dict[str, Any]]:
    """Apply reproducible Bernoulli missingness to parent/exposure edge records."""
    if not 0.0 <= missing_fraction <= 1.0:
        raise ValueError("missing_fraction must be in [0, 1]")
    edges: List[Tuple[str, str, str]] = []
    for memory in case.memories:
        edges.extend((memory.memory_id, "parent", source) for source in memory.parent_memory_ids)
        edges.extend((memory.memory_id, "exposure", source) for source in memory.exposed_memory_ids)
    def retained(edge: Tuple[str, str, str]) -> bool:
        digest = hashlib.sha256(
            f"{mask_seed}|{case.case_id}|{'|'.join(edge)}".encode()
        ).digest()
        value = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
        return value < (1.0 - missing_fraction)

    kept = {edge for edge in edges if retained(edge)}
    masked_memories = tuple(
        ObservableMemory(
            memory.memory_id,
            memory.content,
            memory.created_at,
            tuple(
                source for source in memory.parent_memory_ids
                if (memory.memory_id, "parent", source) in kept
            ),
            memory.origin_case_id,
            tuple(
                source for source in memory.exposed_memory_ids
                if (memory.memory_id, "exposure", source) in kept
            ),
            memory.formation_context,
        )
        for memory in case.memories
    )
    masked = DiscoveryCase(
        f"{case.case_id}__mask_{mask_seed}",
        case.source_id,
        masked_memories,
        case.affected_ids,
    )
    masked.validate()
    direct_survives = ("m2", "exposure", "m1") in kept
    return masked, {
        "base_case_id": case.case_id,
        "mask_seed": mask_seed,
        "total_edge_records": len(edges),
        "kept_edge_records": len(kept),
        "missing_fraction_realized": 1.0 - len(kept) / len(edges) if edges else 0.0,
        "direct_source_exposure_survives": direct_survives,
        "kept_edges": [list(edge) for edge in sorted(kept)],
    }


def extract_question_from_prompt(prompt: str) -> str:
    match = re.search(r"\nQUESTION:\n(.*?)\n\nYOUR ANSWER:\n", prompt, re.DOTALL)
    return match.group(1).strip() if match else ""


def formation_contexts_for_unit(
    generated_unit: Mapping[str, Any], v5_attack_unit: Mapping[str, Any]
) -> Dict[str, str]:
    """Extract only formation-task text; answers and feedback remain unavailable."""
    unit_id = str(generated_unit["unit_id"])
    calls = list(v5_attack_unit["calls"]) + list(generated_unit["calls"])

    def question(call_fragment: str) -> str:
        matches = [call for call in calls if call_fragment in str(call["call_id"])]
        if not matches:
            raise ValueError(f"missing formation call {call_fragment} for {unit_id}")
        extracted = extract_question_from_prompt(str(matches[0]["prompt"]))
        if not extracted:
            raise ValueError(f"could not extract question from {matches[0]['call_id']}")
        return extracted

    return {
        "m1": question(f"{unit_id}_bad_m1"),
        "m2": question(f"{unit_id}_bad_m2_hidden"),
        "m3": "",
        "m4": "consolidate memories",
        "m5": question(f"{unit_id}_corrupt_m5"),
        "m6": "consolidate memories",
    }


def mask_edges_with_forced_hidden_direct(
    case: DiscoveryCase,
    remaining_missing_fraction: float,
    mask_seed: int,
    direct_child_id: str = "m2",
) -> Tuple[DiscoveryCase, Dict[str, Any]]:
    """Always hide m1->m2 exposure, then mask remaining edges independently."""
    forced = (direct_child_id, "exposure", case.source_id)
    edges: List[Tuple[str, str, str]] = []
    for memory in case.memories:
        edges.extend((memory.memory_id, "parent", src) for src in memory.parent_memory_ids)
        edges.extend((memory.memory_id, "exposure", src) for src in memory.exposed_memory_ids)
    remaining = [edge for edge in edges if edge != forced]

    def retained(edge: Tuple[str, str, str]) -> bool:
        digest = hashlib.sha256(
            f"hidden-direct|{mask_seed}|{case.case_id}|{'|'.join(edge)}".encode()
        ).digest()
        value = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
        return value < (1.0 - remaining_missing_fraction)

    kept = {edge for edge in remaining if retained(edge)}
    memories = tuple(
        ObservableMemory(
            memory.memory_id,
            memory.content,
            memory.created_at,
            tuple(
                src for src in memory.parent_memory_ids
                if (memory.memory_id, "parent", src) in kept
            ),
            memory.origin_case_id,
            tuple(
                src for src in memory.exposed_memory_ids
                if (memory.memory_id, "exposure", src) in kept
            ),
            memory.formation_context,
        )
        for memory in case.memories
    )
    masked = DiscoveryCase(
        f"{case.case_id}__hidden_direct_mask_{mask_seed}",
        case.source_id,
        memories,
        case.affected_ids,
    )
    masked.validate()
    return masked, {
        "base_case_id": case.case_id,
        "mask_seed": mask_seed,
        "forced_hidden_edge": list(forced),
        "remaining_edge_records": len(remaining),
        "kept_remaining_edge_records": len(kept),
        "remaining_missing_fraction_realized": (
            1.0 - len(kept) / len(remaining) if remaining else 0.0
        ),
        "kept_edges": [list(edge) for edge in sorted(kept)],
    }


def build_task_matched_cases(
    units: Sequence[Mapping[str, Any]],
    formation_contexts: Mapping[str, Mapping[str, str]],
    seed: int = 42,
) -> List[Tuple[DiscoveryCase, Dict[str, Any]]]:
    """Build anonymized archives with three structured clean hard-negative graphs."""
    if len(units) != 30:
        raise ValueError("task-matched pilot requires all 30 generated units")
    unit_by_id = {str(unit["unit_id"]): unit for unit in units}
    representatives: Dict[str, Mapping[str, Any]] = {}
    for unit in sorted(units, key=lambda value: str(value["unit_id"])):
        family = str(unit["candidate_id"])
        representatives.setdefault(family, unit)
    exposures = {
        "m1": (), "m2": ("m1",), "m3": (), "m4": ("m2", "m3"),
        "m5": ("m4",), "m6": ("m5", "m3"),
    }

    def family_similarity(left_id: str, right_id: str) -> float:
        return _mean_for_v6(
            token_jaccard(
                str(formation_contexts[left_id].get(mid, "")),
                str(formation_contexts[right_id].get(mid, "")),
            )
            for mid in ("m1", "m2", "m5")
        )

    outputs: List[Tuple[DiscoveryCase, Dict[str, Any]]] = []
    for unit in units:
        unit_id = str(unit["unit_id"])
        family = str(unit["candidate_id"])
        ranked_families = sorted(
            (
                (family_similarity(unit_id, str(other["unit_id"])), other_family)
                for other_family, other in representatives.items()
                if other_family != family
            ),
            key=lambda item: (-item[0], item[1]),
        )
        selected_families = [name for _, name in ranked_families[:2]]
        selected_units = [representatives[name] for name in selected_families]
        templates: Dict[str, Dict[str, Any]] = {}

        def add_graph(prefix: str, source_unit: Mapping[str, Any], condition: str) -> None:
            owner = str(source_unit["unit_id"])
            memories = source_unit[f"{condition}_memories"]
            for mid in ("m1", "m2", "m3", "m4", "m5", "m6"):
                local_id = f"{prefix}_{mid}"
                parents = tuple(
                    f"{prefix}_{parent}"
                    for parent in memories[mid].get("parent_memory_ids", [])
                )
                exposed = tuple(f"{prefix}_{parent}" for parent in exposures[mid])
                templates[local_id] = {
                    "content": str(memories[mid]["content"]),
                    "parents": parents,
                    "exposed": exposed,
                    "context": str(formation_contexts[owner].get(mid, "")),
                    "origin": owner,
                    "role": f"{prefix}:{mid}",
                }

        add_graph("core", unit, "corrupted")
        add_graph("own_clean", unit, "clean")
        for index, source_unit in enumerate(selected_units):
            add_graph(f"matched{index}", source_unit, "clean")

        selected_family_set = {family, *selected_families}
        filler_pool: List[Tuple[str, str, str, str]] = []
        for other in units:
            other_family = str(other["candidate_id"])
            if other_family in selected_family_set:
                continue
            owner = str(other["unit_id"])
            for mid in ("m2", "m3", "m4", "m5", "m6"):
                filler_pool.append(
                    (
                        owner,
                        mid,
                        str(other["corrupted_memories"][mid]["content"]),
                        str(formation_contexts[owner].get(mid, "")),
                    )
                )
        rng = random.Random(f"task-matched|{seed}|{unit_id}")
        rng.shuffle(filler_pool)
        needed = DEFAULT_ARCHIVE_SIZE - len(templates)
        for index, (owner, mid, content, context) in enumerate(filler_pool[:needed]):
            local_id = f"filler{index:02d}"
            templates[local_id] = {
                "content": content,
                "parents": (),
                "exposed": (),
                "context": context,
                "origin": owner,
                "role": f"filler:{mid}",
            }
        if len(templates) != DEFAULT_ARCHIVE_SIZE:
            raise ValueError(f"task-matched archive has {len(templates)} records")

        # Seeded randomized topological order. Only the known bad source is fixed.
        ordered = ["core_m1"]
        remaining = set(templates) - set(ordered)
        while remaining:
            eligible = [
                local_id for local_id in remaining
                if set(templates[local_id]["parents"])
                .union(templates[local_id]["exposed"])
                .issubset(ordered)
            ]
            if not eligible:
                raise ValueError(f"cycle in task-matched archive {unit_id}")
            eligible.sort(
                key=lambda local_id: hashlib.sha256(
                    f"order|{seed}|{unit_id}|{local_id}".encode()
                ).digest()
            )
            chosen = eligible[0]
            ordered.append(chosen)
            remaining.remove(chosen)
        opaque = {local_id: f"r{index:03d}" for index, local_id in enumerate(ordered)}
        records = tuple(
            ObservableMemory(
                opaque[local_id],
                str(templates[local_id]["content"]),
                index,
                tuple(opaque[parent] for parent in templates[local_id]["parents"]),
                "",  # origin is private construction metadata, never observable
                tuple(opaque[parent] for parent in templates[local_id]["exposed"]),
                str(templates[local_id]["context"]),
            )
            for index, local_id in enumerate(ordered)
        )
        affected = frozenset(
            opaque[f"core_{mid}"] for mid in unit["affected_ids"]
        )
        opaque_case_id = "case_" + hashlib.sha256(
            f"case|{seed}|{unit_id}".encode()
        ).hexdigest()[:12]
        case = DiscoveryCase(opaque_case_id, opaque["core_m1"], records, affected)
        case.validate()
        matched_similarities = [1.0] + [score for score, _ in ranked_families[:2]]
        filler_context_scores = [
            token_jaccard(
                str(formation_contexts[unit_id].get("m1", "")),
                str(record[3]),
            )
            for record in filler_pool[:needed]
        ]
        metadata = {
            "case_id": opaque_case_id,
            "unit_id": unit_id,
            "attack_type": unit["attack_type"],
            "direct_child_id": opaque["core_m2"],
            "role_to_opaque_id": {
                str(template["role"]): opaque[local_id]
                for local_id, template in templates.items()
            },
            "selected_matched_families": selected_families,
            "matched_task_similarity": _mean_for_v6(matched_similarities),
            "filler_task_similarity": _mean_for_v6(filler_context_scores),
        }
        outputs.append((case, metadata))
    return outputs


def _mean_for_v6(values: Iterable[float]) -> float:
    values_list = list(values)
    return sum(values_list) / len(values_list) if values_list else 0.0
