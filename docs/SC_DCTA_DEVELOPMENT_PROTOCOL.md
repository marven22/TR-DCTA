# Support-Corrected DCTA Development Protocol

## Boundary

Use only the 10 Meta-World development tasks with leave-one-task-out source and
cascade fitting.  Use the citation-consistent development ledgers.  No
validation or test artifact may be read.

## Frozen method

SC-DCTA separates the calibrated target source distribution from the
support-safe particle proposal.

For target source probabilities `p(s)`, use the existing 0.05 per-source floor
only to form the proposal

`q(s) = 0.05 + 0.85 p(s)`

for the three-source setting.  A particle sampled from source `s` receives
importance weight `p(s) / q(s)`.  Conditional provenance, contamination, and
harm draws are unchanged.  Aggregate weighted particles into the posterior and
run the existing probabilistic DCTA risk acquisition.

There is no threshold, mode switch, new feature, regularization search, or
proposal-floor tuning.  Use 2,048 particles and the existing deterministic
seeds.

## Comparisons

- SC-DCTA;
- original floored Prob-DCTA;
- hard-source DCTA under the calibrated target posterior;
- ENS under the support-corrected posterior;
- ENS under the original floored posterior;
- Source-then-DCTA under the support-corrected posterior;
- known-source DCTA;
- full-information oracle.

Primary: budget 4 and 25% missing provenance.  Sensitivities: budgets 2 and 8
and provenance masks 0%, 25%, and 50%.  Cluster comparisons by task.

## Go/no-go criteria

SC-DCTA proceeds as the single final method only if it:

1. remains within 0.01 of the better of hard-source and original Prob-DCTA in
   the primary condition;
2. improves initial source Brier score over the floored posterior;
3. remains within 0.03 of support-corrected ENS in the primary condition;
4. retains at least 85% of known-source performance;
5. is not more than 0.03 below both hard-source and original Prob-DCTA in any
   sensitivity cell; and
6. retains at least 50% effective particle sample size in every archive.

If the held-out development tasks contain an ambiguous-source stratum with
maximum target probability below 0.8, report it separately.  Absence of such a
stratum is a benchmark characteristic and does not authorize synthetic
threshold tuning.

