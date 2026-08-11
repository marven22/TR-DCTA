"""Frozen prior-aware ACIS-Risk adaptation for uncertain origins."""
from __future__ import annotations

import hashlib
from typing import Dict, FrozenSet, Mapping, Sequence, Tuple

from .memoryarena_v6 import DiscoveryCase, ObservableMemory
from .risk_aware_acis import LogisticCalibrator, ThreeSignalIndex


def _index(public: Mapping[str, object]) -> ThreeSignalIndex:
    parents: Dict[str, list[str]] = {
        str(node): [] for node in public["memories"]
    }
    for parent, child in public["formation_edges"]:
        parents[str(child)].append(str(parent))
    created = {str(key): int(value) for key, value in public["created_at"].items()}
    memories = tuple(
        ObservableMemory(
            node,
            str(public["memories"][node]["lesson"]),
            created[node],
            tuple(sorted(parents[node])),
            str(public["target_language"]),
            (),
            str(public["target_language"]),
        )
        for node in sorted(created, key=created.get)
    )
    case = DiscoveryCase(
        str(public["archive_id"]), str(public["source_ids"][0]), memories, frozenset()
    )
    return ThreeSignalIndex(case)


def run_prior_weighted_acis_risk(
    public: Mapping[str, object], affected_ids: FrozenSet[str], budget: int,
    calibrator: LogisticCalibrator,
) -> Tuple[str, ...]:
    """ACIS-Risk averaged over the supplied source prior.

    This preserves ACIS's positive-only anchor expansion. Negative labels do
    not update the source prior or candidate scores. Each source hypothesis is
    scored with the paper's frozen three signals and calibrator, then mixed
    using the same observable source prior supplied to probabilistic methods.
    """
    index = _index(public)
    sources = tuple(str(value) for value in public["source_ids"])
    prior = {str(key): float(value) for key, value in public["source_prior"].items()}
    candidates = tuple(str(value) for value in public["candidate_ids"])
    created = {str(key): int(value) for key, value in public["created_at"].items()}
    confirmed: set[str] = set()
    replayed: list[str] = []
    for _ in range(min(budget, len(candidates))):
        remaining = [node for node in candidates if node not in replayed]

        def probability(node: str, extra: str | None = None) -> float:
            return sum(
                prior[source] * calibrator.probability(index.signals(
                    node, {source, *confirmed, *({extra} if extra else set())}
                ))
                for source in sources
            )

        base = {node: probability(node) for node in remaining}
        scores = {}
        for node in remaining:
            impact = 1.0
            for later in remaining:
                if later == node or created[later] <= created[node]:
                    continue
                impact += max(0.0, probability(later, node) - base[later])
            jitter = int.from_bytes(hashlib.sha256(
                f"multi-origin-acis|{public['archive_id']}|{node}".encode()
            ).digest()[:8], "big") / float(2**64) * 1e-12
            scores[node] = base[node] * impact + jitter
        chosen = min(remaining, key=lambda node: (-scores[node], node))
        replayed.append(chosen)
        if chosen in affected_ids:
            confirmed.add(chosen)
    return tuple(replayed)

