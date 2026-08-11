# Corrected-Ledger Meta-World Baseline Results

## Outcome

On the frozen 29-task primary evaluation, SC-DCTA achieved the highest mean
weighted recall among the external, budget-matched comparison policies.  It
significantly exceeded ACIS-Risk and the original floored Prob-DCTA ablation,
slightly exceeded ENS, and was statistically tied with hard-source DCTA.

## Primary table

Four replays with 25% missing provenance; 87 archives from 29 tasks:

| Method | Role | Weighted recall | Audit yield |
|---|---|---:|---:|
| **SC-DCTA** | Proposed | **0.6297** | **0.8764** |
| Hard-source DCTA | Ablation | 0.6335 | 0.8736 |
| Positive-only DCTA | Ablation | 0.6270 | 0.8649 |
| ENS | Active-search baseline | 0.6198 | 0.8678 |
| Floored Prob-DCTA | Ablation | 0.6149 | 0.8621 |
| Static-risk DCTA | Ablation | 0.6080 | 0.8534 |
| Source-then-DCTA | Sequential baseline | 0.5948 | 0.8132 |
| ACIS-Risk | External baseline | 0.5488 | 0.7816 |
| Source information gain | Sequential baseline | 0.2037 | 0.3017 |
| Random | Baseline | 0.1834 | 0.2989 |
| Known-source DCTA | Information oracle | 0.6560 | 0.8994 |
| Full-information hindsight | Ceiling | 0.7117 | 0.9454 |

Hard-source DCTA is an ablation rather than an external method: it uses the
same fitted posterior components but collapses source uncertainty to the most
probable source.  The known-source and full-information rows receive privileged
information and are ceilings, not competitors.

## Paired comparisons

Task-clustered differences in weighted recall (`SC-DCTA - comparator`):

| Comparator | Difference | Task-clustered 95% CI | Wins / ties / losses |
|---|---:|---:|---:|
| Random | +0.4462 | [0.3969, 0.4927] | 29 / 0 / 0 |
| ACIS-Risk | **+0.0809** | **[0.0389, 0.1226]** | 24 / 0 / 5 |
| ENS | +0.0099 | [-0.0257, 0.0445] | 16 / 7 / 6 |
| Source-then-DCTA | +0.0349 | [-0.0087, 0.0694] | 18 / 8 / 3 |
| Hard-source DCTA | -0.0038 | [-0.0264, 0.0150] | 1 / 26 / 2 |
| Floored Prob-DCTA | **+0.0148** | **[0.0013, 0.0311]** | 5 / 24 / 0 |
| Static-risk DCTA | +0.0217 | [-0.0008, 0.0465] | 12 / 14 / 3 |
| Positive-only DCTA | +0.0027 | [-0.0216, 0.0259] | 2 / 26 / 1 |

The confidence intervals are paired task-clustered bootstrap intervals.  They
are not multiple-comparison-adjusted.  The defensible primary conclusions are:

1. SC-DCTA clearly improves on ACIS-Risk in this setting.
2. Importance correction improves on the old floored probabilistic method.
3. SC-DCTA is competitive with ENS and hard-source DCTA; the data do not show a
   statistically resolved difference among those methods.

## Sensitivity table

Weighted recall for the main comparisons:

| Budget / missing | SC-DCTA | ACIS-Risk | ENS | Hard source | Floored Prob | Known source |
|---|---:|---:|---:|---:|---:|---:|
| 2 / 0% | 0.3846 | 0.3863 | 0.3657 | 0.3776 | 0.3834 | 0.3894 |
| 2 / 25% | 0.3426 | 0.3306 | 0.3331 | 0.3601 | 0.3309 | 0.3702 |
| 2 / 50% | 0.3292 | 0.2876 | 0.3241 | 0.3268 | 0.3233 | 0.3452 |
| 4 / 0% | 0.6648 | 0.6205 | 0.6419 | 0.6531 | 0.6636 | 0.6744 |
| 4 / 25% | **0.6297** | 0.5488 | 0.6198 | 0.6335 | 0.6149 | 0.6560 |
| 4 / 50% | 0.6091 | 0.4998 | 0.6281 | 0.6019 | 0.6053 | 0.6251 |
| 8 / 0% | 0.9134 | 0.9187 | 0.9132 | 0.8918 | 0.9044 | 0.9145 |
| 8 / 25% | 0.8958 | 0.8186 | 0.8997 | 0.8733 | 0.8958 | 0.9025 |
| 8 / 50% | 0.8810 | 0.7778 | 0.8879 | 0.8677 | 0.8813 | 0.8935 |

SC-DCTA is not uniformly best in every sensitivity cell, but it remains near
the leading non-oracle policy throughout.  Its advantage over ACIS-Risk is
largest when provenance is incomplete, while ENS is modestly better in some
high-mask or high-budget cells.

## Interpretation

This is a positive single-domain result.  SC-DCTA combines three properties
that no comparison row simultaneously supplies: calibrated source uncertainty,
support-safe importance sampling, and adaptive cascade-risk replay.  Its main
benefit is not a large win over every nearby DCTA variant; it is a coherent
single formulation that removes the old probability-floor bias while matching
the best hard and nonmyopic alternatives.

The experiment supports a publication claim of competitive or superior
Meta-World performance, not universal state-of-the-art dominance.  Stronger
generality claims still require theory and a second domain.

## Integrity

- 29 tasks and 261 archives.
- 12 methods, 3 budgets, and 3 masks.
- 9,396 unique method/archive/budget rows.
- Every recomputed SC-DCTA replay sequence exactly matched the frozen result.
- Raw artifact: `results/sc_dcta_metaworld_baselines.json`.
- Frozen protocol: `docs/SC_DCTA_METAWORLD_BASELINE_PROTOCOL.md`.
- Frozen configuration: `configs/sc_dcta_metaworld_baseline_freeze.json`.

