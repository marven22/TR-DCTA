"""AgentDojo adapters for external Graph Active Search and MemoRepair baselines."""
from __future__ import annotations

from typing import Mapping, Sequence

from .active_search_baselines import GraphActiveSearchParameters


class PriorSafeGraphActiveSearch:
    """Wang et al. graph active search with prior-only isolated vertices.

    Missing provenance can leave a vertex with degree zero. Paper equation 1
    has no neighbor term in that boundary case; we use the declared class prior.
    All non-isolated vertices follow the published fixed-point equation exactly.
    """
    def __init__(self, nodes, edges, initial_labels, parameters):
        parameters.validate()
        self.nodes = tuple(nodes)
        self.p = parameters
        self.neighbors = {node: set() for node in self.nodes}
        for left, right in edges:
            if left not in self.neighbors or right not in self.neighbors:
                raise ValueError("unknown node")
            if left != right:
                self.neighbors[left].add(right)
                self.neighbors[right].add(left)
        self.labels = dict(initial_labels)
        if not any(self.labels.values()):
            raise ValueError("positive seed required")

    def probabilities(self, labels: Mapping[str,int]):
        p = self.p
        omega = p.prior_strength or 1 / len(self.nodes)
        values = {
            node: float(labels.get(node, p.prior_probability)) for node in self.nodes
        }
        for _ in range(p.max_iterations):
            updated = {}
            for node in self.nodes:
                if self.neighbors[node]:
                    propagated = sum(values[x] for x in self.neighbors[node]) / len(
                        self.neighbors[node]
                    )
                else:
                    propagated = p.prior_probability
                if node in labels:
                    updated[node] = (1 - p.eta) * propagated + p.eta * labels[node]
                else:
                    updated[node] = (
                        propagated + omega * p.prior_probability
                    ) / (1 + omega)
            if max(abs(updated[x] - values[x]) for x in self.nodes) <= p.tolerance:
                return updated
            values = updated
        raise RuntimeError("graph active search did not converge")

    def choose(self, labels, remaining):
        base = self.probabilities(labels)
        scores = {}
        for node in remaining:
            positive = self.probabilities({**labels, node: 1})
            delta = sum(positive[x] - base[x] for x in remaining if x != node)
            scores[node] = base[node] + self.p.alpha * base[node] * delta
        return min(remaining, key=lambda x: (-scores[x], x))

    def run(self, candidates: Sequence[str], affected: frozenset[str], budget: int):
        labels = dict(self.labels)
        remaining = list(candidates)
        replayed = []
        for _ in range(min(budget, len(remaining))):
            chosen = self.choose(labels, remaining)
            remaining.remove(chosen)
            replayed.append(chosen)
            labels[chosen] = int(chosen in affected)
        return tuple(replayed), labels, self.probabilities(labels)


def native_graph_quarantine(candidates, probabilities, replayed, affected, capacity):
    """Quarantine confirmed positives, then highest GAS soft-label scores."""
    positive = [x for x in replayed if x in affected]
    remainder = [x for x in candidates if x not in positive]
    ranked = sorted(remainder, key=lambda x: (-probabilities[x], x))
    return tuple(sorted(positive + ranked[: max(0, capacity - len(positive))]))
