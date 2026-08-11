# Memory-LIBERO Multi-Origin Probability Study v1 Results

## Decision

**The frozen study passed: joint probabilistic source reasoning is supported on model-written, simulator-grounded LIBERO memory cascades.**

Prob-DCTA remains the primary method. It substantially outperformed hard source commitment, modestly but significantly outperformed the strong positive-only joint baseline and the post-hoc prior-weighted ACIS-Risk adaptation, matched ENS, and retained 97.9% of known-source DCTA recall at the primary budget.

This is a derived composite study over existing LIBERO-90 generations. It is not an additional untouched-domain result.

## Dataset and execution

- 67 base LIBERO-90 archives;
- 1,005 composite archives;
- three opaque candidate origins per archive;
- three Qwen-written descendant memories per origin;
- three active-origin rotations and five source-evidence conditions;
- budgets 2, 4, and 6;
- 47 base-archive clusters in the test split;
- 46 positive test clusters and 192 positive primary composite rows;
- exact finite-world posterior inference;
- 27,135 method/budget evaluations;
- 17.4 seconds evaluation time on CPU.

The realized forensic-channel accuracies were 0.741 for the declared 0.75 channel, 0.473 for the 0.50 channel, and 0.214 for the wrong60 channel whose true accuracy was 0.20.

## Primary result

Population: test split, high/medium/uniform calibrated source uncertainty, positive archives, budget 4.

| Method | Recall | Mean discoveries | Audit yield |
|---|---:|---:|---:|
| Random | 0.493 | 0.854 | 0.214 |
| DCTA-Top1 | 0.665 | 1.203 | 0.301 |
| Static joint Risk | 0.797 | 1.193 | 0.298 |
| Prior-weighted ACIS-Risk* | 0.938 | — | — |
| Positive-only joint Risk | 0.944 | 1.635 | 0.409 |
| ENS | 0.976 | 1.708 | 0.427 |
| Source-then-DCTA | 0.977 | 1.714 | 0.428 |
| **Prob-DCTA** | **0.979** | **1.719** | **0.430** |
| Known-source DCTA | 1.000 | 1.781 | 0.445 |

\*ACIS-Risk is a disclosed post-hoc, no-tuning extension using the old frozen calibrator and prior-weighted averaging over possible sources. It was not part of the primary frozen gate.

### Paired cluster-bootstrap comparisons

| Comparison | Difference | 95% interval |
|---|---:|---:|
| Prob-DCTA minus Top1 | +0.314 | [+0.238, +0.396] |
| Prob-DCTA minus Positive-only | +0.034 | [+0.014, +0.058] |
| Prob-DCTA minus prior-weighted ACIS-Risk* | +0.042 | [+0.018, +0.070] |
| Prob-DCTA minus ENS | +0.004 | [-0.005, +0.016] |
| Source-then-DCTA minus Prob-DCTA | -0.001 | [-0.004, 0.000] |

Prob-DCTA never lost to Top1 at the base-cluster level: 35 wins, 11 ties, and zero losses. Against ENS it produced two wins, 43 ties, and one loss, so the correct claim is parity rather than superiority.

## Source identification

On positive primary archives, Prob-DCTA reduced mean source Brier score from 0.565 to 0 and identified the active source perfectly after four replays. This occurs because a harmful descendant is branch-specific and therefore identifies its origin.

Across all calibrated ambiguous test archives, including archives with no harmful descendants, source Brier improved from 0.569 to 0.248 and top-1 source accuracy reached 0.835. Zero-harm archives remain intrinsically harder because all-clean replays can be compatible with multiple origins.

## Budget behavior

### Positive test recall by evidence condition

| Condition | Method | Budget 2 | Budget 4 | Budget 6 |
|---|---|---:|---:|---:|
| High | Top1 | 0.714 | 0.865 | 0.917 |
| High | Prob-DCTA | **0.745** | **0.990** | **1.000** |
| Medium | Top1 | 0.385 | 0.578 | 0.760 |
| Medium | Prob-DCTA | **0.536** | **0.979** | **1.000** |
| Uniform | Top1 | 0.328 | 0.552 | 0.719 |
| Uniform | Prob-DCTA | **0.552** | **0.969** | **1.000** |
| Wrong60 | Top1 | 0.172 | 0.370 | 0.599 |
| Wrong60 | Prob-DCTA | **0.380** | **0.948** | **1.000** |

At budget 2, source uncertainty still imposes a meaningful cost: pooled Prob-DCTA recall is approximately 0.611 versus 0.870 with the source known. At budget 4, adaptive joint methods nearly saturate this nine-memory benchmark. Budget 6 is therefore a ceiling condition rather than a discriminating comparison.

## Frozen gate

All six conditions passed:

1. Prob-DCTA beat Top1 with the bootstrap interval excluding zero.
2. Prob-DCTA beat Positive-only joint Risk.
3. Prob-DCTA remained within 0.03 recall of ENS.
4. A declared joint method retained at least 90% of known-source recall.
5. Prob-DCTA improved source Brier score.
6. The sample-size gate passed.

## Interpretation

The main empirical lesson is that **discarding alternative source hypotheses is expensive**. Clean and harmful descendant replays can redirect a joint posterior, while Top1 cannot recover a source that it removed at the beginning. Positive-only updating recovers much of the performance, but retaining negative evidence provides an additional statistically supported gain.

The controlled go/no-go study suggested a small advantage for Source-then-DCTA at budget 4. That advantage did not transfer here: Prob-DCTA was higher by 0.001 recall, with almost universal ties. We should retain Prob-DCTA as the simpler primary architecture and treat explicit source-first querying as a secondary budget-dependent variant.

## Important limitations

1. The composite cases reuse existing Qwen/LIBERO paired generations. The multi-origin construction is new, but the underlying base archives are not a new external domain.
2. The branches are short, disjoint, and structurally matched. A single positive replay identifies the active origin, making budget 4 close to saturation.
3. Source probabilities come from a controlled noisy forensic channel, not a learned real-world incident detector.
4. The study assumes one active origin and deterministic replay labels.
5. The three rotations from a base archive are dependent; cluster bootstrap handles inference but does not create 1,005 independent tasks.

These limitations do not invalidate the result, but they prevent us from presenting it as the final publication-scale evaluation. The next version should use longer overlapping cascades, partially shared descendants, noisy replay, and independently generated candidate origins. Budget 2 should be emphasized because it remains discriminating.

## Artifacts

- `docs/MEMORY_LIBERO_MULTI_ORIGIN_V1_PROTOCOL.md`
- `configs/prob_dcta_libero_multi_origin_v1.json`
- `src/mcx/prob_dcta_libero.py`
- `src/mcx/prob_dcta_libero_baselines.py`
- `results/prob_dcta_libero_multi_origin_v1_public.json`
- `results/prob_dcta_libero_multi_origin_v1_private.json`
- `results/prob_dcta_libero_multi_origin_v1_evaluation.json`
- `results/prob_dcta_libero_multi_origin_v1_acis_extension.json`
