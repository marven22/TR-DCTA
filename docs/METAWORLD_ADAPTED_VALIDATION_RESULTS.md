# Frozen Meta-World Adapted Validation Results

## Status

The frozen adapted pipeline passed all four preregistered validation gates on
10 Meta-World validation tasks.  The evaluation used 90 archive conditions and
a citation-consistent public ledger with 650 hidden-edge citations removed.
All source and cascade parameters and implementation hashes were frozen before
the validation outcomes were joined.

Primary condition: four replays and 25% missing provenance.

## Primary results

| Method/reference | Weighted recall |
|---|---:|
| Full-information four-replay ceiling | 0.752 |
| Adapted hard-source DCTA | **0.685** |
| Adapted known-source DCTA | **0.685** |
| Adapted ENS | 0.670 |
| **Adapted Prob-DCTA** | **0.646** |
| External-source Prob-DCTA | 0.563 |

Adaptation improves Prob-DCTA by 0.0830 over the external-source reference,
with task-cluster interval [0.0495, 0.1226].  It improves on all 10 validation
tasks.

Prob-DCTA trails same-posterior ENS by 0.0241, interval [-0.0790, 0.0044], and
therefore passes the frozen 0.03 noninferiority gate.  It retains 94.3% of
known-source performance and 85.8% of the full-information ceiling.

Initial source Brier improves from 0.684 for the external estimator to 0.114
for the adapted estimator.  The adapted initial source top-1 accuracy is 100%.

## The important negative result

Hard-source DCTA exactly matches known-source DCTA at 0.685 and exceeds
Prob-DCTA by 0.0390.  The task-cluster interval for Prob-DCTA minus hard-source
DCTA is [-0.0950, 0.0000]: Prob-DCTA wins no tasks, ties seven, and loses three.

This is not a failed validation gate because the gate concerned improvement,
ENS noninferiority, source calibration, and known-source retention.  It is,
however, scientifically important.  After domain adaptation, the source is
perfectly ranked before replay on these validation archives.  Maintaining
source uncertainty cannot help in a regime where the observable source signal
already identifies the source, and later noisy replay updates can slightly
reduce performance.

Therefore, this validation supports the adapted posterior but weakens a broad
claim that probabilistic source uncertainty is always preferable to hard
commitment.  The correct conditional claim is that uncertainty-aware inference
helps when source evidence is ambiguous; confident commitment is appropriate
when the source posterior is already concentrated and calibrated.

## Sensitivity

| Budget | Missing provenance | Adapted Prob-DCTA | External Prob-DCTA | Adapted ENS |
|---:|---:|---:|---:|---:|
| 2 | 0% | 0.464 | 0.296 | 0.471 |
| 2 | 25% | 0.436 | 0.239 | 0.465 |
| 2 | 50% | 0.407 | 0.175 | 0.413 |
| 4 | 0% | 0.715 | 0.643 | 0.721 |
| 4 | 25% | 0.646 | 0.563 | 0.670 |
| 4 | 50% | 0.646 | 0.485 | 0.671 |
| 8 | 0% | 0.945 | 0.898 | 0.944 |
| 8 | 25% | 0.927 | 0.898 | 0.919 |
| 8 | 50% | 0.920 | 0.866 | 0.921 |

Adaptation improves Prob-DCTA in all nine sensitivity cells.  At budget eight,
Prob-DCTA matches or slightly exceeds ENS for 0% and 25% missing provenance and
is within 0.002 at 50%.

## Validation decision

The adapted source and cascade model generalizes across the validation task
identities and is suitable for a frozen confirmatory test.  No additional
parameter or acquisition iteration is justified from validation.

The confirmatory study must treat hard-source DCTA as a primary baseline and
must test source-ambiguity strata.  If the fresh archive population again gives
near-perfect initial source ranking, the paper should not claim that Meta-World
demonstrates the value of maintaining source uncertainty.  Instead it supports
calibrated regime selection and strong source-aware containment.

## Artifacts

- Freeze: `configs/prob_dcta_metaworld_adapted_validation_freeze.json`
- Adapted source: `configs/prob_dcta_metaworld_adapted_source_validation.json`
- Adapted cascade: `configs/prob_dcta_metaworld_adapted_cascade_validation.json`
- Corrected public ledger: `results/prob_dcta_metaworld_validation_public_mask_consistent.json`
- Adapted evaluation: `results/prob_dcta_metaworld_adapted_validation_evaluation.json`
- External-source evaluation: `results/prob_dcta_metaworld_external_source_validation_evaluation.json`
- Gate analysis: `results/prob_dcta_metaworld_adapted_validation_analysis.json`

