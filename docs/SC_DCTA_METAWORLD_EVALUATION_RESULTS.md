# Frozen SC-DCTA Meta-World Evaluation Results

## Outcome

Frozen SC-DCTA completed the corrected 29-task Meta-World evaluation without
any post-result method change.  In the primary condition it recovered 0.6297
of weighted harmful memory using four replays.  The task-clustered 95%
bootstrap interval is `[0.5828, 0.6717]`.

This is evidence that the method generalizes to 29 task identities excluded
from calibrator fitting.  A subsequent frozen follow-up recomputed compatible
baselines on this corrected ledger; see
`docs/SC_DCTA_METAWORLD_BASELINE_RESULTS.md`.

## Frozen protocol

- Calibrator fitting: 20 Meta-World development and validation tasks.
- Evaluation: 29 disjoint Meta-World tasks.
- Archives: 261 total; 87 in each provenance-mask condition.
- Primary: four replays and 25% missing provenance.
- Posterior: 2,048 importance-corrected particles.
- Citation correction: 1,825 provenance-revealing citations redacted.
- Baselines in this initial artifact: no.  Corrected baselines were recomputed
  in the subsequent paired artifact.

## Primary result

| Metric | Result |
|---|---:|
| Weighted harmful-memory recall | **0.6297** |
| Unweighted harmful-memory recall | 0.6274 |
| Task-clustered 95% interval | [0.5828, 0.6717] |
| Evaluation tasks | 29 |
| Primary archives | 87 |
| Final source Brier score | 0.0208 |

Each archive contains 21 replay candidates.  SC-DCTA inspected four of them
and recovered approximately 63% of the weighted harmful set.

## Source inference and particle quality

| Diagnostic | Result |
|---|---:|
| Initial source top-1 accuracy | 0.9655 |
| Target source Brier score | 0.0453 |
| Particle source Brier score | 0.0452 |
| Mean target-to-particle L1 error | 0.0038 |
| Mean effective particle fraction | 0.9204 |
| Minimum effective particle fraction, all archives | 0.8867 |

The importance sampler accurately represented the intended source belief and
did not suffer material particle collapse.

## Budget and provenance sensitivity

Weighted harmful-memory recall:

| Replay budget | 0% missing | 25% missing | 50% missing |
|---:|---:|---:|---:|
| 2 | 0.3846 | 0.3426 | 0.3292 |
| 4 | 0.6648 | **0.6297** | 0.6091 |
| 8 | 0.9134 | 0.8958 | 0.8810 |

Performance changes monotonically in the expected directions: more replay
budget improves discovery, while more missing provenance reduces it.  At the
primary four-replay budget, moving from complete provenance to 50% missing
provenance reduced recall by 0.0557.

## Confidence-stratified diagnostic

The 0.8 boundary was frozen as a reporting stratum and never altered the
method.

| Source-confidence stratum | Archives | Tasks represented | Weighted recall |
|---|---:|---:|---:|
| Confident (`max p >= 0.8`) | 79 | 27 | 0.6509 |
| Ambiguous (`max p < 0.8`) | 8 | 3 | 0.4201 |

All 79 confident archives had the correct top-ranked source.  Only five of the
eight ambiguous archives did.  The three incorrect source rankings averaged
0.3595 recall.

The ambiguous result is a real limitation, but only eight archives from three
tasks populate the stratum.  It does not support a claim that SC-DCTA solves
severe source ambiguity, nor is it sufficient to conclude that probabilistic
reasoning is ineffective there.  No threshold or method adjustment may now be
made from these cases.

## Baseline compatibility audit

The previous test evaluation contains the same 29 Meta-World tasks plus 12
LIBERO tasks, but it was generated before citation-mask correction.  Comparing
its scores formally with this corrected SC-DCTA run would mix different public
information conditions.  Those stored scores remain historical context, not a
paired publication comparison.

Corrected baseline policies were subsequently recomputed from the fixed
ledgers without regenerating trajectories, simulator rollouts, or LLM outputs.
SC-DCTA obtained 0.6297 weighted recall, compared with 0.6198 for ENS, 0.5488
for ACIS-Risk, and 0.6149 for the original floored Prob-DCTA.  The paired
analysis and limitations are recorded in
`docs/SC_DCTA_METAWORLD_BASELINE_RESULTS.md`.

## Reproducibility

- Frozen protocol: `docs/SC_DCTA_METAWORLD_EVALUATION_PROTOCOL.md`
- Frozen configuration: `configs/sc_dcta_metaworld_evaluation_freeze.json`
- Runner: `scripts/run_sc_dcta_metaworld_evaluation.py`
- Corrected public ledger:
  `results/prob_dcta_metaworld_test_public_mask_consistent.json`
- Corrected private ledger:
  `results/prob_dcta_metaworld_test_private_mask_consistent.json`
- Raw result: `results/sc_dcta_metaworld_evaluation.json`

The result contains 783 unique policy rows and 261 posterior diagnostics.  All
nine budget/mask cells contain 87 archives and all 29 tasks.  The full
automated suite passes: 161 tests.
