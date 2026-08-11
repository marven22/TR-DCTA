# Meta-World forced-exposure results: 49-task study

## Status

The frozen exposure-conditioned evaluation completed at replay budgets 2, 4,
and 8 on 10 development, 10 task-cross-fitted validation, and 29 untouched test
tasks. The primary confirmatory result is the 29-task test task-macro estimate.
The all-49 estimate is descriptive because development and validation informed
method construction.

The study contains 919 distinct harmful-descendant exposure episodes:

- development: 182;
- validation: 172;
- test: 565.

Every exposed descendant was placed at retrieval rank one for every method and
was known from prior Meta-World replay to fail on the target task. After the
frozen audit budget, confirmed failed memories were quarantined and the first
surviving memory in the common semantic order was executed.

## Primary untouched 29-task result

| Replays | SC-DCTA task-macro recovery (95% CI) | SC-DCTA episode-micro recovery | Recovery given localization |
|---:|---:|---:|---:|
| 2 | 26.90% [24.60, 29.03] | 26.90% | 95.00% |
| 4 | 51.03% [46.95, 54.73] | 51.15% | 94.75% |
| 8 | 82.11% [76.30, 86.69] | 82.65% | 95.70% |

The held-out curve confirms the development diagnosis: recovery is principally
limited by whether the audit budget reaches the exposed descendant. Once it is
localized, the common quarantine and fallback mechanism succeeds about 95% of
the time.

## ENS shared-posterior comparison on test

| Replays | SC-DCTA | ENS–SharedPosterior | SC-DCTA minus ENS (task-macro 95% CI) |
|---:|---:|---:|---:|
| 2 | 26.90% | 26.57% | +0.33 pp [-0.78, +1.56] |
| 4 | 51.03% | 50.69% | +0.33 pp [-1.40, +2.17] |
| 8 | 82.11% | 82.01% | +0.10 pp [-0.53, +0.76] |

SC-DCTA and ENS–SharedPosterior are statistically and practically tied at all
three budgets. ENS–SharedPosterior is a mechanism-control baseline, not a
faithful end-to-end ENS kNN implementation.

At budget four, hard-source DCTA obtained 50.93%, known-source DCTA 52.60%, and
the full-information oracle 57.98% task-macro recovery. At budget eight those
values were 80.10%, 82.50%, and 89.99%, respectively.

## Split-specific SC-DCTA task-macro recovery

| Split | Tasks | Budget 2 | Budget 4 | Budget 8 |
|---|---:|---:|---:|---:|
| Development | 10 | 29.20% | 52.16% | 84.82% |
| Validation, task-cross-fitted | 10 | 34.69% | 59.09% | 90.32% |
| Test, untouched | 29 | 26.90% | 51.03% | 82.11% |

## Descriptive all-49 result

| Replays | Task-macro recovery (95% CI) | Episode-micro recovery | Localization rate | Recovery given localization |
|---:|---:|---:|---:|---:|
| 2 | 28.96% [26.88, 31.11] | 28.40% | 29.71% | 95.60% |
| 4 | 52.90% [49.50, 56.40] | 52.23% | 54.84% | 95.24% |
| 8 | 84.34% [80.13, 87.88] | 84.22% | 87.38% | 96.39% |

Against ENS–SharedPosterior, the all-49 task-macro differences were +0.58,
+0.18, and -0.42 percentage points at budgets 2, 4, and 8. Every interval
included zero. The correct conclusion remains parity.

## Interpretation and claim boundary

The results support three claims:

1. SC-DCTA produces real behavioral recovery under controlled harmful-memory
   exposure.
2. Recovery increases strongly and monotonically with replay budget.
3. The post-localization remediation step is reliable at approximately 95%.

They do not support a claim that SC-DCTA's acquisition rule beats
ENS–SharedPosterior. The all-49 aggregate is not an untouched test statistic and
must be labeled descriptive. A faithful ENS–kNN system remains a future
end-to-end baseline.

## Reproducibility artifacts

- Freeze: `configs/metaworld_forced_exposure_freeze_v1.json`
- Validation cross-fit audits: `results/sc_dcta_metaworld_validation_crossfit.json`
- Aggregate ledger: `results/metaworld_forced_exposure_all49_aggregate.json`
- Aggregator: `scripts/aggregate_metaworld_forced_exposure.py`
