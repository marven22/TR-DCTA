"""Transparent reimplementation of the public MemoRepair algorithm.

This module implements the contract and exact fixed-lambda selector described in
arXiv:2605.07242v1.  It is not the authors' code: their per-benchmark candidate
values, costs, operators, and validation suites are not public.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    kind: str = "record"
    architecture: Optional[str] = None
    replayable: bool = True
    support_sufficient: bool = True
    param_partitions_available: bool = False
    operator_available: bool = True
    value: float = 1.0
    cost: float = 1.0


@dataclass(frozen=True)
class Candidate:
    artifact_id: str
    mode: str
    predecessors: Tuple[str, ...]
    executable: bool
    value: float
    cost: float


@dataclass(frozen=True)
class RepairPlan:
    cascade: frozenset[str]
    descendants: frozenset[str]
    barrier: frozenset[str]
    candidates: Mapping[str, Candidate]
    selected: frozenset[str]
    execution_order: Tuple[str, ...]
    republished: frozenset[str]
    validation_failed: frozenset[str]


def affected_cascade(
    roots: Iterable[str], influence_edges: Iterable[Tuple[str, str]]
) -> Set[str]:
    """Return zero-hop roots and all descendants through influence edges."""
    children: Dict[str, Set[str]] = {}
    for source, target in influence_edges:
        children.setdefault(source, set()).add(target)
    found = set(roots)
    queue = deque(sorted(found))
    while queue:
        for child in sorted(children.get(queue.popleft(), ())):
            if child not in found:
                found.add(child)
                queue.append(child)
    return found


def assign_mode(artifact: Artifact) -> str:
    """Paper's deterministic artifact-aware mode map."""
    if not artifact.operator_available:
        return "remove"
    if artifact.kind in {"record", "cache"}:
        return "recompute" if artifact.replayable else "remove"
    if artifact.kind == "summary":
        return "regen" if artifact.support_sufficient else "remove"
    if artifact.kind == "skill":
        if artifact.architecture == "neural":
            return "param" if artifact.param_partitions_available else "remove"
        if artifact.architecture in {"prompt", "chain"}:
            return "regen" if artifact.support_sufficient else "remove"
    return "remove"


class _Dinic:
    def __init__(self, size: int) -> None:
        self.graph: list[list[list[float | int]]] = [[] for _ in range(size)]

    def add_edge(self, source: int, target: int, capacity: float) -> None:
        forward: list[float | int] = [target, capacity, len(self.graph[target])]
        reverse: list[float | int] = [source, 0.0, len(self.graph[source])]
        self.graph[source].append(forward)
        self.graph[target].append(reverse)

    def max_flow(self, source: int, sink: int) -> float:
        total = 0.0
        while True:
            level = [-1] * len(self.graph)
            level[source] = 0
            queue = deque([source])
            while queue:
                node = queue.popleft()
                for target, capacity, _ in self.graph[node]:
                    target = int(target)
                    if float(capacity) > 1e-12 and level[target] < 0:
                        level[target] = level[node] + 1
                        queue.append(target)
            if level[sink] < 0:
                return total
            cursor = [0] * len(self.graph)

            def send(node: int, amount: float) -> float:
                if node == sink:
                    return amount
                while cursor[node] < len(self.graph[node]):
                    edge = self.graph[node][cursor[node]]
                    target, capacity, reverse_index = int(edge[0]), float(edge[1]), int(edge[2])
                    if capacity > 1e-12 and level[target] == level[node] + 1:
                        pushed = send(target, min(amount, capacity))
                        if pushed > 1e-12:
                            edge[1] = capacity - pushed
                            reverse = self.graph[target][reverse_index]
                            reverse[1] = float(reverse[1]) + pushed
                            return pushed
                    cursor[node] += 1
                return 0.0

            while True:
                pushed = send(source, float("inf"))
                if pushed <= 1e-12:
                    break
                total += pushed

    def reachable(self, source: int) -> Set[int]:
        found = {source}
        queue = deque([source])
        while queue:
            node = queue.popleft()
            for target, capacity, _ in self.graph[node]:
                target = int(target)
                if float(capacity) > 1e-12 and target not in found:
                    found.add(target)
                    queue.append(target)
        return found


