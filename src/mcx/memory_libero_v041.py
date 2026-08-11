"""Irregular-DAG Memory-LIBERO v0.4.1 adapter and frontier policies."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import itertools
import math
import random
from typing import Dict, Mapping, Sequence, Tuple

from .memory_libero_v04 import (
    V04Archive, build_archive as build_v04, paired_prompt_invariant,
)
from .memoryarena_v6 import DiscoveryCase, ObservableMemory, token_jaccard
from .risk_aware_acis import LogisticCalibrator, ThreeSignalIndex, adaptive_three_signal_replay


PROTOCOL = "memory-libero/counterfactual-cascade-v0.4.1"
BUDGETS = (2, 4, 6, 9, 18)
MOTIFS = (
    "deep_continuation", "recovery_continuation", "cross_branch_merge",
    "late_probe", "authoritative_bridge", "post_bridge_revival",
)


@dataclass(frozen=True)
class FrontierParameters:
    gamma: float
    decay: float
    neutral_weight: float
    delta_threshold: float


@dataclass(frozen=True)
class V041Archive:
    archive_id: str
    suite: str
    split: str
    source_id: str
    candidate_ids: Tuple[str, ...]
    true_edges: frozenset[Tuple[str, str]]
    memories: Mapping[str, Mapping[str, object]]
    counterfactuals: Mapping[str, Mapping[str, object]]
    created_at: Mapping[str, int]
    affected_ids: frozenset[str]
    direct_gateways: frozenset[str]
    target_language: str
    base: V04Archive


def _opaque(archive_id: str, raw_id: str) -> str:
    return "m_" + hashlib.sha256(f"{PROTOCOL}|{archive_id}|{raw_id}".encode()).hexdigest()[:16]


def is_strict_record(record: Mapping[str, object]) -> bool:
    extensions = record.get("extensions", ())
    if len(extensions) != 6 or tuple(x.get("motif") for x in extensions) != MOTIFS:  # type: ignore[arg-type]
        return False
    policy_success = record["base_archive"]["policy_success"]  # type: ignore[index]
    for item in extensions:  # type: ignore[assignment]
        if not paired_prompt_invariant(item):
            return False
        for world in ("factual", "counterfactual"):
            parsed = item[world].get("parsed")
            if parsed is None or parsed["recommended_policy_id"] not in policy_success:
                return False
    return True


def build_archive(record: Mapping[str, object]) -> V041Archive:
    if not is_strict_record(record):
        raise ValueError("record is not a strict v0.4.1 archive")
    base_record = record["base_archive"]  # type: ignore[assignment]
    base = build_v04(base_record)
    archive_id = str(record["archive_id"])
    raw_to_old = {str(base_record["invalid_source"]["memory_id"]): base.source_id}
    for raw_branch, opaque_branch in zip(base_record["branches"], base.branch_ids):
        for raw, opaque in zip(raw_branch["memories"], opaque_branch):
            raw_to_old[str(raw["memory_id"])] = opaque
    # Re-opaque every node under the v0.4.1 protocol to avoid carrying positional hashes.
    raw_ids = list(raw_to_old)
    raw_ids.extend(str(x["memory_id"]) for x in record["extensions"])  # type: ignore[index]
    mapping = {raw: _opaque(archive_id, raw) for raw in raw_ids}
    source_raw = str(base_record["invalid_source"]["memory_id"])
    source_id = mapping[source_raw]
    memories, counterfactuals, created_at = {}, {}, {}
    # Copy base factual/counterfactual state through raw IDs.
    inverse_old = {opaque: raw for raw, opaque in raw_to_old.items()}
    for old, memory in base.memories.items():
        raw = inverse_old[old]
        memories[mapping[raw]] = memory
        created_at[mapping[raw]] = base.created_at[old]
        if old in base.counterfactuals:
            counterfactuals[mapping[raw]] = base.counterfactuals[old]
    affected = {mapping[inverse_old[node]] for node in base.affected_ids}
    edges = {(mapping[inverse_old[p]], mapping[inverse_old[c]]) for p, c in base.true_edges}
    order = max(created_at.values()) + 1
    policy_success = base_record["policy_success"]
    for item in record["extensions"]:  # type: ignore[index]
        raw = str(item["memory_id"]); node = mapping[raw]
        factual, counterfactual = item["factual"]["parsed"], item["counterfactual"]["parsed"]
        memories[node] = factual; counterfactuals[node] = counterfactual; created_at[node] = order
        order += 1
        for parent in item["parent_memory_ids"]:
            # Independent simulator-grounded support is exogenous evidence,
            # not an auditable persistent-memory node in this archive.
            if str(parent) in mapping:
                edges.add((mapping[str(parent)], node))
        if bool(policy_success.get(factual["recommended_policy_id"], False)) != bool(
            policy_success.get(counterfactual["recommended_policy_id"], False)
        ):
            affected.add(node)
    candidates = tuple(node for node in sorted(created_at, key=created_at.get) if node != source_id)
    gateways = frozenset(child for parent, child in edges if parent == source_id)
    return V041Archive(
        archive_id, str(record["suite"]), str(record["split"]), source_id,
        candidates, frozenset(edges), memories, counterfactuals, created_at,
        frozenset(affected), gateways, str(base_record["target"]["target_language"]), base,
    )


def counterfactual_delta(archive: V041Archive, node: str) -> float:
    if node not in archive.counterfactuals:
        return 0.0
    return 1.0 - token_jaccard(
        str(archive.memories[node]["lesson"]),
        str(archive.counterfactuals[node]["lesson"]),
    )


def discovery_case(archive: V041Archive) -> DiscoveryCase:
    parents: Dict[str, list[str]] = {node: [] for node in archive.memories}
    for parent, child in archive.true_edges:
        parents[child].append(parent)
    memories = tuple(
        ObservableMemory(
            node, str(archive.memories[node]["lesson"]), archive.created_at[node],
            tuple(sorted(parents[node])), "memory-libero-v0.4.1", (), archive.target_language,
        )
        for node in sorted(archive.memories, key=archive.created_at.get)
    )
    case = DiscoveryCase(archive.archive_id, archive.source_id, memories, archive.affected_ids)
    case.validate()
    return case


def _distances(archive: V041Archive) -> Dict[Tuple[str, str], int]:
    children: Dict[str, list[str]] = {}
    for parent, child in archive.true_edges:
        children.setdefault(parent, []).append(child)
    result = {}
    for start in archive.memories:
        queue = [(start, 0)]; seen = {start}
        while queue:
            node, depth = queue.pop(0)
            for child in children.get(node, ()):
                if child not in seen:
                    seen.add(child); result[(start, child)] = depth + 1
                    queue.append((child, depth + 1))
    return result


def static_probabilities(archive: V041Archive, calibrator: LogisticCalibrator):
    case = discovery_case(archive); index = ThreeSignalIndex(case)
    return {node: calibrator.probability(index.signals(node, {archive.source_id}))
            for node in archive.candidate_ids}


def frontier_replay(
    archive: V041Archive, calibrator: LogisticCalibrator, budget: int,
    parameters: FrontierParameters,
):
    base = static_probabilities(archive, calibrator)
    distances = _distances(archive)
    replayed = []; observed = {}
    while len(replayed) < min(budget, len(archive.candidate_ids)):
        scores = {}
        for node in archive.candidate_ids:
            if node in replayed:
                continue
            logit = math.log(max(base[node], 1e-9) / max(1.0 - base[node], 1e-9))
            for anchor, signal in observed.items():
                distance = distances.get((anchor, node))
                if distance:
                    logit += parameters.gamma * signal * parameters.decay ** (distance - 1)
            scores[node] = logit
        chosen = min(scores, key=lambda node: (-scores[node], node))
        replayed.append(chosen)
        if chosen in archive.affected_ids:
            signal = 1.0
        else:
            delta = counterfactual_delta(archive, chosen)
            scaled = max(0.0, (delta - parameters.delta_threshold)
                         / max(1e-9, 1.0 - parameters.delta_threshold))
            signal = parameters.neutral_weight * scaled
        observed[chosen] = signal
    return replayed


def fit_frontier_parameters(
    archives: Sequence[V041Archive], calibrator: LogisticCalibrator, *, neutral: bool,
) -> FrontierParameters:
    best = None
    for gamma, decay, weight, threshold in itertools.product(
        (0.5, 1.0, 2.0, 4.0), (0.4, 0.7, 1.0),
        ((0.0,) if not neutral else (0.25, 0.5, 1.0)),
        ((1.0,) if not neutral else (0.25, 0.5, 0.75)),
    ):
        params = FrontierParameters(gamma, decay, weight, threshold)
        recalls = []
        for archive in archives:
            if not archive.affected_ids:
                continue
            replayed = frontier_replay(archive, calibrator, 4, params)
            recalls.append(len(set(replayed) & archive.affected_ids) / len(archive.affected_ids))
        value = sum(recalls) / len(recalls)
        # Deterministic simplicity tie-break: smaller boost, faster decay, less neutral use.
        candidate = (value, -gamma, -decay, -weight, threshold, params)
        if best is None or candidate[:-1] > best[:-1]:
            best = candidate
    return best[-1]  # type: ignore[index]


def _seed(*parts):
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def graph_ranking(archive: V041Archive):
    distance = {archive.source_id: 0}; queue = [archive.source_id]
    children: Dict[str, list[str]] = {}
    for parent, child in archive.true_edges:
        children.setdefault(parent, []).append(child)
    while queue:
        parent = queue.pop(0)
        for child in sorted(children.get(parent, ())):
            if child not in distance:
                distance[child] = distance[parent] + 1; queue.append(child)
    return sorted(archive.candidate_ids, key=lambda n: (distance.get(n, 99), n))


def evaluate_method(archive, calibrator, method, budget, positive_params, delta_params):
    case = discovery_case(archive); static = static_probabilities(archive, calibrator)
    if method == "random":
        replayed = list(archive.candidate_ids); random.Random(_seed(PROTOCOL, archive.archive_id, budget)).shuffle(replayed); replayed = replayed[:budget]
    elif method == "raw_content":
        source = str(archive.memories[archive.source_id]["lesson"])
        replayed = sorted(archive.candidate_ids, key=lambda n: (-token_jaccard(source, str(archive.memories[n]["lesson"])), n))[:budget]
    elif method == "graph_reachability": replayed = graph_ranking(archive)[:budget]
    elif method == "static_source_probability": replayed = sorted(archive.candidate_ids, key=lambda n: (-static[n], n))[:budget]
    elif method in ("acis_probability", "acis_risk"):
        replayed = adaptive_three_signal_replay(case, budget, method, calibrator, seed=42)["replayed_ids"]
    elif method == "positive_frontier": replayed = frontier_replay(archive, calibrator, budget, positive_params)
    elif method == "delta_frontier": replayed = frontier_replay(archive, calibrator, budget, delta_params)
    elif method == "causal_oracle":
        replayed = sorted(archive.affected_ids)[:budget]
        replayed += [n for n in archive.candidate_ids if n not in archive.affected_ids][:max(0, budget-len(replayed))]
    elif method == "full_replay": replayed = list(archive.candidate_ids)
    else: raise ValueError(method)
    hits = set(replayed) & archive.affected_ids
    deep = archive.affected_ids - archive.direct_gateways
    return {
        "replayed_ids": replayed, "discoveries": len(hits),
        "recall": len(hits)/len(archive.affected_ids) if archive.affected_ids else 1.0,
        "deep_recall": len(hits & deep)/len(deep) if deep else 1.0,
        "audit_yield": len(hits)/len(replayed),
        "residual_invalid_exposure": (len(archive.affected_ids)-len(hits))/18.0,
    }
