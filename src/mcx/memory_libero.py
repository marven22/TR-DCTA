"""Deterministic Memory-LIBERO archive adapter and discovery evaluation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import random
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from .memoryarena_v6 import (
    DiscoveryCase, ObservableMemory, recorded_descendants, static_ranking,
    token_jaccard,
)
from .risk_aware_acis import LogisticCalibrator, adaptive_three_signal_replay
from .scacd_up import FiniteCascadeBelief, LatentWorld, run_belief_policy


PROTOCOL = "memory-libero/source-conditioned-provenance-pilot-v0.2"
CONDITIONS = ("complete", "deleted", "deleted_spurious")
BUDGETS = (1, 2, 3, 6, 12)


@dataclass(frozen=True)
class LiberoArchive:
    archive_id: str
    source_id: str
    branch_ids: Tuple[Tuple[str, ...], ...]
    true_edges: frozenset[Tuple[str, str]]
    memories: Mapping[str, Mapping[str, object]]
    counterfactuals: Mapping[str, Mapping[str, object]]
    task_languages: Mapping[str, str]
    created_at: Mapping[str, int]
    affected_ids: frozenset[str]
    target_language: str
    native_policy_id: str


def _opaque(archive_id: str, raw_id: str) -> str:
    return "m_" + hashlib.sha256(f"{archive_id}|{raw_id}".encode()).hexdigest()[:16]


def build_archive(record: Mapping[str, object]) -> LiberoArchive:
    archive_id = str(record["archive_id"])
    raw_source = str(record["invalid_source"]["memory_id"])  # type: ignore[index]
    raw_branches = [
        tuple(item["memory_id"] for item in record["affected_branch"])  # type: ignore[index]
    ] + [
        tuple(item["memory_id"] for item in branch["memories"])
        for branch in record["clean_branches"]  # type: ignore[index]
    ]
    mapping = {raw_source: _opaque(archive_id, raw_source)}
    for raw_id in (node for branch in raw_branches for node in branch):
        mapping[raw_id] = _opaque(archive_id, raw_id)
    source_id = mapping[raw_source]
    branch_ids = tuple(tuple(mapping[node] for node in branch) for branch in raw_branches)

    memories: Dict[str, Mapping[str, object]] = {
        source_id: record["invalid_source"]  # type: ignore[dict-item]
    }
    counterfactuals: Dict[str, Mapping[str, object]] = {}
    task_languages = {source_id: str(record["target"]["target_language"])}  # type: ignore[index]
    created_at = {source_id: 0}
    order = 1
    for item in record["affected_branch"]:  # type: ignore[index]
        node = mapping[item["memory_id"]]
        if item["factual"]["parsed"] is None or item["counterfactual"]["parsed"] is None:
            raise ValueError(f"non-strict parsed record in {archive_id}")
        memories[node] = item["factual"]["parsed"]
        counterfactuals[node] = item["counterfactual"]["parsed"]
        task_languages[node] = str(record["target"]["target_language"])  # type: ignore[index]
        created_at[node] = order
        order += 1
    for branch in record["clean_branches"]:  # type: ignore[index]
        for item in branch["memories"]:
            node = mapping[item["memory_id"]]
            if item["generation"]["parsed"] is None:
                raise ValueError(f"invalid clean record in {archive_id}")
            memories[node] = item["generation"]["parsed"]
            task_languages[node] = str(branch["task_language"])
            created_at[node] = order
            order += 1

    edges = {(source_id, branch_ids[0][0])}
    for branch in branch_ids:
        edges.update(zip(branch, branch[1:]))
    return LiberoArchive(
        archive_id=archive_id, source_id=source_id, branch_ids=branch_ids,
        true_edges=frozenset(edges), memories=memories,
        counterfactuals=counterfactuals, task_languages=task_languages,
        created_at=created_at, affected_ids=frozenset(branch_ids[0]),
        target_language=str(record["target"]["target_language"]),  # type: ignore[index]
        native_policy_id=str(record["native_policy_id"]),
    )


def _seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def possible_chronological_edges(archive: LiberoArchive) -> frozenset[Tuple[str, str]]:
    nodes = sorted(archive.created_at, key=archive.created_at.get)
    return frozenset(
        (left, right) for left in nodes for right in nodes
        if archive.created_at[left] < archive.created_at[right]
    )


def mask_edges(archive: LiberoArchive, condition: str, mask_index: int) -> frozenset[Tuple[str, str]]:
    if condition not in CONDITIONS or not 0 <= mask_index < 10:
        raise ValueError("unknown condition or mask index")
    if condition == "complete":
        return archive.true_edges
    direct = (archive.source_id, archive.branch_ids[0][0])
    rng = random.Random(_seed(PROTOCOL, archive.archive_id, "deleted", mask_index))
    observed = {
        edge for edge in sorted(archive.true_edges)
        if edge != direct and rng.random() < 0.5
    }
    if condition == "deleted_spurious":
        candidates = sorted(possible_chronological_edges(archive) - archive.true_edges)
        spurious_rng = random.Random(
            _seed(PROTOCOL, archive.archive_id, "spurious", mask_index)
        )
        observed.update(spurious_rng.sample(candidates, round(0.20 * len(archive.true_edges))))
    return frozenset(observed)


def channel_rates(
    archives: Sequence[LiberoArchive], condition: str
) -> Tuple[float, float, Mapping[str, int]]:
    retained = missing = inserted = absent = 0
    for archive in archives:
        false_edges = possible_chronological_edges(archive) - archive.true_edges
        for mask_index in range(10):
            observed = mask_edges(archive, condition, mask_index)
            retained += len(observed & archive.true_edges)
            missing += len(archive.true_edges - observed)
            inserted += len(observed & false_edges)
            absent += len(false_edges - observed)
    q = (retained + 1) / (retained + missing + 2)
    r = (inserted + 1) / (inserted + absent + 2)
    return q, r, {
        "retained_true": retained, "missing_true": missing,
        "inserted_false": inserted, "absent_false": absent,
    }


def clue(archive: LiberoArchive, node: str) -> int:
    source_lesson = str(archive.memories[archive.source_id]["lesson"])
    return int(token_jaccard(source_lesson, str(archive.memories[node]["lesson"])) >= 0.20)


def content_rates(
    archives: Sequence[LiberoArchive], held_out: str
) -> Tuple[float, float, Mapping[str, int]]:
    tp = fn = fp = tn = 0
    for archive in archives:
        if archive.archive_id == held_out:
            continue
        for branch in archive.branch_ids:
            for node in branch:
                value = clue(archive, node)
                affected = node in archive.affected_ids
                tp += int(affected and value)
                fn += int(affected and not value)
                fp += int(not affected and value)
                tn += int(not affected and not value)
    sensitivity = (tp + 1) / (tp + fn + 2)
    false_positive_rate = (fp + 1) / (fp + tn + 2)
    return sensitivity, false_positive_rate, {"tp": tp, "fn": fn, "fp": fp, "tn": tn}


def discovery_case(archive: LiberoArchive, edges: Iterable[Tuple[str, str]]) -> DiscoveryCase:
    parents: Dict[str, list[str]] = {node: [] for node in archive.memories}
    for parent, child in edges:
        parents[child].append(parent)
    observable = tuple(
        ObservableMemory(
            memory_id=node,
            content=str(archive.memories[node]["lesson"]),
            created_at=archive.created_at[node],
            parent_memory_ids=tuple(sorted(parents[node])),
            origin_case_id="memory-libero-v0.2",
            exposed_memory_ids=(),
            formation_context=archive.task_languages[node],
        )
        for node in sorted(archive.memories, key=archive.created_at.get)
    )
    case = DiscoveryCase(
        archive.archive_id, archive.source_id, observable, archive.affected_ids
    )
    case.validate()
    return case


def branch_belief(
    archive: LiberoArchive, edges: Iterable[Tuple[str, str]],
    q: float, r: float, sensitivity: float, false_positive_rate: float,
) -> FiniteCascadeBelief:
    observed = set(edges)
    log_weights = []
    for world_index, branch in enumerate(archive.branch_ids):
        log_weight = -math.log(len(archive.branch_ids))
        for candidate_index, candidate in enumerate(archive.branch_ids):
            edge_seen = (archive.source_id, candidate[0]) in observed
            edge_probability = q if candidate_index == world_index else r
            log_weight += math.log(edge_probability if edge_seen else 1 - edge_probability)
            for node in candidate:
                probability = sensitivity if candidate_index == world_index else false_positive_rate
                log_weight += math.log(probability if clue(archive, node) else 1 - probability)
        log_weights.append(log_weight)
    maximum = max(log_weights)
    weights = [math.exp(value - maximum) for value in log_weights]
    total = sum(weights)
    worlds = tuple(
        LatentWorld(f"branch_{index}", frozenset(branch), weights[index] / total)
        for index, branch in enumerate(archive.branch_ids)
    )
    return FiniteCascadeBelief(
        tuple(node for branch in archive.branch_ids for node in branch), worlds
    )


def graph_ranking(archive: LiberoArchive, edges: Iterable[Tuple[str, str]]) -> list[str]:
    children: Dict[str, list[str]] = {}
    for parent, child in edges:
        children.setdefault(parent, []).append(child)
    distance = {archive.source_id: 0}
    queue = [archive.source_id]
    while queue:
        parent = queue.pop(0)
        for child in sorted(children.get(parent, [])):
            if child not in distance:
                distance[child] = distance[parent] + 1
                queue.append(child)
    candidates = [node for branch in archive.branch_ids for node in branch]
    return sorted(candidates, key=lambda node: (node not in distance, distance.get(node, 10**9), node))


def content_ranking(archive: LiberoArchive) -> list[str]:
    source = str(archive.memories[archive.source_id]["lesson"])
    candidates = [node for branch in archive.branch_ids for node in branch]
    return sorted(
        candidates,
        key=lambda node: (-clue(archive, node), -token_jaccard(source, str(archive.memories[node]["lesson"])), node),
    )


def random_ranking(archive: LiberoArchive, condition: str, mask_index: int) -> list[str]:
    candidates = [node for branch in archive.branch_ids for node in branch]
    random.Random(_seed(PROTOCOL, archive.archive_id, condition, mask_index, "random")).shuffle(candidates)
    return candidates


def evaluate_method(
    *, archive: LiberoArchive, case: DiscoveryCase, edges: frozenset[Tuple[str, str]],
    condition: str, mask_index: int, budget: int, method: str,
    calibrator: LogisticCalibrator, sensitivity: float, false_positive_rate: float,
    q: float, r: float,
) -> Mapping[str, object]:
    if method == "random":
        replayed = random_ranking(archive, condition, mask_index)[:budget]
    elif method == "content":
        replayed = content_ranking(archive)[:budget]
    elif method == "graph_reachability":
        replayed = graph_ranking(archive, edges)[:budget]
    elif method == "acis_risk_v1":
        replayed = adaptive_three_signal_replay(
            case, budget, "acis_risk", calibrator, seed=42
        )["replayed_ids"]
    elif method in {"graph_as_truth", "scacd_up_point"}:
        belief = branch_belief(
            archive, edges,
            0.99 if method == "graph_as_truth" else q,
            0.01 if method == "graph_as_truth" else r,
            sensitivity, false_positive_rate,
        )
        replayed = list(run_belief_policy(belief, 0, budget, horizon=1).replayed_ids)
    elif method == "full_replay":
        # Costed reference: it always spends the full 12 replays rather than
        # receiving privileged branch ordering at a smaller nominal budget.
        replayed = [node for branch in archive.branch_ids for node in branch]
    else:
        raise ValueError(f"unknown method: {method}")
    repaired = sorted(set(replayed) & archive.affected_ids)
    latest = max(archive.affected_ids, key=archive.created_at.get)
    selected_record = archive.counterfactuals[latest] if latest in repaired else archive.memories[latest]
    robot_success = selected_record["recommended_policy_id"] == archive.native_policy_id
    return {
        "replayed_ids": list(replayed), "repaired_ids": repaired,
        "replay_cost": len(replayed),
        "discoveries": len(repaired), "recall": len(repaired) / 3.0,
        "repair_precision": 1.0, "robot_success": bool(robot_success),
    }
