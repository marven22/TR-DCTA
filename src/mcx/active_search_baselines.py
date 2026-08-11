"""Budget-matched active-search baselines for memory-cascade auditing.

ENS follows Jiang et al. (ICML 2017): query utility is the immediate target
probability plus the expected sum of the largest posterior probabilities that
can be collected with the remaining budget.  Our finite-world posterior makes
that expectation exact, so the Monte Carlo machinery in the authors' MATLAB
implementation is unnecessary.

Graph Active Search follows Wang et al. (KDD 2013): an undirected soft-label
graph model supplies probabilities and the acquisition score is probability
plus alpha times positive-conditioned graph impact (paper equations 1--3).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, FrozenSet, Iterable, Mapping, Sequence, Tuple

from .directional_transition import DirectionalPosterior


def _top_sum(values: Iterable[float], count: int) -> float:
    if count <= 0:
        return 0.0
    return sum(sorted(values, reverse=True)[:count])


def ens_score(
    posterior: DirectionalPosterior,
    node: str,
    remaining: Sequence[str],
    remaining_budget: int,
) -> float:
    """Exact sequential ENS acquisition for a supplied Bayesian posterior.

    ``remaining_budget`` includes the query currently being scored.  ENS
    treats all later queries as one terminal batch and therefore sums the
    largest conditional marginals for the remaining slots.
    """
    if node not in remaining:
        raise ValueError("ENS node must be in the remaining candidate set")
    if remaining_budget <= 0:
        raise ValueError("ENS requires a positive remaining budget")
    return _ens_scores(posterior, remaining, remaining_budget)[node]


def _ens_scores(
    posterior: DirectionalPosterior,
    remaining: Sequence[str],
    remaining_budget: int,
) -> Dict[str, float]:
    """Compute every exact ENS score from one marginal/joint pass.

    This is algebraically identical to conditioning separately on each
    outcome, but avoids repeatedly materializing posterior objects.  It is
    important for the 6,940-world LIBERO posteriors.
    """
    if remaining_budget <= 0:
        raise ValueError("ENS requires a positive remaining budget")
    nodes = tuple(remaining)
    if not nodes:
        return {}
    allowed = set(nodes)
    total = sum(world.weight for world in posterior.worlds)
    marginal_mass = {node: 0.0 for node in nodes}
    joint_mass: Dict[Tuple[str, str], float] = {}
    for world in posterior.worlds:
        positive = sorted(world.affected_ids & allowed)
        for node in positive:
            marginal_mass[node] += world.weight
        for left, right in combinations(positive, 2):
            joint_mass[left, right] = joint_mass.get((left, right), 0.0) + world.weight
    marginals = {node: mass / total for node, mass in marginal_mass.items()}
    future_slots = min(remaining_budget - 1, len(nodes) - 1)
    output = {}
    for node in nodes:
        probability = marginals[node]
        positive_probabilities = []
        negative_probabilities = []
        for other in nodes:
            if other == node:
                continue
            pair = (node, other) if node < other else (other, node)
            joint = joint_mass.get(pair, 0.0) / total
            if probability > 0.0:
                positive_probabilities.append(joint / probability)
            if probability < 1.0:
                negative_probabilities.append(
                    (marginals[other] - joint) / (1.0 - probability)
                )
        expected_future = (
            probability * _top_sum(positive_probabilities, future_slots)
            + (1.0 - probability) * _top_sum(negative_probabilities, future_slots)
        )
        output[node] = probability + expected_future
    return output


def ens_choice(
    posterior: DirectionalPosterior,
    remaining: Sequence[str],
    remaining_budget: int,
) -> str:
    """Select the deterministic maximum-ENS candidate."""
    if not remaining:
        raise ValueError("ENS requires at least one remaining candidate")
    scores = _ens_scores(posterior, remaining, remaining_budget)
    return min(remaining, key=lambda node: (-scores[node], node))


def run_ens_policy(
    posterior: DirectionalPosterior,
    affected_ids: FrozenSet[str],
    budget: int,
) -> Tuple[str, ...]:
    """Run sequential ENS, revealing a private label only after selection."""
    if budget < 0:
        raise ValueError("budget must be nonnegative")
    current = posterior
    remaining = list(posterior.candidates)
    replayed = []
    total = min(budget, len(remaining))
    for step in range(total):
        chosen = ens_choice(current, remaining, total - step)
        replayed.append(chosen)
        remaining.remove(chosen)
        current = current.condition(chosen, int(chosen in affected_ids))
        if current is None:
            raise ValueError("observed label has zero probability under ENS posterior")
    return tuple(replayed)


@dataclass(frozen=True)
class GraphActiveSearchParameters:
    """Wang et al. soft-label and acquisition parameters."""

    eta: float = 0.5
    prior_strength: float | None = None
    prior_probability: float = 0.1
    alpha: float = 0.01
    tolerance: float = 1e-12
    max_iterations: int = 10000

    def validate(self) -> None:
        if not 0.0 < self.eta <= 1.0:
            raise ValueError("eta must be in (0, 1]")
        if self.prior_strength is not None and self.prior_strength <= 0.0:
            raise ValueError("prior_strength must be positive")
        if not 0.0 <= self.prior_probability <= 1.0:
            raise ValueError("prior_probability must be in [0, 1]")
        if self.alpha < 0.0:
            raise ValueError("alpha must be nonnegative")
        if self.tolerance <= 0.0 or self.max_iterations <= 0:
            raise ValueError("invalid convergence controls")


class GraphActiveSearch:
    """Faithful small-graph implementation of Wang et al. (KDD 2013).

    The paper assumes an undirected nonnegative weight matrix.  Formation-DAG
    edges are therefore symmetrized before inference.  The known invalid source
    is supplied as an initial positive label, matching the paper's one-positive
    initialization.
    """

    def __init__(
        self,
        nodes: Sequence[str],
        edges: Iterable[Tuple[str, str]],
        initial_labels: Mapping[str, int],
        parameters: GraphActiveSearchParameters,
    ) -> None:
        parameters.validate()
        if not nodes or len(nodes) != len(set(nodes)):
            raise ValueError("graph nodes must be nonempty and unique")
        self.nodes = tuple(nodes)
        self.index = {node: offset for offset, node in enumerate(self.nodes)}
        self.parameters = parameters
        self.neighbors: Dict[str, Dict[str, float]] = {
            node: {} for node in self.nodes
        }
        for left, right in edges:
            if left not in self.index or right not in self.index:
                raise ValueError("graph edge references an unknown node")
            if left == right:
                continue
            self.neighbors[left][right] = self.neighbors[left].get(right, 0.0) + 1.0
            self.neighbors[right][left] = self.neighbors[right].get(left, 0.0) + 1.0
        if any(not self.neighbors[node] for node in self.nodes):
            raise ValueError("graph active search requires positive degree for every node")
        if not initial_labels:
            raise ValueError("graph active search requires an initial positive label")
        if any(node not in self.index or label not in (0, 1)
               for node, label in initial_labels.items()):
            raise ValueError("invalid initial graph label")
        if not any(initial_labels.values()):
            raise ValueError("paper initialization requires at least one positive")
        self.initial_labels = dict(initial_labels)

    def probabilities(self, labels: Mapping[str, int]) -> Dict[str, float]:
        """Solve paper equation 1 by fixed-point iteration."""
        if any(node not in self.index or label not in (0, 1)
               for node, label in labels.items()):
            raise ValueError("invalid graph label")
        p = self.parameters
        omega = p.prior_strength
        if omega is None:
            omega = 1.0 / len(self.nodes)
        values = {node: float(labels.get(node, p.prior_probability))
                  for node in self.nodes}
        for _ in range(p.max_iterations):
            updated = {}
            for node in self.nodes:
                degree = sum(self.neighbors[node].values())
                propagated = sum(weight * values[other]
                                 for other, weight in self.neighbors[node].items()) / degree
                if node in labels:
                    updated[node] = (1.0 - p.eta) * propagated + p.eta * labels[node]
                else:
                    updated[node] = (
                        propagated + omega * p.prior_probability
                    ) / (1.0 + omega)
            if max(abs(updated[node] - values[node]) for node in self.nodes) <= p.tolerance:
                return updated
            values = updated
        raise RuntimeError("graph active-search soft-label model did not converge")

    def score(
        self,
        node: str,
        labels: Mapping[str, int],
        remaining: Sequence[str],
    ) -> Tuple[float, float, float]:
        """Return score, probability, and positive-conditioned impact."""
        if node not in remaining:
            raise ValueError("graph-search node must be unobserved")
        base = self.probabilities(labels)
        positive = self.probabilities({**labels, node: 1})
        delta = sum(positive[other] - base[other]
                    for other in remaining if other != node)
        impact = base[node] * delta
        return base[node] + self.parameters.alpha * impact, base[node], impact

    def choose(self, labels: Mapping[str, int], remaining: Sequence[str]) -> str:
        if not remaining:
            raise ValueError("graph active search requires a remaining candidate")
        scored = [(self.score(node, labels, remaining)[0], node) for node in remaining]
        return min(scored, key=lambda item: (-item[0], item[1]))[1]

    def run(
        self,
        candidate_ids: Sequence[str],
        affected_ids: FrozenSet[str],
        budget: int,
    ) -> Tuple[str, ...]:
        """Run the adaptive policy without exposing unqueried private labels."""
        if budget < 0:
            raise ValueError("budget must be nonnegative")
        if any(node not in self.index for node in candidate_ids):
            raise ValueError("candidate is absent from graph")
        labels = dict(self.initial_labels)
        remaining = list(candidate_ids)
        replayed = []
        for _ in range(min(budget, len(remaining))):
            chosen = self.choose(labels, remaining)
            replayed.append(chosen)
            remaining.remove(chosen)
            labels[chosen] = int(chosen in affected_ids)
        return tuple(replayed)
