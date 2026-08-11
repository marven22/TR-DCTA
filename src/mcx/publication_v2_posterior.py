"""Scalable latent-contamination posterior for multi-origin Prob-DCTA."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import random
from typing import Mapping, Sequence

from .prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld
from .publication_v2_source import SourceEstimator, fit_source_estimator, memory_text, similarity


@dataclass(frozen=True)
class CascadeParameters:
    contamination: SourceEstimator
    emission: SourceEstimator
    latent_edge_probability: float = 0.5


@dataclass(frozen=True)
class ImportanceSamplingDiagnostics:
    effective_sample_size: float
    maximum_importance_weight: float
    minimum_importance_weight: float
    sampled_source_counts: Mapping[str, int]
    target_source_prior: Mapping[str, float]
    proposal_source_prior: Mapping[str, float]


def _parents(edges: Sequence[Sequence[str]], candidates: Sequence[str]) -> dict[str, list[str]]:
    values = {node: [] for node in candidates}
    for left, right in edges:
        if right in values:
            values[right].append(str(left))
    return values


def contamination_features(
    archive: Mapping[str, object], node: str, active_parents: Sequence[str],
    all_parents: Sequence[str], source: str,
) -> tuple[float, ...]:
    memories = archive["memories"]
    child = memory_text(memories[node])
    similarities = [similarity(memory_text(memories[parent]), child)
                    for parent in active_parents]
    return (
        float(source in active_parents), float(len(all_parents) > 1),
        max(similarities), float(len(active_parents) - 1),
        similarity(child, archive["target_language"]),
    )


def emission_features(
    archive: Mapping[str, object], node: str, source: str,
    active_parents: Sequence[str], all_parents: Sequence[str],
) -> tuple[float, ...]:
    memories = archive["memories"]
    child = memory_text(memories[node]); source_text = memory_text(memories[source])
    parent_similarity = max(similarity(memory_text(memories[parent]), child)
                            for parent in active_parents)
    candidate_times = [int(archive["created_at"][value]) for value in archive["candidate_ids"]]
    minimum, maximum = min(candidate_times), max(candidate_times)
    depth = (int(archive["created_at"][node]) - minimum) / max(maximum - minimum, 1)
    return (
        similarity(child, archive["target_language"]), similarity(source_text, child),
        parent_similarity, depth, float(len(all_parents) > 1),
        min(len(memories[node].get("cited_memory_ids", ())), 3) / 3.0,
    )


def fit_cascade_parameters(
    public_archives: Sequence[Mapping[str, object]],
    private_by_id: Mapping[str, Mapping[str, object]],
    *, l2: float = 1.0,
) -> tuple[CascadeParameters, dict[str, int]]:
    contamination_rows, emission_rows = [], []
    for archive in public_archives:
        truth = private_by_id[str(archive["archive_id"])]
        source = str(truth["active_source_id"])
        contaminated = set(map(str, truth["contaminated_ids"]))
        affected = set(map(str, truth["affected_ids"]))
        candidates = sorted(map(str, archive["candidate_ids"]),
                            key=lambda node: int(archive["created_at"][node]))
        parents = _parents(truth["true_formation_edges"], candidates)
        seen_contaminated: set[str] = set()
        for node in candidates:
            active = [parent for parent in parents[node]
                      if parent == source or parent in seen_contaminated]
            label = int(node in contaminated)
            if active:
                contamination_rows.append((contamination_features(
                    archive, node, active, parents[node], source
                ), label))
            elif label:
                raise ValueError(f"contamination without causal parent: {archive['archive_id']} {node}")
            if label:
                seen_contaminated.add(node)
                emission_rows.append((emission_features(
                    archive, node, source, active, parents[node]
                ), int(node in affected)))
            elif node in affected:
                raise ValueError("harmful node is not contaminated")
    parameters = CascadeParameters(
        fit_source_estimator(contamination_rows, l2=l2),
        fit_source_estimator(emission_rows, l2=l2), .5,
    )
    return parameters, {"contamination_rows": len(contamination_rows),
                        "emission_rows": len(emission_rows)}


def estimator_from_json(value: Mapping[str, object]) -> SourceEstimator:
    return SourceEstimator(tuple(map(float, value["means"])),
                           tuple(map(float, value["scales"])),
                           tuple(map(float, value["coefficients"])))


def cascade_from_json(value: Mapping[str, object]) -> CascadeParameters:
    return CascadeParameters(
        estimator_from_json(value["contamination"]),
        estimator_from_json(value["emission"]),
        float(value["latent_edge_probability"]),
    )


def sample_posterior(
    archive: Mapping[str, object], source_prior: Mapping[str, float],
    parameters: CascadeParameters, particles: int, seed: int,
) -> LatentSourcePosterior:
    if particles <= 0:
        raise ValueError("particle count must be positive")
    sources = tuple(map(str, archive["source_ids"])); candidates = tuple(sorted(
        map(str, archive["candidate_ids"]), key=lambda node: int(archive["created_at"][node])
    ))
    if set(source_prior) != set(sources) or not math.isclose(sum(source_prior.values()), 1.0, abs_tol=1e-8):
        raise ValueError("invalid source prior")
    rng = random.Random(seed)
    cumulative, total = [], 0.0
    for source in sources:
        total += float(source_prior[source]); cumulative.append((total, source))
    observed = [list(map(str, edge)) for edge in archive["observed_formation_edges"]]
    latent = [list(map(str, edge)) for edge in archive["latent_edge_candidates"]]
    counts: dict[tuple[str, frozenset[str]], int] = {}
    for _ in range(particles):
        draw = rng.random(); source = next(value for threshold, value in cumulative if draw <= threshold)
        edges = observed + [edge for edge in latent if rng.random() < parameters.latent_edge_probability]
        parents = _parents(edges, candidates)
        contaminated, affected = set(), set()
        for node in candidates:
            active = [parent for parent in parents[node]
                      if parent == source or parent in contaminated]
            if not active:
                continue
            probability = parameters.contamination.score(contamination_features(
                archive, node, active, parents[node], source
            ))
            if rng.random() >= probability:
                continue
            contaminated.add(node)
            harm_probability = parameters.emission.score(emission_features(
                archive, node, source, active, parents[node]
            ))
            if rng.random() < harm_probability:
                affected.add(node)
        key = (source, frozenset(affected)); counts[key] = counts.get(key, 0) + 1
    worlds = tuple(LatentSourceWorld(source, affected, count / particles)
                   for (source, affected), count in counts.items())
    return LatentSourcePosterior(candidates, sources, worlds).normalize()


def support_proposal(
    target_prior: Mapping[str, float], minimum_probability: float,
) -> dict[str, float]:
    """Add sampling support without redefining the target source belief."""
    sources = tuple(map(str, target_prior))
    if not sources or not 0.0 <= minimum_probability < 1.0 / len(sources):
        raise ValueError("invalid source-proposal floor")
    if any(float(target_prior[source]) < 0.0 for source in sources) or not math.isclose(
        sum(float(target_prior[source]) for source in sources), 1.0, abs_tol=1e-8
    ):
        raise ValueError("invalid target source prior")
    remaining = 1.0 - minimum_probability * len(sources)
    return {source: minimum_probability + remaining * float(target_prior[source])
            for source in sources}


def sample_importance_posterior(
    archive: Mapping[str, object], target_source_prior: Mapping[str, float],
    proposal_source_prior: Mapping[str, float], parameters: CascadeParameters,
    particles: int, seed: int,
) -> tuple[LatentSourcePosterior, ImportanceSamplingDiagnostics]:
    """Sample with a support-safe proposal and recover the target posterior.

    The proposal differs only in the source marginal.  Conditional edge,
    contamination, and emission draws are unchanged, so each particle's
    importance ratio is exactly ``target(source) / proposal(source)``.
    """
    if particles <= 0:
        raise ValueError("particle count must be positive")
    sources = tuple(map(str, archive["source_ids"])); candidates = tuple(sorted(
        map(str, archive["candidate_ids"]), key=lambda node: int(archive["created_at"][node])
    ))
    for name, prior in (("target", target_source_prior), ("proposal", proposal_source_prior)):
        if set(prior) != set(sources) or any(float(prior[source]) < 0.0 for source in sources) \
                or not math.isclose(sum(float(prior[source]) for source in sources), 1.0, abs_tol=1e-8):
            raise ValueError(f"invalid {name} source prior")
    if any(float(proposal_source_prior[source]) <= 0.0 and float(target_source_prior[source]) > 0.0
           for source in sources):
        raise ValueError("proposal does not cover target support")
    rng = random.Random(seed)
    cumulative, total = [], 0.0
    for source in sources:
        total += float(proposal_source_prior[source]); cumulative.append((total, source))
    observed = [list(map(str, edge)) for edge in archive["observed_formation_edges"]]
    latent = [list(map(str, edge)) for edge in archive["latent_edge_candidates"]]
    masses: dict[tuple[str, frozenset[str]], float] = {}
    sampled_counts = {source: 0 for source in sources}
    importance_weights: list[float] = []
    for _ in range(particles):
        draw = rng.random(); source = next(value for threshold, value in cumulative if draw <= threshold)
        sampled_counts[source] += 1
        weight = float(target_source_prior[source]) / float(proposal_source_prior[source])
        importance_weights.append(weight)
        edges = observed + [edge for edge in latent if rng.random() < parameters.latent_edge_probability]
        parents = _parents(edges, candidates)
        contaminated, affected = set(), set()
        for node in candidates:
            active = [parent for parent in parents[node]
                      if parent == source or parent in contaminated]
            if not active:
                continue
            probability = parameters.contamination.score(contamination_features(
                archive, node, active, parents[node], source
            ))
            if rng.random() >= probability:
                continue
            contaminated.add(node)
            harm_probability = parameters.emission.score(emission_features(
                archive, node, source, active, parents[node]
            ))
            if rng.random() < harm_probability:
                affected.add(node)
        key = (source, frozenset(affected)); masses[key] = masses.get(key, 0.0) + weight
    total_weight = sum(importance_weights)
    worlds = tuple(LatentSourceWorld(source, affected, mass / total_weight)
                   for (source, affected), mass in masses.items() if mass > 0.0)
    posterior = LatentSourcePosterior(candidates, sources, worlds).normalize()
    squared = sum(weight * weight for weight in importance_weights)
    diagnostics = ImportanceSamplingDiagnostics(
        effective_sample_size=total_weight * total_weight / squared,
        maximum_importance_weight=max(importance_weights),
        minimum_importance_weight=min(importance_weights),
        sampled_source_counts=sampled_counts,
        target_source_prior={source: float(target_source_prior[source]) for source in sources},
        proposal_source_prior={source: float(proposal_source_prior[source]) for source in sources},
    )
    return posterior, diagnostics


def stable_seed(archive_id: str, particles: int) -> int:
    digest = hashlib.sha256(f"publication-v2|particles|{archive_id}|{particles}".encode()).digest()
    return int.from_bytes(digest[:8], "big")
