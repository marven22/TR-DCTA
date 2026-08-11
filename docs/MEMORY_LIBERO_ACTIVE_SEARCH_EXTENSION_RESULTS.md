# Memory-LIBERO Active-Search Extension

## Status

This is a **post-hoc extension** of the external Memory-LIBERO v1 evaluation. The
67 external archives had already been evaluated for DCTA-Risk-Local and
ACIS-Risk. Before running the extension, the two new baseline implementations
and their parameters were frozen using only the papers, reference code where
available, and the original 12-archive development set.

The comparison contains 67 archives, four inspection budgets, and four methods
(1,072 archive-method-budget rows). The audit passes all artifact, completeness,
metric, and prior-result-reuse checks.

## Compared methods

- **DCTA-Risk-Local v1**: the proposed directed, uncertainty-aware inspection
  policy.
- **ACIS-Risk**: the frozen risk-aware predecessor.
- **ENS (shared DCTA posterior)**: the ENS one-step nonmyopic acquisition rule,
  evaluated with the same finite-world posterior as DCTA. This deliberately
  isolates the acquisition policy. It is not presented as an end-to-end
  reproduction of the original ENS k-NN system.
- **Graph Active Search**: a paper-equation implementation using a symmetrized
  formation graph, soft graph labels, and the development-frozen exploration
  weight.

## Macro corruption recall

| Inspection budget | DCTA-Risk-Local | ACIS-Risk | ENS | Graph Active Search |
|---:|---:|---:|---:|---:|
| 2 | 0.3677 | **0.4605** | 0.3066 | 0.2335 |
| 4 (primary) | **0.6322** | 0.6305 | 0.5333 | 0.3107 |
| 6 | **0.7820** | 0.7714 | 0.7524 | 0.5443 |
| 9 | 0.9226 | **0.9233** | 0.9132 | 0.8472 |

At the primary four-inspection budget, DCTA exceeds ENS by 0.0989 macro recall
(paired 95% bootstrap CI: 0.0681 to 0.1324) and Graph Active Search by 0.3214
(CI: 0.2812 to 0.3628). DCTA and ENS have 0/38/29 archive-level
win/tie/loss counts when the comparison is expressed as ENS minus DCTA; hence
DCTA never loses to ENS on an archive at this budget.

The DCTA-versus-ENS difference is also positive at budgets 2 and 6. At budget 9,
the point difference is small (0.0094) and its paired interval reaches zero.

## Interpretation

The strongest result is the controlled ENS comparison. ENS receives DCTA's own
posterior, so the primary-budget gain cannot be attributed merely to a better
probability estimator. It supports the narrower claim that DCTA's acquisition
rule exploits directed corruption-cascade structure more effectively than a
standard nonmyopic active-search objective in this setting.

Graph Active Search performs substantially worse. A plausible mechanism is that
symmetrizing the formation graph discards the causal direction of propagation,
while its graph-only soft labels do not use the semantic and task evidence
available to the memory-specific methods. This is an interpretation, not a
standalone causal finding.

The result does not eliminate DCTA's tight-budget limitation: ACIS-Risk remains
better at budget 2. Nor should this post-hoc extension be described as a new
untouched external test. A final paper should confirm the comparison on a newly
locked domain or fresh archive split.

## Reproducibility artifacts

- Configuration: `configs/active_search_baselines_v1.json`
- Freeze record: `configs/active_search_external_v1_evaluator_freeze.json`
- Baseline implementation: `src/mcx/active_search_baselines.py`
- Evaluation output: `results/memory_libero_external_v1_active_search.json`
- Audit output: `results/memory_libero_external_v1_active_search_validation.json`
- Evaluator: `scripts/run_active_search_external_v1.py`
- Validator: `scripts/validate_active_search_external_v1.py`

Validation: 116 automated tests pass, and the extension audit passes all checks.