def maximum_predecessor_closure(
    candidates: Mapping[str, Candidate], lambda_cost: float = 0.3
) -> Set[str]:
    """Solve MemoRepair's scalarized publication selector with one min-cut."""
    ids = sorted(candidates)
    index = {artifact_id: offset + 2 for offset, artifact_id in enumerate(ids)}
    source, sink = 0, 1
    network = _Dinic(len(ids) + 2)
    profits = {
        artifact_id: candidate.value - lambda_cost * candidate.cost
        for artifact_id, candidate in candidates.items()
    }
    finite_capacity = sum(abs(value) for value in profits.values())
    infinity = finite_capacity + 1.0
    for artifact_id in ids:
        candidate = candidates[artifact_id]
        node = index[artifact_id]
        profit = profits[artifact_id]
        if profit > 0:
            network.add_edge(source, node, profit)
        elif profit < 0:
            network.add_edge(node, sink, -profit)
        if not candidate.executable:
            network.add_edge(node, sink, infinity)
        for predecessor in candidate.predecessors:
            if predecessor in index:
                network.add_edge(node, index[predecessor], infinity)
    network.max_flow(source, sink)
    reachable = network.reachable(source)
    return {
        artifact_id for artifact_id, node in index.items()
        if node in reachable and candidates[artifact_id].executable
    }


def _topological_order(
    selected: Set[str], candidates: Mapping[str, Candidate]
) -> Tuple[str, ...]:
    indegree = {node: 0 for node in selected}
    children: Dict[str, Set[str]] = {node: set() for node in selected}
    for node in selected:
        for predecessor in candidates[node].predecessors:
            if predecessor in selected:
                indegree[node] += 1
                children[predecessor].add(node)
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    ordered = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for child in sorted(children[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return tuple(ordered)


def plan_repair(
    artifacts: Mapping[str, Artifact],
    influence_edges: Iterable[Tuple[str, str]],
    roots: Iterable[str],
    lambda_cost: float = 0.3,
    validation: Optional[Mapping[str, bool]] = None,
) -> RepairPlan:
    """Run the public MemoRepair contract through validated republication."""
    edges = set(influence_edges)
    roots_set = set(roots)
    cascade = affected_cascade(roots_set, edges)
    descendants = cascade - roots_set
    raw_modes = {node: assign_mode(artifacts[node]) for node in descendants}
    nonremoved = {node for node, mode in raw_modes.items() if mode != "remove"}
    affected_parents = {
        node: {source for source, target in edges if target == node and source in descendants}
        for node in descendants
    }
    executable = {
        node: artifacts[node].operator_available
        and not bool(affected_parents[node] - nonremoved)
        for node in nonremoved
    }
    # Cycles and all candidates depending on a non-executable candidate cannot run.
    provisional = {
        node: Candidate(
            node, raw_modes[node], tuple(sorted(affected_parents[node])),
            executable[node], artifacts[node].value, artifacts[node].cost,
        )
        for node in nonremoved
    }
    order = _topological_order(set(nonremoved), provisional)
    cyclic = nonremoved - set(order)
    for node in cyclic:
        executable[node] = False
    changed = True
    while changed:
        changed = False
        for node in nonremoved:
            if executable[node] and any(
                predecessor in nonremoved and not executable[predecessor]
                for predecessor in affected_parents[node]
            ):
                executable[node] = False
                changed = True
    candidates = {
        node: Candidate(
            node, raw_modes[node], tuple(sorted(affected_parents[node])),
            executable[node], artifacts[node].value, artifacts[node].cost,
        )
        for node in nonremoved
    }
    selected = maximum_predecessor_closure(candidates, lambda_cost)
    execution_order = _topological_order(selected, candidates)
    validation = validation or {}
    republished: Set[str] = set()
    failed: Set[str] = set()
    for node in execution_order:
        if any(predecessor in selected and predecessor not in republished
               for predecessor in candidates[node].predecessors):
            failed.add(node)
        elif validation.get(node, True):
            republished.add(node)
        else:
            failed.add(node)
    return RepairPlan(
        frozenset(cascade), frozenset(descendants), frozenset(cascade),
        candidates, frozenset(selected), execution_order,
        frozenset(republished), frozenset(failed),
    )

