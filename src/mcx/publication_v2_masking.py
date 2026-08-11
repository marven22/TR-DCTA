"""Information-consistent masking for publication-v2 public archives."""
from __future__ import annotations

from copy import deepcopy
from typing import Mapping


def mask_hidden_citations(archive: Mapping[str, object]) -> tuple[dict, int]:
    """Remove structured citations whose formation edges are not observed."""
    result = deepcopy(dict(archive))
    observed = {tuple(map(str, edge)) for edge in result["observed_formation_edges"]}
    redactions = 0
    for node, memory in result["memories"].items():
        citations = list(map(str, memory.get("cited_memory_ids", ())))
        retained = [parent for parent in citations if (parent, str(node)) in observed]
        redactions += len(citations) - len(retained)
        memory["cited_memory_ids"] = retained
    return result, redactions


def assert_mask_consistent(archive: Mapping[str, object]) -> None:
    observed = {tuple(map(str, edge)) for edge in archive["observed_formation_edges"]}
    for node, memory in archive["memories"].items():
        for parent in memory.get("cited_memory_ids", ()):
            if (str(parent), str(node)) not in observed:
                raise ValueError(f"citation reveals hidden edge: {parent} -> {node}")

