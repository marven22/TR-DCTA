# Frozen SC-DCTA Meta-World Evaluation Protocol

## Status

This protocol was frozen before executing SC-DCTA on the corrected 29-task
Meta-World evaluation ledger.  The method may not be changed after inspecting
the evaluation result.

## Model fitting

Fit the existing six-feature source estimator and cascade estimator once using
the 20 Meta-World development and validation tasks.  Use only their archives
with fully observed provenance (`provenance_missing_rate = 0`).  No evaluation
task or evaluation label may enter either fit.

## Method

Use SC-DCTA exactly as accepted by the development gate:

- calibrated target source distribution `p(s)` with no probability floor;
- support proposal `q(s) = 0.05 + 0.85 p(s)` for three sources;
- particle importance weight `p(s) / q(s)`;
- 2,048 deterministic particles; and
- the existing probabilistic DCTA risk acquisition.

There is no confidence threshold, hard/probabilistic switch, feature change,
or evaluation-set tuning.

## Evaluation

- Evaluation tasks: 29 Meta-World task identities disjoint from fitting.
- Archives: 261 total (3 rotations x 3 provenance masks x 29 tasks).
- Primary condition: replay budget 4 and 25% missing provenance (87 archives).
- Sensitivities: budgets 2, 4, and 8 crossed with masks 0%, 25%, and 50%.
- Primary metric: archive-mean weighted harmful-memory recall.
- Uncertainty: task-clustered bootstrap interval with 10,000 draws.
- Diagnostics: source top-1 accuracy, source Brier score, particle effective
  sample size, and performance stratified at maximum source probability 0.8.

The 0.8 split is descriptive only and never changes SC-DCTA's behavior.

## Baseline boundary

Run SC-DCTA only.  The existing test baseline artifact is not directly
comparable because it mixes Meta-World and LIBERO and predates citation-mask
correction.  It may not be used for a formal paired claim against this run.
Replaying stored trajectories is unnecessary; any later corrected-baseline
evaluation would be a deterministic ledger-level computation.

