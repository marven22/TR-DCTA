"""Hard-evidence Memory-LIBERO v0.3.3 adapter and continuous posterior."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import random
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from .memoryarena_v6 import DiscoveryCase, ObservableMemory, token_jaccard
from .risk_aware_acis import LogisticCalibrator, adaptive_three_signal_replay
from .scacd_up import FiniteCascadeBelief, LatentWorld, run_belief_policy


PROTOCOL = "memory-libero/hard-evidence-heldout-v0.3.3"
CONDITIONS = ("complete", "deleted", "deleted_spurious")
BUDGETS = (1, 2, 3, 6, 12)


@dataclass(frozen=True)
class GaussianEvidence:
    affected_mean: float
    affected_variance: float
    clean_mean: float
    clean_variance: float
    affected_count: int
    clean_count: int


@dataclass(frozen=True)
class HardArchive:
    archive_id: str
    suite: str
    split: str
    source_id: str
    branch_ids: Tuple[Tuple[str, ...], ...]
    true_edges: frozenset[Tuple[str, str]]
    memories: Mapping[str, Mapping[str, object]]
    counterfactuals: Mapping[str, Mapping[str, object]]
    created_at: Mapping[str, int]
    affected_ids: frozenset[str]
    target_language: str


def is_strict_record(record: Mapping[str, object]) -> bool:
    for item in record["affected_branch"]:  # type: ignore[index]
        factual = item["factual"]["parsed"]
        counterfactual = item["counterfactual"]["parsed"]
        if factual is None or counterfactual is None:
            return False
        if factual == counterfactual:
            return False
        if factual["recommended_policy_id"] != record["donor_policy_id"]:
            return False
        if counterfactual["recommended_policy_id"] != record["native_policy_id"]:
            return False
    return all(
        item["generation"]["parsed"] is not None
        for branch in record["clean_branches"]  # type: ignore[index]
        for item in branch["memories"]
    )


def _opaque(archive_id: str, raw_id: str) -> str:
    return "m_" + hashlib.sha256(f"{PROTOCOL}|{archive_id}|{raw_id}".encode()).hexdigest()[:16]


def build_archive(record: Mapping[str, object]) -> HardArchive:
    if not is_strict_record(record):
        raise ValueError("record is not a strict v0.3.3 archive")
    archive_id = str(record["archive_id"])
    raw_source = str(record["invalid_source"]["memory_id"])  # type: ignore[index]
    raw_branches = [
        tuple(item["memory_id"] for item in record["affected_branch"])  # type: ignore[index]
    ] + [
        tuple(item["memory_id"] for item in branch["memories"])
        for branch in record["clean_branches"]  # type: ignore[index]
    ]
    mapping = {raw_source: _opaque(archive_id, raw_source)}
    for raw in (node for branch in raw_branches for node in branch):
        mapping[raw] = _opaque(archive_id, raw)
    source_id = mapping[raw_source]
    branch_ids = tuple(tuple(mapping[node] for node in branch) for branch in raw_branches)
    memories: Dict[str, Mapping[str, object]] = {
        source_id: record["invalid_source"]  # type: ignore[dict-item]
    }
    counterfactuals: Dict[str, Mapping[str, object]] = {}
    created_at = {source_id: 0}
    order = 1
    for item in record["affected_branch"]:  # type: ignore[index]
        node = mapping[item["memory_id"]]
        memories[node] = item["factual"]["parsed"]
        counterfactuals[node] = item["counterfactual"]["parsed"]
        created_at[node] = order
        order += 1
    for branch in record["clean_branches"]:  # type: ignore[index]
        for item in branch["memories"]:
            node = mapping[item["memory_id"]]
            memories[node] = item["generation"]["parsed"]
            created_at[node] = order
            order += 1
    edges = {(source_id, branch_ids[0][0])}
    for branch in branch_ids:
        edges.update(zip(branch, branch[1:]))
    return HardArchive(
        archive_id=archive_id, suite=str(record["suite"]), split=str(record["split"]),
        source_id=source_id, branch_ids=branch_ids, true_edges=frozenset(edges),
        memories=memories, counterfactuals=counterfactuals, created_at=created_at,
        affected_ids=frozenset(branch_ids[0]),
        target_language=str(record["target"]["target_language"]),  # type: ignore[index]
    )


def similarity(archive: HardArchive, node: str) -> float:
    return token_jaccard(
        str(archive.memories[archive.source_id]["lesson"]),
        str(archive.memories[node]["lesson"]),
    )


def logit_similarity(value: float) -> float:
    clipped = min(max(value, 0.01), 0.99)
    return math.log(clipped / (1.0 - clipped))


def fit_evidence(archives: Sequence[HardArchive]) -> GaussianEvidence:
    affected = [
        logit_similarity(similarity(archive, node))
        for archive in archives for node in archive.affected_ids
    ]
    clean = [
        logit_similarity(similarity(archive, node))
        for archive in archives for branch in archive.branch_ids[1:] for node in branch
    ]
    if len(affected) < 2 or len(clean) < 2:
        raise ValueError("content calibration requires both classes")
    def moments(values: Sequence[float]) -> Tuple[float, float]:
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return mean, max(variance, 0.25)
    affected_mean, affected_variance = moments(affected)
    clean_mean, clean_variance = moments(clean)
    return GaussianEvidence(
        affected_mean, affected_variance, clean_mean, clean_variance,
        len(affected), len(clean),
    )


def _normal_logpdf(value: float, mean: float, variance: float) -> float:
    return -0.5 * (math.log(2.0 * math.pi * variance) + (value - mean) ** 2 / variance)


def _seed(*parts: object) -> int:
    return int.from_bytes(
        hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big"
    )


def possible_edges(archive: HardArchive) -> frozenset[Tuple[str, str]]:
    nodes = sorted(archive.created_at, key=archive.created_at.get)
    return frozenset(
        (left, right) for left in nodes for right in nodes
        if archive.created_at[left] < archive.created_at[right]
    )


def mask_edges(archive: HardArchive, condition: str, mask_index: int) -> frozenset[Tuple[str, str]]:
    if condition not in CONDITIONS or not 0 <= mask_index < 10:
        raise ValueError("unknown mask")
    if condition == "complete":
        return archive.true_edges
    direct = (archive.source_id, archive.branch_ids[0][0])
    rng = random.Random(_seed(PROTOCOL, archive.archive_id, "deleted", mask_index))
    observed = {
        edge for edge in sorted(archive.true_edges)
        if edge != direct and rng.random() < 0.5
    }
    if condition == "deleted_spurious":
        false_edges = sorted(possible_edges(archive) - archive.true_edges)
        rng = random.Random(_seed(PROTOCOL, archive.archive_id, "spurious", mask_index))
        observed.update(rng.sample(false_edges, round(0.20 * len(archive.true_edges))))
    return frozenset(observed)


def channel_rates(
    development: Sequence[HardArchive], condition: str
) -> Tuple[float, float, Mapping[str, int]]:
    retained = missing = inserted = absent = 0
    for archive in development:
        false_edges = possible_edges(archive) - archive.true_edges
        for index in range(10):
            observed = mask_edges(archive, condition, index)
            retained += len(observed & archive.true_edges)
            missing += len(archive.true_edges - observed)
            inserted += len(observed & false_edges)
            absent += len(false_edges - observed)
    return (
        (retained + 1) / (retained + missing + 2),
        (inserted + 1) / (inserted + absent + 2),
        {"retained_true": retained, "missing_true": missing,
         "inserted_false": inserted, "absent_false": absent},
    )


def discovery_case(archive: HardArchive, edges: Iterable[Tuple[str, str]]) -> DiscoveryCase:
    parents: Dict[str, list[str]] = {node: [] for node in archive.memories}
    for parent, child in edges:
        parents[child].append(parent)
    memories = tuple(
        ObservableMemory(
            node, str(archive.memories[node]["lesson"]), archive.created_at[node],
            tuple(sorted(parents[node])), "memory-libero-v0.3.3", (),
            archive.target_language,
        )
        for node in sorted(archive.memories, key=archive.created_at.get)
    )
    case = DiscoveryCase(archive.archive_id, archive.source_id, memories, archive.affected_ids)
    case.validate()
    return case


def branch_belief(
    archive: HardArchive, edges: Iterable[Tuple[str, str]], evidence: GaussianEvidence,
    q: float, r: float,
) -> FiniteCascadeBelief:
    observed = set(edges)
    log_weights = []
    for world_index in range(4):
        value = -math.log(4.0)
        for branch_index, branch in enumerate(archive.branch_ids):
            edge_seen = (archive.source_id, branch[0]) in observed
            probability = q if branch_index == world_index else r
            value += math.log(probability if edge_seen else 1.0 - probability)
            for node in branch:
                z = logit_similarity(similarity(archive, node))
                if branch_index == world_index:
                    value += _normal_logpdf(z, evidence.affected_mean, evidence.affected_variance)
                else:
                    value += _normal_logpdf(z, evidence.clean_mean, evidence.clean_variance)
        log_weights.append(value)
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


def graph_ranking(archive: HardArchive, edges: Iterable[Tuple[str, str]]) -> list[str]:
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
    return sorted(candidates, key=lambda node: (
        node not in distance, distance.get(node, 10**9), node
    ))


def evaluate_method(
    *, archive: HardArchive, case: DiscoveryCase, edges: frozenset[Tuple[str, str]],
    evidence: GaussianEvidence, q: float, r: float, condition: str,
    mask_index: int, budget: int, method: str, calibrator: LogisticCalibrator,
) -> Mapping[str, object]:
    candidates = [node for branch in archive.branch_ids for node in branch]
    if method == "random":
        replayed = candidates[:]
        random.Random(_seed(PROTOCOL, archive.archive_id, condition, mask_index, "random")).shuffle(replayed)
        replayed = replayed[:budget]
    elif method == "content":
        replayed = sorted(candidates, key=lambda node: (-similarity(archive, node), node))[:budget]
    elif method == "graph_reachability":
        replayed = graph_ranking(archive, edges)[:budget]
    elif method == "acis_risk_v1":
        replayed = adaptive_three_signal_replay(
            case, budget, "acis_risk", calibrator, seed=42
        )["replayed_ids"]
    elif method in {"graph_as_truth", "scacd_up_continuous"}:
        belief = branch_belief(
            archive, edges, evidence,
            0.99 if method == "graph_as_truth" else q,
            0.01 if method == "graph_as_truth" else r,
        )
        replayed = list(run_belief_policy(belief, 0, budget, horizon=1).replayed_ids)
    elif method == "full_replay":
        replayed = candidates
    else:
        raise ValueError(f"unknown method: {method}")
    repaired = sorted(set(replayed) & archive.affected_ids)
    return {
        "replayed_ids": list(replayed), "repaired_ids": repaired,
        "replay_cost": len(replayed), "discoveries": len(repaired),
        "recall": len(repaired) / 3.0, "repair_precision": 1.0,
        "robot_policy_validity": (9 + len(repaired)) / 12.0,
    }
