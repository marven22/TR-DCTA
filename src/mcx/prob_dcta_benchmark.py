"""Controlled latent-origin benchmark for probabilistic DCTA.

The benchmark separates an unobserved corruption origin from the descendant
memories that can be replayed.  Origins are quarantined forensic candidates,
so the fixed replay budget is spent only on descendant memories for every
method.  A replay label updates both the origin posterior and the descendant
states for methods that retain full history.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, FrozenSet, Mapping, Sequence, Tuple

from .active_search_baselines import ens_choice
from .causal_regime_benchmark import PolicyOutcome, exact_weighted_policy_value
from .directional_transition import risk_choice


@dataclass(frozen=True)
class LatentSourceWorld:
    source_id: str
    affected_ids: FrozenSet[str]
    weight: float


@dataclass(frozen=True)
class LatentSourcePosterior:
    candidates: Tuple[str, ...]
    source_ids: Tuple[str, ...]
    worlds: Tuple[LatentSourceWorld, ...]

    def __post_init__(self) -> None:
        if not self.candidates or not self.source_ids or not self.worlds:
            raise ValueError("latent-source posterior cannot be empty")
        if sum(world.weight for world in self.worlds) <= 0.0:
            raise ValueError("posterior mass must be positive")
        if any(world.source_id not in self.source_ids for world in self.worlds):
            raise ValueError("world references an unknown source")

    def normalize(self) -> "LatentSourcePosterior":
        total = sum(world.weight for world in self.worlds)
        return LatentSourcePosterior(
            self.candidates,
            self.source_ids,
            tuple(
                LatentSourceWorld(world.source_id, world.affected_ids, world.weight / total)
                for world in self.worlds if world.weight > 0.0
            ),
        )

    def marginal(self, node: str) -> float:
        total = sum(world.weight for world in self.worlds)
        return sum(
            world.weight for world in self.worlds if node in world.affected_ids
        ) / total

    def condition(self, node: str, label: int) -> "LatentSourcePosterior | None":
        kept = tuple(
            world for world in self.worlds
            if int(node in world.affected_ids) == label
        )
        if not kept:
            return None
        return LatentSourcePosterior(self.candidates, self.source_ids, kept).normalize()

    def restrict_source(self, source_id: str) -> "LatentSourcePosterior":
        kept = tuple(world for world in self.worlds if world.source_id == source_id)
        if not kept:
            raise ValueError("source has zero posterior support")
        return LatentSourcePosterior(self.candidates, self.source_ids, kept).normalize()

    def source_probabilities(self) -> Dict[str, float]:
        total = sum(world.weight for world in self.worlds)
        return {
            source: sum(world.weight for world in self.worlds
                        if world.source_id == source) / total
            for source in self.source_ids
        }

    def source_entropy(self) -> float:
        return -sum(
            probability * math.log(probability)
            for probability in self.source_probabilities().values()
            if probability > 0.0
        )


@dataclass(frozen=True)
class ProbDCTAInstance:
    instance_id: str
    confidence: str
    signaled_source: str
    truth: LatentSourcePosterior
    belief: LatentSourcePosterior
    harm_weights: Mapping[str, float]
    budget: int
    misspecified: bool = False


@dataclass(frozen=True)
class LatentPolicyOutcome:
    replayed_ids: Tuple[str, ...]
    discoveries: int
    weighted_utility: float
    final_posterior: LatentSourcePosterior


def _source_prior(signaled: str, confidence: float) -> Dict[str, float]:
    sources = ("sa", "sb", "sc")
    if not 1.0 / 3.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [1/3, 1]")
    remainder = (1.0 - confidence) / 2.0
    return {source: confidence if source == signaled else remainder for source in sources}


def build_latent_posterior(
    source_prior: Mapping[str, float], *, level: int,
) -> LatentSourcePosterior:
    """Enumerate three matched source-conditioned cascades exactly."""
    if set(source_prior) != {"sa", "sb", "sc"}:
        raise ValueError("exactly three source probabilities are required")
    if any(value < 0.0 for value in source_prior.values()) or not math.isclose(
        sum(source_prior.values()), 1.0, abs_tol=1e-12
    ):
        raise ValueError("invalid source prior")
    if level not in range(4):
        raise ValueError("level must be 0, 1, 2, or 3")

    candidates = tuple(f"{branch}{depth}" for branch in "abc" for depth in (1, 2, 3))
    gateway = (.82, .74, .66, .58)[level]
    transmission = (.90, .84, .78, .72)[level]
    worlds: list[LatentSourceWorld] = []
    for source, source_weight in source_prior.items():
        if source_weight <= 0.0:
            continue
        branch = source[-1]
        chain = (branch + "1", branch + "2", branch + "3")

        def visit(depth: int, affected: set[str], weight: float) -> None:
            if depth == len(chain):
                worlds.append(LatentSourceWorld(
                    source, frozenset(affected), source_weight * weight
                ))
                return
            probability = gateway if depth == 0 else (
                transmission if chain[depth - 1] in affected else 0.0
            )
            if probability < 1.0:
                visit(depth + 1, affected, weight * (1.0 - probability))
            if probability > 0.0:
                affected.add(chain[depth])
                visit(depth + 1, affected, weight * probability)
                affected.remove(chain[depth])

        visit(0, set(), 1.0)
    return LatentSourcePosterior(candidates, ("sa", "sb", "sc"), tuple(worlds)).normalize()


def frozen_prob_dcta_instances() -> Tuple[ProbDCTAInstance, ...]:
    """Return the preregistered calibrated and misspecified factorial."""
    confidence_levels = (("known", 1.0), ("high", .75), ("medium", .50),
                         ("uniform", 1.0 / 3.0))
    instances: list[ProbDCTAInstance] = []
    weights = {f"{branch}{depth}": float(depth)
               for branch in "abc" for depth in (1, 2, 3)}
    for level in range(4):
        for signaled in ("sa", "sb", "sc"):
            for label, confidence in confidence_levels:
                prior = _source_prior(signaled, confidence)
                posterior = build_latent_posterior(prior, level=level)
                instances.append(ProbDCTAInstance(
                    f"matched_l{level}_{signaled}_{label}", label, signaled,
                    posterior, posterior, weights, budget=4,
                ))
            # Deliberately overconfident and wrong: belief assigns .60 to the
            # signaled source while truth assigns it only .20.
            belief = build_latent_posterior(_source_prior(signaled, .60), level=level)
            truth_prior = {source: (.20 if source == signaled else .40)
                           for source in ("sa", "sb", "sc")}
            truth = build_latent_posterior(truth_prior, level=level)
            instances.append(ProbDCTAInstance(
                f"matched_l{level}_{signaled}_wrong60", "wrong60", signaled,
                truth, belief, weights, budget=4, misspecified=True,
            ))
    return tuple(instances)


def _information_gain_choice(
    posterior: LatentSourcePosterior, remaining: Sequence[str],
) -> str:
    before = posterior.source_entropy()
    scores: Dict[str, float] = {}
    for node in remaining:
        probability = posterior.marginal(node)
        expected_after = 0.0
        for label, outcome_probability in ((1, probability), (0, 1.0 - probability)):
            if outcome_probability <= 0.0:
                continue
            conditioned = posterior.condition(node, label)
            if conditioned is not None:
                expected_after += outcome_probability * conditioned.source_entropy()
        scores[node] = before - expected_after
    return min(remaining, key=lambda node: (-scores[node], node))


def run_latent_policy(
    posterior: LatentSourcePosterior,
    true_world: LatentSourceWorld,
    budget: int,
    *,
    method: str,
    weights: Mapping[str, float],
) -> LatentPolicyOutcome:
    """Run one policy without exposing the origin or unqueried labels."""
    allowed = {"prob_dcta", "top1_dcta", "ens", "source_ig", "source_then_dcta",
               "positive_only_risk", "static_risk"}
    if method not in allowed:
        raise ValueError(f"unknown latent-source method: {method}")
    belief = posterior
    if method == "top1_dcta":
        probabilities = belief.source_probabilities()
        selected = min(belief.source_ids, key=lambda source: (-probabilities[source], source))
        belief = belief.restrict_source(selected)
    remaining = list(posterior.candidates)
    replayed: list[str] = []
    total = min(budget, len(remaining))
    for step in range(total):
        if method == "ens":
            chosen = ens_choice(belief, remaining, total - step)
        elif method == "source_ig" or (method == "source_then_dcta" and step == 0):
            chosen = _information_gain_choice(belief, remaining)
        else:
            chosen = risk_choice(belief, remaining, weights)
        replayed.append(chosen)
        remaining.remove(chosen)
        label = int(chosen in true_world.affected_ids)
        should_update = method not in {"static_risk"} and not (
            method == "positive_only_risk" and label == 0
        )
        if should_update:
            conditioned = belief.condition(chosen, label)
            # A collapsed Top-1 model can be contradicted by a positive on a
            # different branch. It cannot recover excluded source support.
            if conditioned is not None:
                belief = conditioned
    discoveries = len(set(replayed) & true_world.affected_ids)
    utility = sum(weights[node] for node in replayed if node in true_world.affected_ids)
    return LatentPolicyOutcome(tuple(replayed), discoveries, utility, belief)


def source_brier(posterior: LatentSourcePosterior, true_source: str) -> float:
    probabilities = posterior.source_probabilities()
    return sum((probabilities[source] - float(source == true_source)) ** 2
               for source in posterior.source_ids)


def evaluate_instance(instance: ProbDCTAInstance) -> Dict[str, Dict[str, float]]:
    methods = ("static_risk", "positive_only_risk", "top1_dcta", "source_ig",
               "source_then_dcta", "ens", "prob_dcta")
    result: Dict[str, Dict[str, float]] = {}
    for method in methods:
        rows = []
        for world in instance.truth.worlds:
            outcome = run_latent_policy(
                instance.belief, world, instance.budget,
                method=method, weights=instance.harm_weights,
            )
            total_harm = sum(instance.harm_weights[node] for node in world.affected_ids)
            source_probabilities = outcome.final_posterior.source_probabilities()
            predicted = min(
                outcome.final_posterior.source_ids,
                key=lambda source: (-source_probabilities[source], source),
            )
            rows.append((world.weight, outcome, total_harm, predicted))
        result[method] = {
            "expected_weighted_utility": sum(w * o.weighted_utility for w, o, _, _ in rows),
            "expected_discoveries": sum(w * o.discoveries for w, o, _, _ in rows),
            "expected_harm_recall": sum(
                w * (o.weighted_utility / total if total > 0.0 else 1.0)
                for w, o, total, _ in rows
            ),
            "source_top1_accuracy": sum(
                w * float(predicted == world.source_id)
                for (w, _, _, predicted), world in zip(rows, instance.truth.worlds)
            ),
            "source_brier": sum(
                w * source_brier(o.final_posterior, world.source_id)
                for (w, o, _, _), world in zip(rows, instance.truth.worlds)
            ),
            "source_entropy": sum(w * o.final_posterior.source_entropy()
                                  for w, o, _, _ in rows),
        }
    result["exact_bayes_oracle"] = {
        "expected_weighted_utility": exact_weighted_policy_value(
            instance.truth, instance.budget, instance.harm_weights
        )
    }
    return result
