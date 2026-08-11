"""Oracle policies for publication-v2 replay-allocation diagnostics.

The hindsight oracle knows the realized harmful set.  The Bayes oracle does
not: it receives a finite posterior over harmful sets and computes the exact
adaptive policy maximizing expected weighted discoveries for a small budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from typing import FrozenSet, Mapping, Sequence, Tuple

from .prob_dcta_benchmark import LatentSourcePosterior


@dataclass(frozen=True)
class OracleOutcome:
    replayed_ids: Tuple[str, ...]
    expected_weighted_utility: float
    realized_weighted_utility: float
    zero_support_observations: int
    dynamic_program_states: int


def hindsight_selection(
    candidates: Sequence[str], affected: FrozenSet[str], budget: int,
    weights: Mapping[str, float], *, enumerate_subsets: bool = False,
) -> Tuple[str, ...]:
    """Return the exact best realized set under a fixed replay budget.

    Enumeration is useful as an independently checkable primary-budget
    calculation.  Sorting harmful candidates by nonnegative reward is the
    mathematically equivalent scalable solution used for sensitivity runs.
    """
    if budget < 0:
        raise ValueError("budget must be nonnegative")
    values = tuple(map(str, candidates))
    take = min(budget, len(values))
    if take == 0:
        return ()
    if enumerate_subsets:
        best_score = -1.0
        best: Tuple[str, ...] | None = None
        for subset in combinations(values, take):
            score = sum(float(weights[node]) for node in subset if node in affected)
            if score > best_score + 1e-12 or (
                abs(score - best_score) <= 1e-12 and (best is None or subset < best)
            ):
                best_score, best = score, subset
        assert best is not None
        return best
    ranked = sorted(values, key=lambda node: (
        -float(node in affected),
        -float(weights[node]) if node in affected else 0.0,
        node,
    ))
    return tuple(ranked[:take])


class ExactBayesReplayPlanner:
    """Exact finite-posterior adaptive planner for modest replay budgets."""

    def __init__(
        self, posterior: LatentSourcePosterior, weights: Mapping[str, float],
    ) -> None:
        self.posterior = posterior.normalize()
        self.candidates = tuple(self.posterior.candidates)
        self.worlds = tuple(self.posterior.worlds)
        self.weights = {node: float(weights[node]) for node in self.candidates}
        self._candidate_index = {node: index for index, node in enumerate(self.candidates)}
        self._world_weights = tuple(world.weight for world in self.worlds)
        self._harm_masks = tuple(sum(
            1 << world_index
            for world_index, world in enumerate(self.worlds)
            if node in world.affected_ids
        ) for node in self.candidates)
        self._all_worlds = (1 << len(self.worlds)) - 1
        self._all_candidates = (1 << len(self.candidates)) - 1
        self._solve = self._build_solver()

    def _build_solver(self):
        world_weights = self._world_weights
        weights = self.weights
        candidates = self.candidates
        harm_masks = self._harm_masks
        mass_cache: dict[int, float] = {0: 0.0}

        def mass(mask: int) -> float:
            cached = mass_cache.get(mask)
            if cached is not None:
                return cached
            value = 0.0
            remaining = mask
            while remaining:
                bit = remaining & -remaining
                value += world_weights[bit.bit_length() - 1]
                remaining ^= bit
            mass_cache[mask] = value
            return value

        @lru_cache(maxsize=None)
        def solve(
            possible: int, remaining: int, left: int,
        ) -> tuple[float, int | None]:
            if left <= 0 or not remaining or not possible:
                return 0.0, None
            total = mass(possible)
            best_value, best_index = -1.0, None
            candidate_bits = remaining
            while candidate_bits:
                candidate_bit = candidate_bits & -candidate_bits
                index = candidate_bit.bit_length() - 1
                node = candidates[index]
                positive = possible & harm_masks[index]
                negative = possible ^ positive
                positive_mass = mass(positive)
                probability = positive_mass / total
                rest = remaining ^ candidate_bit
                value = probability * weights[node]
                if positive:
                    continuation, _ = solve(positive, rest, left - 1)
                    value += probability * continuation
                if negative:
                    continuation, _ = solve(negative, rest, left - 1)
                    value += (1.0 - probability) * continuation
                if value > best_value + 1e-12 or (
                    abs(value - best_value) <= 1e-12
                    and (best_index is None or node < candidates[best_index])
                ):
                    best_value, best_index = value, index
                candidate_bits ^= candidate_bit
            return best_value, best_index

        return solve

    def expected_value(self, budget: int) -> float:
        if budget < 0:
            raise ValueError("budget must be nonnegative")
        value, _ = self._solve(
            self._all_worlds, self._all_candidates,
            min(budget, len(self.candidates)),
        )
        return value

    def run(self, true_affected: FrozenSet[str], budget: int) -> OracleOutcome:
        """Follow the exact policy along one realized sequence of labels.

        If the realized label has zero posterior support, the observation is
        recorded and the planner retains its preceding belief, matching the
        conservative behavior of the publication evaluator under particle
        support mismatch.
        """
        if budget < 0:
            raise ValueError("budget must be nonnegative")
        possible = self._all_worlds
        remaining = self._all_candidates
        left = min(budget, len(self.candidates))
        expected, _ = self._solve(possible, remaining, left)
        replayed: list[str] = []
        collapses = 0
        while left > 0 and remaining:
            _, chosen_index = self._solve(possible, remaining, left)
            if chosen_index is None:
                break
            chosen = self.candidates[chosen_index]
            replayed.append(chosen)
            label = int(chosen in true_affected)
            positive = possible & self._harm_masks[chosen_index]
            compatible = positive if label else possible ^ positive
            if compatible:
                possible = compatible
            else:
                collapses += 1
            remaining ^= 1 << chosen_index
            left -= 1
        realized = sum(self.weights[node] for node in replayed if node in true_affected)
        return OracleOutcome(
            tuple(replayed), expected, realized, collapses,
            self._solve.cache_info().currsize,
        )
