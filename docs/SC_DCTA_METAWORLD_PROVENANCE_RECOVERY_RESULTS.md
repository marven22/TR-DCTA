# Meta-World provenance-missingness recovery results

## Result

The frozen 3-mask x 3-budget recovery study completed on all 49 Meta-World
tasks. It contains 27 split-mask-budget cells and reuses 919 identical harmful
exposure episodes per mask-budget condition. All lineage, completeness, and
automated integrity checks passed.

## Primary held-out contrast: four replays

| Missing provenance | SC-DCTA localized | SC-DCTA recovered | SC-DCTA task-macro recovery | ENS–SharedPosterior task-macro recovery | Hard-source task-macro recovery |
|---:|---:|---:|---:|---:|---:|
| 0% | 314 / 565 | 299 / 565 | 53.09% | 51.57% | 52.09% |
| 25% | 305 / 565 | 289 / 565 | 51.03% | 50.69% | 50.93% |
| 50% | 297 / 565 | 282 / 565 | 49.93% | 51.50% | 49.60% |

From 0% to 50% missing provenance, SC-DCTA changed by -3.15 percentage
points, with a task-clustered 95% interval of [-5.57, -1.12]. The decline is
statistically resolved on the 29 held-out tasks.

ENS–SharedPosterior changed by -0.06 points, interval [-1.66, +1.50]. The
difference in degradation, SC-DCTA minus ENS, is -3.09 points with interval
[-5.45, -1.00]. Therefore ENS–SharedPosterior is significantly more robust on
the frozen primary missing-provenance contrast.

SC-DCTA's degradation was not distinguishable from hard-source DCTA's:
the difference in change was -0.66 points, interval [-2.63, +0.64].

## Budget sensitivity on held-out test

| Replays | SC-DCTA change, 50% minus 0% | ENS change | SC-DCTA minus ENS robustness |
|---:|---:|---:|---:|
| 2 | -2.47 pp [-4.41, -0.72] | -2.05 pp [-3.67, -0.59] | -0.42 pp [-1.92, +1.27] |
| 4 | -3.15 pp [-5.57, -1.12] | -0.06 pp [-1.66, +1.50] | -3.09 pp [-5.45, -1.00] |
| 8 | -2.59 pp [-5.03, -0.53] | -2.13 pp [-3.87, -0.65] | -0.45 pp [-1.68, +0.50] |

The relative robustness difference is specific to the primary four-replay
budget. At two and eight replays, SC-DCTA and ENS degrade by similar amounts.

## Descriptive all-49 counts at four replays

| Missing provenance | SC-DCTA localized | SC-DCTA recovered | Benign replay calls | ENS recovered | Hard-source recovered |
|---:|---:|---:|---:|---:|---:|
| 0% | 523 / 919 | 500 / 919 | 65 / 588 | 494 / 919 | 495 / 919 |
| 25% | 504 / 919 | 480 / 919 | 84 / 588 | 479 / 919 | 482 / 919 |
| 50% | 492 / 919 | 469 / 919 | 96 / 588 | 486 / 919 | 475 / 919 |

As links disappear, SC-DCTA spends more of the fixed physical budget on benign
memories and reaches fewer harmful descendants. Target-benign retention remains
100% because quarantine still requires an observed target-task failure.

## Interpretation

The experiment does not support the intended claim that SC-DCTA is more robust
than strong alternatives to missing provenance. Instead it reveals a precise
boundary:

- SC-DCTA is strongest relative to ENS when the graph is complete at budget
  four;
- its directed cascade acquisition relies more heavily on visible formation
  structure;
- the current latent-edge model does not fully compensate when half of that
  structure is hidden;
- ENS's generic nonmyopic acquisition is unusually stable at the primary
  budget.

This negative result must remain in the paper. A defensible claim is that
SC-DCTA supports inference with incomplete provenance and degrades moderately,
not that it dominates under missing provenance. Source-uncertainty and cascade-
depth stratification should next determine which hidden-edge patterns cause the
loss.

## Artifacts

- Freeze: `configs/metaworld_provenance_recovery_freeze_v1.json`
- Result ledger: `results/metaworld_provenance_recovery_all_masks.json`
- Aggregator: `scripts/aggregate_metaworld_provenance_recovery.py`
