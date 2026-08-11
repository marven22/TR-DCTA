"""Small exact models for source-conditioned cascade discovery.

This module is intentionally separate from the MemoryArena development data.
It provides a finite latent-world Bayes oracle and a controlled branch-family
generator for testing whether uncertain provenance changes replay decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import product
import math
import random
from typing import Dict, FrozenSet, Iterable, Mapping, Sequence, Tuple

from .memoryarena_v6 import DiscoveryCase, ObservableMemory


@dataclass(frozen=True)
class LatentWorld:
    """One possible affected cascade and its prior/post-observation weight."""

    name: str
    affected_ids: FrozenSet[str]
    weight: float


@dataclass(frozen=True)
class FiniteCascadeBelief:
    """A normalized finite posterior over affected-cascade worlds."""

    candidates: Tuple[str, ...]
    worlds: Tuple[LatentWorld, ...]

    def __post_init__(self) -> None:
        if not self.candidates:
            raise ValueError("at least one candidate is required")
        if not self.worlds:
            raise ValueError("at least one latent world is required")
        candidate_set = set(self.candidates)
        if len(candidate_set) != len(self.candidates):
            raise ValueError("candidate IDs must be unique")
        if any(world.weight < 0.0 for world in self.worlds):
            raise ValueError("world weights must be nonnegative")
        if sum(world.weight for world in self.worlds) <= 0.0:
            raise ValueError("world weights must have positive mass")
        if any(not world.affected_ids.issubset(candidate_set) for world in self.worlds):
            raise ValueError("world contains an unknown affected candidate")

    def normalized_weights(self, possible: Iterable[int] | None = None) -> Dict[int, float]:
        indices = tuple(range(len(self.worlds))) if possible is None else tuple(possible)
        total = sum(self.worlds[index].weight for index in indices)
        if total <= 0.0:
            raise ValueError("conditioning event has zero posterior mass")
        return {index: self.worlds[index].weight / total for index in indices}

    def probability(self, node: str, possible: Iterable[int] | None = None) -> float:
        weights = self.normalized_weights(possible)
        return sum(
            weight
            for index, weight in weights.items()
            if node in self.worlds[index].affected_ids
        )

    def condition(self, possible: Iterable[int], node: str, label: int) -> Tuple[int, ...]:
        return tuple(
            index
            for index in possible
            if int(node in self.worlds[index].affected_ids) == label
        )


@dataclass(frozen=True)
class PolicyRun:
    replayed_ids: Tuple[str, ...]
    discovered_ids: FrozenSet[str]

    @property
    def discoveries(self) -> int:
        return len(self.discovered_ids)


@dataclass(frozen=True)
class BranchInstance:
    """Observed archive plus exact posterior for one sampled latent branch."""

    case: DiscoveryCase
    belief: FiniteCascadeBelief
    true_world: int
    observed_source_edges: FrozenSet[str]
    content_signals: Mapping[str, int]
    q: float
    r: float
    sensitivity: float
    false_positive_rate: float


@dataclass(frozen=True)
class MultiCascadeInstance:
    """Observed archive and finite posterior with several possible cascades."""

    case: DiscoveryCase
    belief: FiniteCascadeBelief
    true_world: int
    true_depths: Tuple[int, ...]
    observed_edges: FrozenSet[Tuple[str, str]]
    content_signals: Mapping[str, int]
    branch_nodes: Tuple[Tuple[str, ...], ...]
    prevalence: float
    transmission: float
    q: float
    r: float
    sensitivity: float
    false_positive_rate: float


def branch_posterior_under_parameters(
    instance: BranchInstance,
    *,
    q: float,
    r: float,
    sensitivity: float | None = None,
    false_positive_rate: float | None = None,
) -> FiniteCascadeBelief:
    """Recompute the branch posterior under possibly misspecified parameters."""
    sensitivity = instance.sensitivity if sensitivity is None else sensitivity
    false_positive_rate = (
        instance.false_positive_rate
        if false_positive_rate is None
        else false_positive_rate
    )
    for name, value in {
        "q": q,
        "r": r,
        "sensitivity": sensitivity,
        "false_positive_rate": false_positive_rate,
    }.items():
        if not 0.0 < value < 1.0:
            raise ValueError(f"{name} must lie strictly between zero and one")

    log_weights = []
    for candidate_world, world in enumerate(instance.belief.worlds):
        log_weight = -math.log(len(instance.belief.worlds))
        for branch, branch_world in enumerate(instance.belief.worlds):
            gateway = min(
                branch_world.affected_ids,
                key=lambda node: int(node.rsplit("n", 1)[1]),
            )
            edge_probability = q if branch == candidate_world else r
            log_weight += _bernoulli_log_likelihood(
                int(gateway in instance.observed_source_edges), edge_probability
            )
            for node in branch_world.affected_ids:
                affected = branch == candidate_world
                clue_probability = sensitivity if affected else false_positive_rate
                log_weight += _bernoulli_log_likelihood(
                    instance.content_signals[node], clue_probability
                )
        log_weights.append(log_weight)
    posterior = _normalize_log_weights(log_weights)
    return FiniteCascadeBelief(
        instance.belief.candidates,
        tuple(
            LatentWorld(world.name, world.affected_ids, posterior[index])
            for index, world in enumerate(instance.belief.worlds)
        ),
    )


def _depth_probabilities(
    branch_size: int, prevalence: float, transmission: float
) -> Tuple[float, ...]:
    probabilities = [1.0 - prevalence]
    for depth in range(1, branch_size):
        probabilities.append(
            prevalence * transmission ** (depth - 1) * (1.0 - transmission)
        )
    probabilities.append(prevalence * transmission ** (branch_size - 1))
    return tuple(probabilities)


def _draw_categorical(rng: random.Random, probabilities: Sequence[float]) -> int:
    threshold = rng.random()
    cumulative = 0.0
    for index, probability in enumerate(probabilities):
        cumulative += probability
        if threshold <= cumulative:
            return index
    return len(probabilities) - 1


def _multicascade_posterior(
    *,
    branch_nodes: Tuple[Tuple[str, ...], ...],
    observed_edges: FrozenSet[Tuple[str, str]],
    content_signals: Mapping[str, int],
    prevalence: float,
    transmission: float,
    q: float,
    r: float,
    sensitivity: float,
    false_positive_rate: float,
) -> FiniteCascadeBelief:
    depth_probabilities = _depth_probabilities(
        len(branch_nodes[0]), prevalence, transmission
    )
    depth_worlds = tuple(
        depths
        for depths in product(range(len(branch_nodes[0]) + 1), repeat=len(branch_nodes))
        if any(depths)
    )
    log_weights = []
    affected_sets = []
    for depths in depth_worlds:
        log_weight = sum(
            _safe_log_probability(depth_probabilities[depth]) for depth in depths
        )
        affected = set()
        for branch, nodes in enumerate(branch_nodes):
            depth = depths[branch]
            affected.update(nodes[:depth])
            legal_edges = (("s", nodes[0]),) + tuple(
                (nodes[offset - 1], nodes[offset])
                for offset in range(1, len(nodes))
            )
            for target_offset, edge in enumerate(legal_edges):
                is_transmitting = depth > target_offset
                edge_probability = q if is_transmitting else r
                log_weight += _bernoulli_log_likelihood(
                    int(edge in observed_edges), edge_probability
                )
            for offset, node in enumerate(nodes):
                clue_probability = (
                    sensitivity if offset < depth else false_positive_rate
                )
                log_weight += _bernoulli_log_likelihood(
                    content_signals[node], clue_probability
                )
        log_weights.append(log_weight)
        affected_sets.append(frozenset(affected))
    posterior = _normalize_log_weights(log_weights)
    candidates = tuple(node for nodes in branch_nodes for node in nodes)
    return FiniteCascadeBelief(
        candidates,
        tuple(
            LatentWorld(
                "depths_" + "_".join(str(depth) for depth in depths),
                affected_sets[index],
                posterior[index],
            )
            for index, depths in enumerate(depth_worlds)
        ),
    )


def build_multicascade_instance(
    *,
    seed: int,
    branches: int = 4,
    branch_size: int = 3,
    prevalence: float = 0.35,
    transmission: float = 0.95,
    q: float = 0.45,
    r: float = 0.20,
    sensitivity: float = 0.80,
    false_positive_rate: float = 0.20,
) -> MultiCascadeInstance:
    """Sample several prefix cascades and compute their exact finite posterior."""
    if branches < 2 or branch_size < 2:
        raise ValueError("multi-cascade family requires >=2 branches of size >=2")
    for name, value in {
        "prevalence": prevalence,
        "transmission": transmission,
        "q": q,
        "r": r,
        "sensitivity": sensitivity,
        "false_positive_rate": false_positive_rate,
    }.items():
        if not 0.0 < value < 1.0:
            raise ValueError(f"{name} must lie strictly between zero and one")
    rng = random.Random(seed)
    probabilities = _depth_probabilities(branch_size, prevalence, transmission)
    while True:
        true_depths = tuple(
            _draw_categorical(rng, probabilities) for _ in range(branches)
        )
        if any(true_depths):
            break
    branch_nodes = tuple(
        tuple(f"b{branch}_n{offset}" for offset in range(branch_size))
        for branch in range(branches)
    )
    observed_edges = set()
    content_signals: Dict[str, int] = {}
    for branch, nodes in enumerate(branch_nodes):
        depth = true_depths[branch]
        legal_edges = (("s", nodes[0]),) + tuple(
            (nodes[offset - 1], nodes[offset])
            for offset in range(1, len(nodes))
        )
        for target_offset, edge in enumerate(legal_edges):
            probability = q if depth > target_offset else r
            if rng.random() < probability:
                observed_edges.add(edge)
        for offset, node in enumerate(nodes):
            probability = sensitivity if offset < depth else false_positive_rate
            content_signals[node] = int(rng.random() < probability)

    observed_edges_frozen = frozenset(observed_edges)
    belief = _multicascade_posterior(
        branch_nodes=branch_nodes,
        observed_edges=observed_edges_frozen,
        content_signals=content_signals,
        prevalence=prevalence,
        transmission=transmission,
        q=q,
        r=r,
        sensitivity=sensitivity,
        false_positive_rate=false_positive_rate,
    )
    source_content = "invalid source policy hazard"
    memories = [ObservableMemory("s", source_content, 0)]
    created_at = 1
    for branch, nodes in enumerate(branch_nodes):
        for offset, node in enumerate(nodes):
            content = (
                f"invalid source policy hazard branch{branch} node{offset}"
                if content_signals[node]
                else f"independent clean routine branch{branch} node{offset}"
            )
            edge = ("s", node) if offset == 0 else (nodes[offset - 1], node)
            parents = (edge[0],) if offset > 0 and edge in observed_edges else ()
            exposures = ("s",) if offset == 0 and edge in observed_edges else ()
            memories.append(
                ObservableMemory(
                    node,
                    content,
                    created_at,
                    parents,
                    "scacd-up-multicascade-family",
                    exposures,
                    "",
                )
            )
            created_at += 1
    affected = frozenset(
        node
        for branch, nodes in enumerate(branch_nodes)
        for node in nodes[:true_depths[branch]]
    )
    case = DiscoveryCase(
        f"scacd_multicascade_seed_{seed}", "s", tuple(memories), affected
    )
    case.validate()
    true_world_name = "depths_" + "_".join(str(depth) for depth in true_depths)
    true_world = next(
        index for index, world in enumerate(belief.worlds)
        if world.name == true_world_name
    )
    return MultiCascadeInstance(
        case=case,
        belief=belief,
        true_world=true_world,
        true_depths=true_depths,
        observed_edges=observed_edges_frozen,
        content_signals=content_signals,
        branch_nodes=branch_nodes,
        prevalence=prevalence,
        transmission=transmission,
        q=q,
        r=r,
        sensitivity=sensitivity,
        false_positive_rate=false_positive_rate,
    )


def multicascade_posterior_under_parameters(
    instance: MultiCascadeInstance,
    *,
    q: float,
    r: float,
    prevalence: float | None = None,
    transmission: float | None = None,
    sensitivity: float | None = None,
    false_positive_rate: float | None = None,
) -> FiniteCascadeBelief:
    """Recompute a multi-cascade posterior under declared parameters."""
    return _multicascade_posterior(
        branch_nodes=instance.branch_nodes,
        observed_edges=instance.observed_edges,
        content_signals=instance.content_signals,
        prevalence=instance.prevalence if prevalence is None else prevalence,
        transmission=(
            instance.transmission if transmission is None else transmission
        ),
        q=q,
        r=r,
        sensitivity=(
            instance.sensitivity if sensitivity is None else sensitivity
        ),
        false_positive_rate=(
            instance.false_positive_rate
            if false_positive_rate is None
            else false_positive_rate
        ),
    )


def _log_beta(alpha: float, beta: float) -> float:
    return math.lgamma(alpha) + math.lgamma(beta) - math.lgamma(alpha + beta)


def multicascade_posterior_integrated_channel(
    instance: MultiCascadeInstance,
    *,
    q_alpha: float,
    q_beta: float,
    r_alpha: float,
    r_beta: float,
) -> FiniteCascadeBelief:
    """Marginalize the provenance likelihood over Beta channel posteriors."""
    if min(q_alpha, q_beta, r_alpha, r_beta) <= 0.0:
        raise ValueError("Beta shape parameters must be positive")
    depth_probabilities = _depth_probabilities(
        len(instance.branch_nodes[0]), instance.prevalence, instance.transmission
    )
    depth_worlds = tuple(
        depths
        for depths in product(
            range(len(instance.branch_nodes[0]) + 1),
            repeat=len(instance.branch_nodes),
        )
        if any(depths)
    )
    base_q = _log_beta(q_alpha, q_beta)
    base_r = _log_beta(r_alpha, r_beta)
    log_weights = []
    affected_sets = []
    for depths in depth_worlds:
        log_weight = sum(
            _safe_log_probability(depth_probabilities[depth]) for depth in depths
        )
        retained_true = missing_true = inserted_false = absent_false = 0
        affected = set()
        for branch, nodes in enumerate(instance.branch_nodes):
            depth = depths[branch]
            affected.update(nodes[:depth])
            legal_edges = (("s", nodes[0]),) + tuple(
                (nodes[offset - 1], nodes[offset])
                for offset in range(1, len(nodes))
            )
            for target_offset, edge in enumerate(legal_edges):
                observed = edge in instance.observed_edges
                if depth > target_offset:
                    retained_true += int(observed)
                    missing_true += int(not observed)
                else:
                    inserted_false += int(observed)
                    absent_false += int(not observed)
            for offset, node in enumerate(nodes):
                clue_probability = (
                    instance.sensitivity
                    if offset < depth
                    else instance.false_positive_rate
                )
                log_weight += _bernoulli_log_likelihood(
                    instance.content_signals[node], clue_probability
                )
        log_weight += (
            _log_beta(q_alpha + retained_true, q_beta + missing_true) - base_q
        )
        log_weight += (
            _log_beta(r_alpha + inserted_false, r_beta + absent_false) - base_r
        )
        log_weights.append(log_weight)
        affected_sets.append(frozenset(affected))
    posterior = _normalize_log_weights(log_weights)
    return FiniteCascadeBelief(
        instance.belief.candidates,
        tuple(
            LatentWorld(
                "depths_" + "_".join(str(depth) for depth in depths),
                affected_sets[index],
                posterior[index],
            )
            for index, depths in enumerate(depth_worlds)
        ),
    )


def _safe_log_probability(value: float) -> float:
    if value <= 0.0:
        return -math.inf
    return math.log(value)


def _bernoulli_log_likelihood(observed: int, probability: float) -> float:
    return _safe_log_probability(probability if observed else 1.0 - probability)


def _normalize_log_weights(log_weights: Sequence[float]) -> Tuple[float, ...]:
    maximum = max(log_weights)
    if maximum == -math.inf:
        raise ValueError("observations have zero probability under every world")
    # Preserve structurally possible worlds through several rare conditioning
    # events; exact zero from floating-point underflow would make a valid replay
    # history impossible to condition on.
    shifted = [max(math.exp(value - maximum), 1e-300) for value in log_weights]
    total = sum(shifted)
    return tuple(value / total for value in shifted)


def build_branch_instance(
    *,
    seed: int,
    branches: int = 4,
    branch_size: int = 3,
    q: float = 0.5,
    r: float = 0.2,
    sensitivity: float = 0.75,
    false_positive_rate: float = 0.25,
) -> BranchInstance:
    """Sample a one-contaminated-branch archive and compute its exact posterior.

    Every branch has genuine internal formation links. Only the contaminated
    branch has a true source-to-gateway edge. That edge is observed with
    probability q; clean gateways receive spurious source edges with
    probability r. Each node also has a binary content clue.
    """
    if branches < 2 or branch_size < 2:
        raise ValueError("the branch family requires >=2 branches of size >=2")
    for name, value in {
        "q": q,
        "r": r,
        "sensitivity": sensitivity,
        "false_positive_rate": false_positive_rate,
    }.items():
        if not 0.0 < value < 1.0:
            raise ValueError(f"{name} must lie strictly between zero and one")

    rng = random.Random(seed)
    true_world = rng.randrange(branches)
    source_edges = set()
    content_signals: Dict[str, int] = {}
    observed_internal_edges = set()

    branch_nodes = tuple(
        tuple(f"b{branch}_n{offset}" for offset in range(branch_size))
        for branch in range(branches)
    )
    for branch, nodes in enumerate(branch_nodes):
        source_probability = q if branch == true_world else r
        if rng.random() < source_probability:
            source_edges.add(nodes[0])
        for offset in range(1, branch_size):
            if rng.random() < q:
                observed_internal_edges.add((nodes[offset - 1], nodes[offset]))
        for node in nodes:
            affected = branch == true_world
            clue_probability = sensitivity if affected else false_positive_rate
            content_signals[node] = int(rng.random() < clue_probability)

    log_weights = []
    for candidate_world in range(branches):
        log_weight = -math.log(branches)
        for branch, nodes in enumerate(branch_nodes):
            edge_probability = q if branch == candidate_world else r
            log_weight += _bernoulli_log_likelihood(
                int(nodes[0] in source_edges), edge_probability
            )
            for node in nodes:
                affected = branch == candidate_world
                clue_probability = sensitivity if affected else false_positive_rate
                log_weight += _bernoulli_log_likelihood(
                    content_signals[node], clue_probability
                )
        log_weights.append(log_weight)
    posterior = _normalize_log_weights(log_weights)

    source_tokens = "invalid source policy hazard"
    memories = [ObservableMemory("s", source_tokens, 0)]
    created_at = 1
    for branch, nodes in enumerate(branch_nodes):
        for offset, node in enumerate(nodes):
            clue = content_signals[node]
            content = (
                f"invalid source policy hazard branch{branch} node{offset}"
                if clue
                else f"independent clean routine branch{branch} node{offset}"
            )
            parents = ()
            exposures = ()
            if offset == 0 and node in source_edges:
                exposures = ("s",)
            elif offset > 0 and (nodes[offset - 1], node) in observed_internal_edges:
                parents = (nodes[offset - 1],)
            memories.append(
                ObservableMemory(
                    node,
                    content,
                    created_at,
                    parents,
                    "scacd-up-branch-family",
                    exposures,
                    "",
                )
            )
            created_at += 1

    affected = frozenset(branch_nodes[true_world])
    case = DiscoveryCase(
        f"scacd_branch_seed_{seed}", "s", tuple(memories), affected
    )
    case.validate()
    candidates = tuple(node for nodes in branch_nodes for node in nodes)
    worlds = tuple(
        LatentWorld(f"branch_{branch}", frozenset(nodes), posterior[branch])
        for branch, nodes in enumerate(branch_nodes)
    )
    return BranchInstance(
        case=case,
        belief=FiniteCascadeBelief(candidates, worlds),
        true_world=true_world,
        observed_source_edges=frozenset(source_edges),
        content_signals=content_signals,
        q=q,
        r=r,
        sensitivity=sensitivity,
        false_positive_rate=false_positive_rate,
    )


def exact_policy_value(
    belief: FiniteCascadeBelief,
    budget: int,
    *,
    possible: Tuple[int, ...] | None = None,
    remaining: Tuple[str, ...] | None = None,
) -> Tuple[float, str | None]:
    """Return Bayes-optimal discovery value and first action."""
    possible = tuple(range(len(belief.worlds))) if possible is None else possible
    remaining = belief.candidates if remaining is None else remaining

    @lru_cache(maxsize=None)
    def solve(
        current_possible: Tuple[int, ...], current_remaining: Tuple[str, ...], left: int
    ) -> Tuple[float, str | None]:
        if left <= 0 or not current_remaining:
            return 0.0, None
        best_value = -1.0
        best_node = None
        for node in current_remaining:
            current_weights = belief.normalized_weights(current_possible)
            probability = sum(
                weight
                for index, weight in current_weights.items()
                if node in belief.worlds[index].affected_ids
            )
            next_remaining = tuple(item for item in current_remaining if item != node)
            value = probability
            for label in (1, 0):
                conditioned = belief.condition(current_possible, node, label)
                if not conditioned:
                    continue
                label_probability = sum(
                    current_weights[index] for index in conditioned
                )
                if label_probability <= 0.0:
                    continue
                continuation, _ = solve(conditioned, next_remaining, left - 1)
                value += label_probability * continuation
            if value > best_value + 1e-12 or (
                abs(value - best_value) <= 1e-12
                and (best_node is None or node < best_node)
            ):
                best_value = value
                best_node = node
        return best_value, best_node

    return solve(possible, remaining, min(budget, len(remaining)))


def run_belief_policy(
    belief: FiniteCascadeBelief,
    true_world: int,
    budget: int,
    *,
    horizon: int | None = None,
) -> PolicyRun:
    """Run posterior greedy (horizon=1), finite horizon, or the full oracle."""
    possible = tuple(range(len(belief.worlds)))
    remaining = belief.candidates
    replayed = []
    discovered = set()
    for step in range(min(budget, len(remaining))):
        budget_left = budget - step
        lookahead = budget_left if horizon is None else min(horizon, budget_left)
        _, chosen = exact_policy_value(
            belief,
            lookahead,
            possible=possible,
            remaining=remaining,
        )
        if chosen is None:
            break
        label = int(chosen in belief.worlds[true_world].affected_ids)
        replayed.append(chosen)
        if label:
            discovered.add(chosen)
        possible = belief.condition(possible, chosen, label)
        remaining = tuple(node for node in remaining if node != chosen)
    return PolicyRun(tuple(replayed), frozenset(discovered))
