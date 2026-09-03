"""Pure construction utilities for the AgentDojo TR-DCTA method pilot."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import itertools
import math
import random
from typing import Iterable, Mapping, Sequence

from .prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld


def stable_seed(*parts: object) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16)


def select_archive_source_groups(
    qualifying: Iterable[tuple[str, str]], *, suite: str, salt: str,
    archive_count: int, sources_per_archive: int,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    by_user: dict[str, list[str]] = defaultdict(list)
    for user_id, injection_id in set(qualifying):
        by_user[user_id].append(injection_id)
    candidates = []
    for user_id, injections in by_user.items():
        ranked = sorted(
            set(injections),
            key=lambda injection: hashlib.sha256(
                f"{salt}|source|{suite}|{user_id}|{injection}".encode()
            ).hexdigest(),
        )
        if len(ranked) < sources_per_archive:
            continue
        chosen = tuple(ranked[:sources_per_archive])
        score = hashlib.sha256(
            f"{salt}|archive|{suite}|{user_id}|{'|'.join(chosen)}".encode()
        ).hexdigest()
        candidates.append((score, user_id, chosen))
    candidates.sort()
    if len(candidates) < archive_count:
        raise ValueError(f"suite {suite} lacks {archive_count} qualifying archive groups")
    return tuple((user, sources) for _, user, sources in candidates[:archive_count])


def opaque_lineages(
    archive_id: str, sources: Sequence[str], variants: Sequence[str],
) -> tuple[dict[str, tuple[str, ...]], dict[tuple[str, str], str], tuple[tuple[str, ...], ...]]:
    lineages: dict[str, list[str]] = {source: [] for source in sources}
    private_to_opaque: dict[tuple[str, str], str] = {}
    by_depth = []
    for depth, variant in enumerate(variants):
        shuffled = list(sources)
        random.Random(stable_seed("opaque", archive_id, depth)).shuffle(shuffled)
        nodes = []
        for rank, source in enumerate(shuffled):
            node = f"m{depth}_{rank:02d}"
            lineages[source].append(node)
            private_to_opaque[(source, variant)] = node
            nodes.append(node)
        by_depth.append(tuple(sorted(nodes)))
    return (
        {source: tuple(nodes) for source, nodes in lineages.items()},
        private_to_opaque,
        tuple(by_depth),
    )


def observed_edges(
    archive_id: str, lineages: Mapping[str, Sequence[str]], hidden_per_layer: int,
) -> tuple[tuple[str, str], ...]:
    sources = tuple(sorted(lineages))
    if hidden_per_layer < 0 or hidden_per_layer >= len(sources):
        raise ValueError("hidden links must leave at least one visible edge per layer")
    edges = []
    for layer in range(3):
        rotation = stable_seed("mask", archive_id, hidden_per_layer, layer) % len(sources)
        hidden = {
            sources[(rotation + offset) % len(sources)]
            for offset in range(hidden_per_layer)
        }
        for source in sources:
            if source in hidden:
                continue
            left = source if layer == 0 else lineages[source][layer - 1]
            right = lineages[source][layer]
            edges.append((left, right))
    return tuple(sorted(edges))


def _layer_options(
    parents: Sequence[str], children: Sequence[str],
    observed: Sequence[tuple[str, str]],
) -> tuple[tuple[tuple[str, str], ...], ...]:
    fixed = tuple(
        (left, right) for left, right in observed
        if left in parents and right in children
    )
    used_parents = {left for left, _ in fixed}
    used_children = {right for _, right in fixed}
    missing_parents = tuple(node for node in parents if node not in used_parents)
    missing_children = tuple(node for node in children if node not in used_children)
    if len(missing_parents) != len(missing_children):
        raise ValueError("observed layer is not a partial one-to-one matching")
    return tuple(
        tuple(sorted(fixed + tuple(zip(missing_parents, permutation))))
        for permutation in itertools.permutations(missing_children)
    )


def build_posterior(
    sources: Sequence[str], by_depth: Sequence[Sequence[str]],
    observed: Sequence[tuple[str, str]], source_prior: Mapping[str, float],
    length_prior: Sequence[float],
) -> tuple[LatentSourcePosterior, int]:
    sources = tuple(sources)
    by_depth = tuple(tuple(layer) for layer in by_depth)
    if not math.isclose(sum(source_prior.values()), 1.0, abs_tol=1e-12):
        raise ValueError("source prior must sum to one")
    if not math.isclose(sum(length_prior), 1.0, abs_tol=1e-12):
        raise ValueError("length prior must sum to one")
    options = (
        _layer_options(sources, by_depth[0], observed),
        _layer_options(by_depth[0], by_depth[1], observed),
        _layer_options(by_depth[1], by_depth[2], observed),
    )
    completion_count = math.prod(len(layer) for layer in options)
    counts: Counter[tuple[str, int, frozenset[str]]] = Counter()
    for first, second, third in itertools.product(*options):
        maps = (dict(first), dict(second), dict(third))
        for source in sources:
            chain = (maps[0][source],)
            chain += (maps[1][chain[0]],)
            chain += (maps[2][chain[1]],)
            for length in range(1, 4):
                counts[(source, length, frozenset(chain[:length]))] += 1
    worlds = []
    for (source, length, affected), count in sorted(
        counts.items(), key=lambda item: (item[0][0], item[0][1], sorted(item[0][2]))
    ):
        weight = float(source_prior[source]) * float(length_prior[length - 1])
        weight *= count / completion_count
        if weight > 0.0:
            worlds.append(LatentSourceWorld(source, affected, weight))
    candidates = tuple(node for layer in by_depth for node in layer)
    return LatentSourcePosterior(candidates, sources, tuple(worlds)).normalize(), completion_count


def regime_prior(
    source_ids: Sequence[str], true_source: str, decoy_source: str,
    specification: Mapping[str, float],
) -> dict[str, float]:
    values = {}
    for source in source_ids:
        role = "true" if source == true_source else "decoy" if source == decoy_source else "other"
        values[source] = float(specification[role])
    if not math.isclose(sum(values.values()), 1.0, abs_tol=1e-12):
        raise ValueError("regime prior must sum to one")
    return values


def condition_trace(
    posterior: LatentSourcePosterior, replayed: Sequence[str], affected: frozenset[str],
) -> LatentSourcePosterior:
    belief = posterior
    for node in replayed:
        updated = belief.condition(node, int(node in affected))
        if updated is not None:
            belief = updated
    return belief


def random_policy(
    posterior: LatentSourcePosterior, affected: frozenset[str], budget: int, seed: int,
) -> tuple[tuple[str, ...], LatentSourcePosterior]:
    rng = random.Random(seed)
    remaining = list(posterior.candidates)
    replayed = []
    belief = posterior
    for _ in range(min(budget, len(remaining))):
        chosen = remaining.pop(rng.randrange(len(remaining)))
        replayed.append(chosen)
        updated = belief.condition(chosen, int(chosen in affected))
        if updated is not None:
            belief = updated
    return tuple(replayed), belief

