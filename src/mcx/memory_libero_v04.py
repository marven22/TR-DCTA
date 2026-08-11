"""Counterfactual cascade discovery for Memory-LIBERO v0.4."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import itertools
import json
import math
import random
import re
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from .memoryarena_v6 import DiscoveryCase, ObservableMemory, token_jaccard
from .risk_aware_acis import LogisticCalibrator, adaptive_three_signal_replay


PROTOCOL = "memory-libero/counterfactual-cascade-v0.4"
BUDGETS = (1, 2, 3, 6, 12)
REGIMES = (
    "memory_priority", "simulator_priority",
    "corroborated_override", "recovery",
)


@dataclass(frozen=True)
class GaussianEvidence:
    affected_mean: float
    affected_variance: float
    clean_mean: float
    clean_variance: float
    affected_count: int
    clean_count: int


@dataclass(frozen=True)
class V04Archive:
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
    policy_changed_ids: frozenset[str]
    content_changed_ids: frozenset[str]
    target_language: str


@dataclass(frozen=True)
class BranchModel:
    evidence: GaussianEvidence
    alpha: float
    beta: float


def _opaque(archive_id: str, raw_id: str) -> str:
    digest = hashlib.sha256(f"{PROTOCOL}|{archive_id}|{raw_id}".encode()).hexdigest()
    return "m_" + digest[:16]


def _canonical_text(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))


def _policy_success(record: Mapping[str, object], policy: object) -> bool:
    return bool(record["policy_success"].get(str(policy), False))  # type: ignore[union-attr]


def paired_prompt_invariant(item: Mapping[str, object]) -> bool:
    """Check that paired prompts differ only in retrieved, intervention-carried state."""
    try:
        factual = json.loads(str(item["factual"]["prompt"]).splitlines()[-1])  # type: ignore[index]
        counterfactual = json.loads(str(item["counterfactual"]["prompt"]).splitlines()[-1])  # type: ignore[index]
    except (KeyError, TypeError, json.JSONDecodeError):
        return False
    factual.pop("retrieved_memories", None)
    counterfactual.pop("retrieved_memories", None)
    return factual == counterfactual


def is_strict_record(record: Mapping[str, object]) -> bool:
    if tuple(record.get("regimes", ())) != REGIMES:
        return False
    if len(record.get("branches", ())) != 4:  # type: ignore[arg-type]
        return False
    for branch in record["branches"]:  # type: ignore[index]
        if len(branch["memories"]) != 3:
            return False
        for item in branch["memories"]:
            if not paired_prompt_invariant(item):
                return False
            factual = item["factual"].get("parsed")
            counterfactual = item["counterfactual"].get("parsed")
            if factual is None or counterfactual is None:
                return False
            if factual["recommended_policy_id"] not in record["policy_success"]:
                return False
            if counterfactual["recommended_policy_id"] not in record["policy_success"]:
                return False
    return True


def build_archive(record: Mapping[str, object]) -> V04Archive:
    if not is_strict_record(record):
        raise ValueError("record is not a strict v0.4 archive")
    archive_id = str(record["archive_id"])
    raw_source = str(record["invalid_source"]["memory_id"])  # type: ignore[index]
    raw_branches = tuple(
        tuple(str(item["memory_id"]) for item in branch["memories"])
        for branch in record["branches"]  # type: ignore[index]
    )
    mapping = {raw_source: _opaque(archive_id, raw_source)}
    for raw in itertools.chain.from_iterable(raw_branches):
        mapping[raw] = _opaque(archive_id, raw)
    source_id = mapping[raw_source]
    branches = tuple(tuple(mapping[node] for node in branch) for branch in raw_branches)
    memories: Dict[str, Mapping[str, object]] = {
        source_id: record["invalid_source"]  # type: ignore[dict-item]
    }
    counterfactuals: Dict[str, Mapping[str, object]] = {}
    created_at = {source_id: 0}
    affected, policy_changed, content_changed = set(), set(), set()
    order = 1
    for raw_branch, opaque_branch, branch in zip(
        raw_branches, branches, record["branches"]  # type: ignore[index]
    ):
        del raw_branch
        for node, item in zip(opaque_branch, branch["memories"]):
            factual = item["factual"]["parsed"]
            counterfactual = item["counterfactual"]["parsed"]
            memories[node] = factual
            counterfactuals[node] = counterfactual
            created_at[node] = order
            order += 1
            factual_policy = factual["recommended_policy_id"]
            counterfactual_policy = counterfactual["recommended_policy_id"]
            if factual_policy != counterfactual_policy:
                policy_changed.add(node)
            if _canonical_text(factual["lesson"]) != _canonical_text(counterfactual["lesson"]):
                content_changed.add(node)
            if _policy_success(record, factual_policy) != _policy_success(record, counterfactual_policy):
                affected.add(node)
    edges = set()
    for branch in branches:
        edges.add((source_id, branch[0]))
        edges.update(zip(branch, branch[1:]))
    return V04Archive(
        archive_id=archive_id, suite=str(record["suite"]), split=str(record["split"]),
        source_id=source_id, branch_ids=branches, true_edges=frozenset(edges),
        memories=memories, counterfactuals=counterfactuals, created_at=created_at,
        affected_ids=frozenset(affected), policy_changed_ids=frozenset(policy_changed),
        content_changed_ids=frozenset(content_changed),
        target_language=str(record["target"]["target_language"]),  # type: ignore[index]
    )


def similarity(archive: V04Archive, node: str) -> float:
    return token_jaccard(
        str(archive.memories[archive.source_id]["lesson"]),
        str(archive.memories[node]["lesson"]),
    )


def _logit(value: float) -> float:
    value = min(max(value, 0.01), 0.99)
    return math.log(value / (1.0 - value))


def _moments(values: Sequence[float]) -> Tuple[float, float]:
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return mean, max(variance, 0.25)


def fit_evidence(archives: Sequence[V04Archive]) -> GaussianEvidence:
    affected = [_logit(similarity(a, n)) for a in archives for n in a.affected_ids]
    clean = [
        _logit(similarity(a, n)) for a in archives
        for branch in a.branch_ids for n in branch if n not in a.affected_ids
    ]
    if len(affected) < 2 or len(clean) < 2:
        raise ValueError("v0.4 calibration requires at least two examples per class")
    am, av = _moments(affected)
    cm, cv = _moments(clean)
    return GaussianEvidence(am, av, cm, cv, len(affected), len(clean))


def _normal_logpdf(value: float, mean: float, variance: float) -> float:
    return -0.5 * (math.log(2.0 * math.pi * variance) + (value - mean) ** 2 / variance)


def fit_branch_model(archives: Sequence[V04Archive]) -> BranchModel:
    evidence = fit_evidence(archives)
    counts = [sum(node in a.affected_ids for node in branch)
              for a in archives for branch in a.branch_ids]
    best = None
    for alpha in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0):
        for beta in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0):
            score = sum(
                math.lgamma(alpha + count) + math.lgamma(beta + 3 - count)
                - math.lgamma(alpha + beta + 3)
                - (math.lgamma(alpha) + math.lgamma(beta) - math.lgamma(alpha + beta))
                for count in counts
            )
            candidate = (score, -alpha - beta, alpha, beta)
            if best is None or candidate > best:
                best = candidate
    return BranchModel(evidence, best[2], best[3])  # type: ignore[index]


def _branch_worlds(archive: V04Archive, branch: Tuple[str, ...], model: BranchModel):
    worlds = []
    for labels in itertools.product((0, 1), repeat=len(branch)):
        count = sum(labels)
        log_weight = (
            math.lgamma(model.alpha + count)
            + math.lgamma(model.beta + len(branch) - count)
            - math.lgamma(model.alpha + model.beta + len(branch))
            - (math.lgamma(model.alpha) + math.lgamma(model.beta)
               - math.lgamma(model.alpha + model.beta))
        )
        for node, label in zip(branch, labels):
            z = _logit(similarity(archive, node))
            ev = model.evidence
            log_weight += _normal_logpdf(
                z,
                ev.affected_mean if label else ev.clean_mean,
                ev.affected_variance if label else ev.clean_variance,
            )
        worlds.append((labels, log_weight))
    maximum = max(weight for _, weight in worlds)
    normalizer = sum(math.exp(weight - maximum) for _, weight in worlds)
    return {labels: math.exp(weight - maximum) / normalizer for labels, weight in worlds}


def initial_probabilities(archive: V04Archive, model: BranchModel) -> Dict[str, float]:
    result = {}
    for branch in archive.branch_ids:
        worlds = _branch_worlds(archive, branch, model)
        for offset, node in enumerate(branch):
            result[node] = sum(weight for labels, weight in worlds.items() if labels[offset])
    return result


def individual_probabilities(archive: V04Archive, model: BranchModel) -> Dict[str, float]:
    """Content-only posterior using the fitted marginal affected prevalence."""
    prior = model.alpha / (model.alpha + model.beta)
    result = {}
    for node in itertools.chain.from_iterable(archive.branch_ids):
        z = _logit(similarity(archive, node))
        affected = math.log(prior) + _normal_logpdf(
            z, model.evidence.affected_mean, model.evidence.affected_variance
        )
        clean = math.log(1.0 - prior) + _normal_logpdf(
            z, model.evidence.clean_mean, model.evidence.clean_variance
        )
        maximum = max(affected, clean)
        pa, pc = math.exp(affected - maximum), math.exp(clean - maximum)
        result[node] = pa / (pa + pc)
    return result


def adaptive_branch_replay(
    archive: V04Archive, model: BranchModel, budget: int
) -> Tuple[list[str], Dict[str, float]]:
    states = {branch: _branch_worlds(archive, branch, model) for branch in archive.branch_ids}
    replayed: list[str] = []
    before: Dict[str, float] = {}
    while len(replayed) < min(budget, 12):
        probabilities = {}
        for branch, worlds in states.items():
            for offset, node in enumerate(branch):
                if node not in replayed:
                    probabilities[node] = sum(
                        weight for labels, weight in worlds.items() if labels[offset]
                    )
        chosen = min(probabilities, key=lambda node: (-probabilities[node], node))
        before[chosen] = probabilities[chosen]
        replayed.append(chosen)
        branch = next(branch for branch in archive.branch_ids if chosen in branch)
        offset = branch.index(chosen)
        label = int(chosen in archive.affected_ids)
        kept = {labels: weight for labels, weight in states[branch].items()
                if labels[offset] == label}
        total = sum(kept.values())
        states[branch] = {labels: weight / total for labels, weight in kept.items()}
    return replayed, before


def discovery_case(archive: V04Archive) -> DiscoveryCase:
    parents: Dict[str, list[str]] = {node: [] for node in archive.memories}
    for parent, child in archive.true_edges:
        parents[child].append(parent)
    memories = tuple(
        ObservableMemory(
            memory_id=node, content=str(archive.memories[node]["lesson"]),
            created_at=archive.created_at[node],
            parent_memory_ids=tuple(sorted(parents[node])),
            origin_case_id="memory-libero-v0.4",
            exposed_memory_ids=(), formation_context=archive.target_language,
        )
        for node in sorted(archive.memories, key=archive.created_at.get)
    )
    case = DiscoveryCase(archive.archive_id, archive.source_id, memories, archive.affected_ids)
    case.validate()
    return case


def _seed(*parts: object) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def graph_ranking(archive: V04Archive) -> list[str]:
    distance = {archive.source_id: 0}
    children: Dict[str, list[str]] = {}
    for parent, child in archive.true_edges:
        children.setdefault(parent, []).append(child)
    queue = [archive.source_id]
    while queue:
        parent = queue.pop(0)
        for child in sorted(children.get(parent, ())):
            if child not in distance:
                distance[child] = distance[parent] + 1
                queue.append(child)
    candidates = list(itertools.chain.from_iterable(archive.branch_ids))
    return sorted(candidates, key=lambda node: (distance.get(node, 99), node))


def evaluate_method(
    archive: V04Archive, model: BranchModel, calibrator: LogisticCalibrator,
    method: str, budget: int,
) -> Mapping[str, object]:
    candidates = list(itertools.chain.from_iterable(archive.branch_ids))
    probabilities = initial_probabilities(archive, model)
    individual = individual_probabilities(archive, model)
    score_log: Mapping[str, float] = {}
    if method == "random":
        replayed = candidates[:]
        random.Random(_seed(PROTOCOL, archive.archive_id, budget)).shuffle(replayed)
        replayed = replayed[:budget]
    elif method == "raw_content":
        replayed = sorted(candidates, key=lambda n: (-similarity(archive, n), n))[:budget]
    elif method == "graph_reachability":
        replayed = graph_ranking(archive)[:budget]
    elif method == "acis_risk_v1":
        replayed = adaptive_three_signal_replay(
            discovery_case(archive), budget, "acis_risk", calibrator, seed=42
        )["replayed_ids"]
    elif method == "calibrated_individual":
        replayed = sorted(candidates, key=lambda n: (-individual[n], n))[:budget]
    elif method == "static_branch_posterior":
        replayed = sorted(candidates, key=lambda n: (-probabilities[n], n))[:budget]
    elif method == "adaptive_branch_posterior":
        replayed, score_log = adaptive_branch_replay(archive, model, budget)
    elif method == "full_replay":
        replayed = candidates
    elif method == "causal_oracle":
        replayed = sorted(archive.affected_ids)[:budget]
        replayed += [n for n in sorted(candidates) if n not in archive.affected_ids][
            :max(0, budget - len(replayed))
        ]
    else:
        raise ValueError(f"unknown v0.4 method: {method}")
    hits = sorted(set(replayed) & archive.affected_ids)
    total = len(archive.affected_ids)
    remaining = total - len(hits)
    return {
        "replayed_ids": list(replayed), "confirmed_affected_ids": hits,
        "discoveries": len(hits), "replay_cost": len(replayed),
        "recall": len(hits) / total if total else 1.0,
        "audit_yield": len(hits) / len(replayed) if replayed else 0.0,
        "residual_invalid_exposure": remaining / 12.0,
        "initial_brier": sum(
            ((individual[n] if method == "calibrated_individual" else probabilities[n])
             - int(n in archive.affected_ids)) ** 2 for n in candidates
        ) / 12.0,
        "score_log": score_log,
    }
