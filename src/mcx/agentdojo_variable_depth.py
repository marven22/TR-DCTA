"""Variable-depth provenance utilities for full AgentDojo task coverage."""
from __future__ import annotations

from collections import Counter
import itertools
import math
from typing import Mapping, Sequence

from .agentdojo_method import stable_seed
from .prob_dcta_benchmark import LatentSourcePosterior, LatentSourceWorld


def lineages(archive_id: str, sources: Sequence[str], variants: Sequence[str]):
    import random
    chains = {source: [] for source in sources}; mapping = {}; layers = []
    for depth, variant in enumerate(variants):
        shuffled = list(sources)
        random.Random(stable_seed("opaque", archive_id, depth)).shuffle(shuffled)
        layer = []
        for rank, source in enumerate(shuffled):
            node = f"m{depth}_{rank:02d}"; chains[source].append(node)
            mapping[(source, variant)] = node; layer.append(node)
        layers.append(tuple(sorted(layer)))
    return {key: tuple(value) for key, value in chains.items()}, mapping, tuple(layers)


def masks(archive_id: str, chains: Mapping[str, Sequence[str]], condition: str,
          replicates: int, namespace: str):
    sources = tuple(sorted(chains)); depth = len(next(iter(chains.values())))
    if condition == "complete": patterns = [(0,) * depth]
    elif condition == "partial_33":
        base = (2,) + (0,) * (depth - 1)
        patterns = sorted(set(itertools.permutations(base)))
    elif condition == "partial_67": patterns = [(2,) * depth]
    else: raise ValueError(condition)
    output = []; seen = set()
    for replicate in range(replicates):
        nonce = 0
        while True:
            pattern = patterns[(stable_seed(namespace, archive_id, "pattern") + replicate + nonce) % len(patterns)]
            edges = []
            for layer, hidden_count in enumerate(pattern):
                rotation = stable_seed(namespace, archive_id, replicate, nonce, layer) % len(sources)
                hidden = {sources[(rotation + i) % len(sources)] for i in range(hidden_count)}
                for source in sources:
                    if source not in hidden:
                        left = source if layer == 0 else chains[source][layer - 1]
                        edges.append((left, chains[source][layer]))
            edges = tuple(sorted(edges))
            if edges not in seen:
                seen.add(edges); output.append((replicate, nonce, pattern, edges)); break
            nonce += 1
            if nonce > 1000: raise RuntimeError("cannot construct distinct masks")
    return output


def _options(parents, children, observed):
    fixed = tuple((a, b) for a, b in observed if a in parents and b in children)
    p = tuple(x for x in parents if x not in {a for a, _ in fixed})
    c = tuple(x for x in children if x not in {b for _, b in fixed})
    return tuple(tuple(sorted(fixed + tuple(zip(p, perm)))) for perm in itertools.permutations(c))


def posterior(sources: Sequence[str], layers: Sequence[Sequence[str]], observed,
              source_prior: Mapping[str, float], length_prior: Sequence[float]):
    sources = tuple(sources); layers = tuple(tuple(x) for x in layers)
    if len(length_prior) != len(layers): raise ValueError("length prior/depth mismatch")
    options = []; parents = sources
    for layer in layers:
        options.append(_options(parents, layer, observed)); parents = layer
    completion_count = math.prod(map(len, options)); counts = Counter()
    for completion in itertools.product(*options):
        maps = tuple(dict(edges) for edges in completion)
        for source in sources:
            chain = []; node = source
            for mapping in maps:
                node = mapping[node]; chain.append(node)
            for length in range(1, len(chain) + 1):
                counts[(source, length, frozenset(chain[:length]))] += 1
    worlds = []
    for (source, length, affected), count in sorted(counts.items(), key=lambda x: str(x[0])):
        weight = source_prior[source] * length_prior[length - 1] * count / completion_count
        if weight: worlds.append(LatentSourceWorld(source, affected, weight))
    candidates = tuple(node for layer in layers for node in layer)
    return LatentSourcePosterior(candidates, sources, tuple(worlds)).normalize(), completion_count
