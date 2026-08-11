"""Deterministic task-matched archive scaling for Meta-World DCTA studies."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from typing import Mapping, Sequence

from .publication_v2_source import memory_text, similarity


@dataclass(frozen=True)
class ScaledArchive:
    archive: dict[str, object]
    affected_ids: frozenset[str]
    policy_by_memory: dict[str, str]
    success_by_policy: dict[str, bool]
    original_candidate_ids: tuple[str, ...]
    distractor_ids: tuple[str, ...]
    distractor_true_edges: tuple[tuple[str, str], ...]
    distractor_observed_edges: tuple[tuple[str, str], ...]
    distractor_latent_edges: tuple[tuple[str, str], ...]
    template_ids: tuple[str, ...]


def _stable_fraction(*parts: object) -> float:
    value = "|".join(map(str, parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big") / 2**64


def _clone_id(archive_id: str, offset: int) -> str:
    digest = hashlib.sha256(
        f"metaworld-scalability|{archive_id}|{offset}".encode("utf-8")
    ).hexdigest()[:20]
    return f"d_{digest}"


def _source_reachability(
    sources: Sequence[str], edges: Sequence[Sequence[str]],
) -> dict[str, set[str]]:
    children: dict[str, list[str]] = {}
    for left, right in edges:
        children.setdefault(str(left), []).append(str(right))
    output: dict[str, set[str]] = {}
    for source in map(str, sources):
        reached, frontier = set(), list(children.get(source, ()))
        while frontier:
            node = frontier.pop()
            if node in reached:
                continue
            reached.add(node)
            frontier.extend(children.get(node, ()))
        output[source] = reached
    return output


def _templates(
    archive: Mapping[str, object], clean_memories: Mapping[str, Mapping[str, object]],
    clean_policy_by_memory: Mapping[str, str], success_by_policy: Mapping[str, bool],
) -> dict[str, tuple[tuple[str, str], ...]]:
    """Return difficult, verified-clean templates grouped by observable source."""

    sources = tuple(map(str, archive["source_ids"]))
    candidates = set(map(str, archive["candidate_ids"]))
    observed = [tuple(map(str, edge)) for edge in archive["observed_formation_edges"]]
    possible = observed + [tuple(map(str, edge))
                           for edge in archive["latent_edge_candidates"]]
    reachable = _source_reachability(sources, possible)
    parents: dict[str, list[str]] = {node: [] for node in candidates}
    for left, right in possible:
        if right in parents:
            parents[right].append(left)
    output: dict[str, list[tuple[str, str]]] = {source: [] for source in sources}
    target = str(archive["target_language"])
    for source in sources:
        for node in candidates:
            policy = str(clean_policy_by_memory.get(node, ""))
            if not policy or not bool(success_by_policy.get(policy, False)):
                continue
            if node not in clean_memories or node not in reachable[source]:
                continue
            valid_parents = [parent for parent in parents[node]
                             if parent == source or parent in reachable[source]]
            for parent in valid_parents:
                output[source].append((node, parent))
        output[source].sort(key=lambda item: (
            -similarity(memory_text(clean_memories[item[0]]), target),
            _stable_fraction(archive["archive_id"], source, item[0], item[1]),
            item,
        ))
        if not output[source]:
            raise ValueError(
                f"no verified clean observable template for source {source} "
                f"in {archive['archive_id']}"
            )
    return {source: tuple(values) for source, values in output.items()}


def scale_archive(
    archive: Mapping[str, object], truth: Mapping[str, object],
    clean_memories: Mapping[str, Mapping[str, object]],
    clean_policy_by_memory: Mapping[str, str],
    corrupted_policy_by_memory: Mapping[str, str],
    success_by_policy: Mapping[str, bool], target_size: int,
) -> ScaledArchive:
    """Append nested, task-matched, verified-benign causal distractors.

    Existing candidates, memories, edges, timestamps, and harmful labels remain
    unchanged. Each added memory copies a clean same-task memory whose policy is
    verified successful on the target. It receives one plausible true parent.
    The new edge is observed or latent according to the archive's frozen mask.
    """

    original = tuple(map(str, archive["candidate_ids"]))
    if target_size < len(original):
        raise ValueError("target archive size cannot remove original candidates")
    if len(original) != len(set(original)):
        raise ValueError("base candidate IDs must be unique")
    scaled = deepcopy(dict(archive))
    scaled["candidate_ids"] = list(original)
    scaled["memories"] = deepcopy(dict(archive["memories"]))
    scaled["created_at"] = {str(k): int(v) for k, v in archive["created_at"].items()}
    scaled["observed_formation_edges"] = [
        list(map(str, edge)) for edge in archive["observed_formation_edges"]
    ]
    scaled["latent_edge_candidates"] = [
        list(map(str, edge)) for edge in archive["latent_edge_candidates"]
    ]
    policy_by_memory = {str(k): str(v) for k, v in corrupted_policy_by_memory.items()}
    successes = {str(k): bool(v) for k, v in success_by_policy.items()}
    templates = _templates(
        archive, clean_memories, clean_policy_by_memory, success_by_policy,
    )
    sources = tuple(map(str, archive["source_ids"]))
    maximum_time = max(map(int, scaled["created_at"].values()))
    missing_rate = float(archive["provenance_missing_rate"])
    distractors, true_edges, observed_edges, latent_edges, used_templates = [], [], [], [], []
    for offset in range(target_size - len(original)):
        node = _clone_id(str(archive["archive_id"]), offset)
        source = sources[offset % len(sources)]
        choices = templates[source]
        template, parent = choices[(offset // len(sources)) % len(choices)]
        memory = deepcopy(dict(clean_memories[template]))
        policy = str(clean_policy_by_memory[template])
        if not successes.get(policy, False):
            raise ValueError("distractor template policy is not verified successful")
        edge = (parent, node)
        hidden = _stable_fraction(archive["archive_id"], "edge-mask", offset) < missing_rate
        memory["cited_memory_ids"] = [] if hidden else [parent]
        scaled["candidate_ids"].append(node)
        scaled["memories"][node] = memory
        scaled["created_at"][node] = maximum_time + offset + 1
        if hidden:
            scaled["latent_edge_candidates"].append(list(edge))
            latent_edges.append(edge)
        else:
            scaled["observed_formation_edges"].append(list(edge))
            observed_edges.append(edge)
        policy_by_memory[node] = policy
        distractors.append(node)
        true_edges.append(edge)
        used_templates.append(template)
    scaled["scalability_parent_archive_id"] = str(archive["archive_id"])
    scaled["scalability_target_size"] = target_size
    affected = frozenset(map(str, truth["affected_ids"]))
    if affected - set(original):
        raise ValueError("base harmful set is outside the original archive")
    result = ScaledArchive(
        archive=scaled, affected_ids=affected,
        policy_by_memory=policy_by_memory, success_by_policy=successes,
        original_candidate_ids=original, distractor_ids=tuple(distractors),
        distractor_true_edges=tuple(true_edges),
        distractor_observed_edges=tuple(observed_edges),
        distractor_latent_edges=tuple(latent_edges),
        template_ids=tuple(used_templates),
    )
    validate_scaled_archive(result, archive)
    return result


def validate_scaled_archive(
    scaled: ScaledArchive, base_archive: Mapping[str, object],
) -> None:
    archive = scaled.archive
    base_ids = tuple(map(str, base_archive["candidate_ids"]))
    candidate_ids = tuple(map(str, archive["candidate_ids"]))
    if candidate_ids[:len(base_ids)] != base_ids:
        raise ValueError("scaling changed original candidate order")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("scaled candidate IDs are not unique")
    for node in base_ids:
        if archive["memories"][node] != base_archive["memories"][node]:
            raise ValueError(f"scaling changed original memory {node}")
        if int(archive["created_at"][node]) != int(base_archive["created_at"][node]):
            raise ValueError(f"scaling changed original timestamp {node}")
    if set(scaled.distractor_ids) & scaled.affected_ids:
        raise ValueError("a scalability distractor is labeled harmful")
    if any(not scaled.success_by_policy.get(scaled.policy_by_memory[node], False)
           for node in scaled.distractor_ids):
        raise ValueError("a scalability distractor lacks verified target success")
    if len(scaled.distractor_true_edges) != len(scaled.distractor_ids):
        raise ValueError("every distractor requires exactly one true parent")
    observed = {tuple(map(str, edge)) for edge in archive["observed_formation_edges"]}
    latent = {tuple(map(str, edge)) for edge in archive["latent_edge_candidates"]}
    if observed & latent:
        raise ValueError("an edge cannot be both observed and latent")
    if set(scaled.distractor_true_edges) != set(scaled.distractor_observed_edges) | set(scaled.distractor_latent_edges):
        raise ValueError("new true edges are not partitioned into observed and latent")


def frozen_harm_weights(base_archive: Mapping[str, object]) -> dict[str, float]:
    """Compute the original SC-DCTA weights without archive-size drift."""

    candidates = list(map(str, base_archive["candidate_ids"]))
    created = base_archive["created_at"]
    edges = [tuple(map(str, edge)) for edge in base_archive["observed_formation_edges"]]
    children = {node: [] for node in candidates}
    for left, right in edges:
        if left in children:
            children[left].append(right)
    reach = {}
    for node in candidates:
        found, frontier = set(), list(children[node])
        while frontier:
            child = frontier.pop()
            if child not in found:
                found.add(child)
                frontier.extend(children.get(child, ()))
        reach[node] = len(found)
    times = [int(created[node]) for node in candidates]
    minimum, maximum = min(times), max(times)
    max_reach = max(reach.values()) or 1
    return {
        node: 1.0
        + .25 * (int(created[node]) - minimum) / max(maximum - minimum, 1)
        + .25 * reach[node] / max_reach
        for node in candidates
    }


def extend_harm_weights(
    base_archive: Mapping[str, object], scaled: ScaledArchive,
) -> dict[str, float]:
    base = frozen_harm_weights(base_archive)
    output = dict(base)
    for node, template in zip(scaled.distractor_ids, scaled.template_ids):
        output[node] = base[template]
    return output
