# MemAudit Reconstruction Protocol

## Release status

As checked on 2026-08-05, arXiv:2605.23723v1 does not provide an author code or
data repository. Its reproducibility checklist explicitly states that the
current submission does not provide an anonymized public release. The code in
`src/mcx/memaudit.py` is therefore a paper-level reconstruction, not official
MemAudit code.

## Reproduced components

The implementation follows:

- equation (7): counterfactual memory influence score (CMIS);
- equation (8): consistency anomaly score (CAS);
- equation (10): normalized fusion with the paper default `alpha = 0.6`;
- Algorithm 1: aggregate CMIS across harmful events, compute CAS over the
  unchanged global memory store, fuse once, and rank for batch removal.

Task-specific components are callback interfaces so their provenance remains
visible:

- agent retrieval and counterfactual replay;
- the task-aligned harm scorer;
- semantic embeddings and neighborhood construction;
- the DeBERTa-v3-based NLI inconsistency score.

## Underspecified details

Version 1 does not identify all details needed for code-identical reproduction,
including the semantic embedding checkpoint, the exact NLI checkpoint, graph
neighborhood rule or size, score normalization operator, and some tie-breaking
behavior. This reconstruction uses deterministic lexicographic tie-breaking and
min-max normalization. Any downstream adapter must freeze the remaining choices
before loading external labels.

## LIBERO compatibility boundary

MemAudit assumes a harmful event produced by an agent using a retrieved set of
memories. CMIS then removes each retrieved memory, reruns retrieval and the
agent, and measures the reduction in event harm.

Memory-LIBERO external v1 instead records the physical validity of each
candidate memory's recommended policy. It does not contain a logged agent output
generated jointly from a retrieved memory set, nor counterfactual outputs after
individual deletion. Consequently, affected-memory labels must not be inserted
as CMIS values: doing so would turn MemAudit into a label oracle.

A faithful comparison requires a new adapter that freezes:

1. how the robot-memory agent retrieves a set of memories;
2. how those memories determine a single policy or trajectory;
3. the task-level binary harm definition;
4. replay of the same event after deleting one retrieved memory;
5. whether counterfactual calls count toward the audit budget.

Until that adapter exists, only the paper-level algorithm and the structural
CAS component can be evaluated without leaking private corruption labels.
