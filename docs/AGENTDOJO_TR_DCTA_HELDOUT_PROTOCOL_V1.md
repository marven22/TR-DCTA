# AgentDojo TR-DCTA method-held-out protocol v1

## Status and claim boundary

Frozen before running any method on the evaluation panel. The panel is
method-held-out: no selected user workflow was used in TR-DCTA development.
AgentDojo eligibility labels were necessarily computed during exhaustive
structural screening, so this is not described as a completely unopened or
label-blind dataset.

## Panel

The official AgentDojo package is fixed at version 0.1.35 and benchmark v1.2.2.
All four suites contribute eight archives, for 32 archives total. Every
development user-task ID is excluded before deterministic SHA-256 selection.
Each selected user workflow has three distinct qualifying injection origins
and nine opaque executable descendants. All three origins serve as truth in
turn, producing 96 truth instances.

Every positive replay must execute a graft that satisfies the official
injection evaluator. Every negative replay must execute the clean workflow,
satisfy its utility evaluator, and fail the paired injection objective.

## Multiple-mask design

Complete provenance is evaluated once. The 67%-missing condition is evaluated
under five distinct deterministic mask replicates per archive. If a proposed
replicate duplicates an earlier visible-edge pattern for that archive, its
nonce advances until a new pattern is obtained. Source rotations are
enumerated rather than randomly sampled; cascade lengths and the four source
confidence regimes are exactly balanced.

The experimental unit for inference is the archive. Mask replicates and the
three source rotations are averaged within archive and are never treated as
independent samples.

## Methods, budgets, and endpoint

Budgets are 2, 4, and 8; budget 4 under 67% missing provenance is primary.
Quarantine capacity is three. The frozen comparison includes TR-DCTA,
SC-DCTA, probabilistic and hard-source DCTA, ENS, source information gain,
source-then-DCTA, positive-only DCTA, static risk, 50 random repetitions,
known-source DCTA, and full-information hindsight. Every deployable method
uses the same optimal terminal quarantine operator.

Safe recovery requires every affected descendant to be quarantined and the
verified clean fallback to succeed. Weighted quarantine recall is co-primary.
Replay-discovery recall is mechanistic and secondary.

## Inference

Random repetitions are first averaged within instance, mask, and budget. All
source rotations and masks are then averaged within archive. Ten thousand
paired, suite-stratified archive-bootstrap draws provide 95% intervals for
TR-DCTA minus each primary comparator. Point estimates and intervals are
reported regardless of sign; no method modification follows this run.

## Frozen scale and integrity

Expected scale is 32 archives, 96 truth instances, 576 posterior views, and
105,408 method runs. Required checks include zero development-user overlap,
eight archives per suite, five distinct partial masks per archive, exact
confidence/length balance, positive truth support, executable binary labels,
complete grids, exact budgets, and independent re-execution and aggregation.
