# BabyAI UnlockPickup TR-DCTA held-out results v1

## Status

**Complete, confirmatory, and independently verified.** The frozen TR-DCTA
method was evaluated once on all 240 previously untouched UnlockPickup contexts
(seeds 60--299). Every integrity and independent verification check passed.

## Scale

- 240 held-out contexts
- 4,320 executable memory outcomes
- 720 provenance views
- complete, 33%-missing, and 67%-missing provenance
- replay budgets 2, 4, and 8
- 11 structured methods plus 50 random replicates
- 131,760 method runs
- 80 contexts at each corruption-cascade length
- 60 contexts in each source-confidence regime

## Primary confirmatory result

The prespecified primary analysis averages the two partial-provenance views
within each context at budget four.

| Method | Recovery | Weighted quarantine recall | Weighted replay-discovery recall |
|---|---:|---:|---:|
| **TR-DCTA** | **0.8875** | **0.9365** | 0.6215 |
| ENS | 0.8646 | 0.9194 | **0.8382** |
| Known-source DCTA | 0.8542 | 0.9111 | 0.7986 |
| Probabilistic DCTA | 0.8375 | 0.9028 | 0.6833 |
| SC-DCTA | 0.8333 | 0.9021 | 0.6979 |
| Source-then DCTA | 0.8042 | 0.8819 | 0.6878 |
| Positive-only DCTA | 0.7292 | 0.8142 | 0.7083 |
| Hard-source DCTA | 0.7021 | 0.7795 | 0.6642 |
| Random | 0.6520 | 0.7513 | 0.2225 |
| Static risk | 0.4125 | 0.5181 | 0.6014 |
| Full-information hindsight | 1.0000 | 1.0000 | 1.0000 |

TR-DCTA minus SC-DCTA recovery was 0.0542 with paired cluster-bootstrap 95%
interval [0.0292, 0.0813]. TR-DCTA minus ENS was 0.0229 [0.0021, 0.0438].
Both prespecified superiority criteria passed. Weighted quarantine recall also
favored TR-DCTA over SC-DCTA by 0.0344 [0.0167, 0.0528] and over ENS by 0.0170
[0.0042, 0.0302].

## Condition-specific recovery counts

| Missing provenance | Budget | TR-DCTA | SC-DCTA | ENS |
|---|---:|---:|---:|---:|
| 33% | 2 | **229 / 240** | 190 / 240 | 209 / 240 |
| 33% | 4 | **238 / 240** | 236 / 240 | **238 / 240** |
| 33% | 8 | 240 / 240 | 240 / 240 | 239 / 240 |
| 67% | 2 | **142 / 240** | 116 / 240 | 133 / 240 |
| 67% | 4 | **188 / 240** | 164 / 240 | 177 / 240 |
| 67% | 8 | **238 / 240** | 224 / 240 | 227 / 240 |

All three methods recovered 240/240 complete-provenance contexts at every
budget.

At 33% missing provenance and budget four, TR-DCTA tied ENS and exceeded
SC-DCTA by only two cases; neither condition-specific interval established
superiority. At 67% missing provenance, TR-DCTA exceeded SC-DCTA by 24 cases
(difference 0.1000 [0.0542, 0.1500]) and ENS by 11 cases (0.0458 [0.0083,
0.0833]). The pooled confirmatory advantage is therefore driven principally,
but not exclusively across budgets, by severe provenance uncertainty.

## Interpretation

The untouched evaluation confirms the development claim. ENS remains much
better at replay-confirming harmful memories, but TR-DCTA makes better final
quarantine decisions and recovers more robots. This directly supports the
paper's distinction between corruption discovery and remediation-oriented
auditing.

The effect is appropriately bounded. TR-DCTA does not improve an already
saturated complete-provenance setting, ties ENS at the primary budget under
moderate missingness, and remains below the full-information ceiling. Its clear
advantage appears when limited replay must resolve substantial provenance and
source uncertainty.

## Verification and frozen artifacts

- Held-out report SHA-256:
  `e7a8e1b3c80679684e8798a33d123af32429a5eaed29a4b9bdbaa31bff13b5d5`
- Report: `reports/babyai_unlockpickup_terminal_recovery_heldout_v1.json`
- Independent verification:
  `reports/babyai_unlockpickup_terminal_recovery_heldout_verified_v1.json`
- Verification SHA-256:
  `a2c060b3e145a771777ad3d8786aa05f893dfaaf97271aa983954fb23dced84f`
