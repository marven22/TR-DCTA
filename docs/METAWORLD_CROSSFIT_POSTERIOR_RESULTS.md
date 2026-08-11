# Meta-World Cross-Fitted Posterior Results

## Outcome

The preregistered continuation gate passed all five checks.  A source estimator
fit on nine Meta-World development tasks generalized to the tenth task and
substantially improved the posterior and four-replay containment.  Every task
served as the held-out task once.  No validation or test artifact was read.

Primary condition: four replays, 25% missing provenance, 10 task clusters and
30 task/rotation archives.

## Primary performance

| Posterior model and policy | Weighted recall |
|---|---:|
| Full-information four-replay ceiling from prior diagnostic | 0.748 |
| Known-source cross-fit + Prob-DCTA | 0.641 |
| **Adapted-source cross-fit + Prob-DCTA** | **0.637** |
| Adapted-source cross-fit + ENS | 0.628 |
| Adapted-source cross-fit + exact posterior planning | 0.623 |
| Adapted-source cross-fit + Source-then-DCTA | 0.607 |
| Uniform-source cross-fit + Prob-DCTA | 0.547 |
| External-source cross-fit + Prob-DCTA | 0.542 |
| Frozen current Prob-DCTA | 0.469 |

Relative to the leakage-safe external-source cross-fit reference, source
adaptation improves Prob-DCTA by 0.0957.  The task-cluster bootstrap interval is
[0.0364, 0.1536].  It wins on eight tasks, ties on one, and loses on one.

The adapted method attains 85.2% of the full-information four-replay ceiling
and 99.4% of the corresponding known-source cross-fit score.  These percentages
are descriptive development results, not held-out publication claims.

## Calibration

| Model | Harm-label Brier | Harm ranking AP | Source top-1 | Source Brier |
|---|---:|---:|---:|---:|
| Frozen current | 0.231 | 0.464 | 0.400 | 0.810 |
| External-source cross-fit | 0.209 | 0.571 | 0.400 | 0.808 |
| Uniform-source cross-fit | 0.183 | 0.585 | 0.333 | 0.669 |
| **Adapted-source cross-fit** | **0.099** | **0.850** | **1.000** | **0.094** |
| Known-source cross-fit | 0.080 | 0.889 | 1.000 | 0.000 |

The adapted estimator uses exactly the existing six observable features, L2 of
1.0, and a 0.05 source-probability floor.  No feature or hyperparameter was
selected from fold outcomes.  The largest and highly stable fitted signal is
negative source-to-target similarity: locally successful donor memories tend
to be less aligned with the target task than corrected candidate origins.  The
coefficient pattern is consistent across nine of ten folds.

The cascade refit itself matters.  Replacing the mixed-domain frozen cascade
with a Meta-World-only task-cross-fitted cascade raises the external-source
Prob-DCTA score from 0.469 to 0.542.  Source adaptation supplies the additional
gain to 0.637.

## Sensitivity

Adapted-source minus external-source Prob-DCTA:

| Budget | Missing provenance | Difference |
|---:|---:|---:|
| 2 | 0% | +0.113 |
| 2 | 25% | +0.127 |
| 2 | 50% | +0.159 |
| 4 | 0% | +0.062 |
| 4 | 25% | +0.096 |
| 4 | 50% | +0.178 |
| 8 | 0% | +0.010 |
| 8 | 25% | +0.028 |
| 8 | 50% | +0.090 |

There is no negative cell.  The source prior matters most when the replay
budget is tight or provenance is incomplete; its value shrinks at budget eight
with a complete graph.

## What this does and does not establish

The result shows that the old 67-task LIBERO-trained source estimator transferred
poorly to Meta-World.  Task-cross-fitted domain calibration almost closes the
known-source gap without seeing the held-out task.

It does not yet prove generalization beyond the current Qwen writer and archive
template.  Perfect source top-1 across held-out development tasks is encouraging
but also warns that the active source may carry a stable writer/template signal.
Validation can test new task identities but not a new writer distribution.

The gain also improves ENS from 0.507 to 0.628 under the adapted posterior.
Prob-DCTA remains slightly higher at 0.637, but the principal improvement comes
from the posterior shared by both policies, not from a new acquisition rule.
The contribution should therefore be framed as calibrated causal source and
cascade inference followed by budgeted replay—not as an acquisition-only win.

## Provenance-channel problem

The audit confirmed that 616 masked true edges remain explicitly named in
`cited_memory_ids`, while 104 masked true edges are uncited and no decoy is
cited.  None of the evaluated variants used citation membership.  Nevertheless,
the next archive release must mask citations consistently; otherwise a method
could recover most hidden provenance by reading a structured field.

## Decision

The adapted model is strong enough to freeze as a validation candidate.  Before
validation, create one fixed Meta-World source estimator and cascade fit using
all 10 development tasks, hash the implementation and configuration, and make
no further feature or hyperparameter changes.  Validation should be run once.

Even if validation passes, the final confirmatory archive population must fix
the citation/provenance inconsistency and should include a writer-robustness
condition to test whether source localization relies on template artifacts.

## Reproducibility

- Protocol: `docs/METAWORLD_CROSSFIT_POSTERIOR_PROTOCOL.md`
- Result: `results/prob_dcta_metaworld_development_crossfit.json`
- Runner: `scripts/run_prob_dcta_metaworld_crossfit.py`
- Runtime: approximately 226 seconds

