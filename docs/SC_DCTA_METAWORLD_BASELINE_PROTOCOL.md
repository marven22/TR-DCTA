# Corrected-Ledger Meta-World Baseline Protocol

## Purpose

Recompute compatible comparison policies on the exact corrected 29-task
Meta-World ledger used by frozen SC-DCTA.  No simulator, trajectory, or LLM
generation is repeated.

## Shared conditions

- Use the frozen SC-DCTA evaluation data, 20-task calibrator fit, particles,
  source belief, harm weights, masks, budgets, and deterministic seeds.
- Primary condition: budget 4 and 25% missing provenance.
- Sensitivities: budgets 2, 4, and 8 crossed with 0%, 25%, and 50% missing.
- Compare policies using paired task-clustered bootstrap differences in
  weighted harmful-memory recall with 10,000 draws.
- Do not change SC-DCTA or any baseline after seeing the results.

## Methods

External or established comparators:

- deterministic Random;
- prior-weighted ACIS-Risk with its previously frozen three-signal calibrator;
- ENS with exact finite-posterior outcome integration;
- source information gain; and
- source-then-DCTA.

Method ablations:

- hard-source DCTA;
- original floored Prob-DCTA;
- static-risk DCTA; and
- positive-only-update DCTA.

Information ceilings:

- known-source DCTA; and
- full-information hindsight selection.

MemAudit and MemoRepair are excluded from this ledger-level table because they
consume different observable event/judge or repair inputs.  Their existing
domain-specific evaluations remain separate; fabricating equivalent inputs
from private Meta-World labels would give them information unavailable to the
other methods.

