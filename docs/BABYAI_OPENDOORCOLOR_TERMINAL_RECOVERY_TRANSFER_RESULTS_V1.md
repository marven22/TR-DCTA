# BabyAI OpenDoorColor TR-DCTA transfer results v1

## Status

**Complete and independently verified locked retrospective transfer.** This is
paper-usable cross-task transfer evidence, but not a new confirmatory held-out
test because the OpenDoorColor benchmark had already been examined before
TR-DCTA was frozen on UnlockPickup development.

## Scale and controls

- 240 OpenDoorColor contexts (seeds 60--299)
- 720 paired provenance views
- budgets 2, 4, and 8
- 9 structured methods and 50 random replicates
- 127,440 method runs
- all prior baseline replay trajectories reproduced exactly
- identical terminal quarantine optimizer for every deployable method
- no environment, archive, mask, label, prior, or TR-DCTA parameter regenerated

## Primary budget-four result

| Provenance | Method | Recoveries | Quarantine recall | Replay discovery recall |
|---|---|---:|---:|---:|
| 33% missing | **TR-DCTA** | **240 / 240** | **1.000** | 0.490 |
| 33% missing | SC-DCTA | 236 / 240 | 0.994 | 0.942 |
| 33% missing | ENS | 236 / 240 | 0.994 | **0.953** |
| 33% missing | Random | mean 183.3 / 240 | 0.848 | 0.223 |
| 67% missing | **TR-DCTA** | **150 / 240** | **0.793** | 0.443 |
| 67% missing | SC-DCTA | 126 / 240 | 0.765 | 0.599 |
| 67% missing | ENS | 128 / 240 | 0.749 | **0.606** |
| 67% missing | Random | mean 95.4 / 240 | 0.617 | 0.222 |

At 33% missing provenance, TR-DCTA improved recovery over SC-DCTA and ENS by
4/240 cases. The paired recovery difference was 0.0167 with descriptive 95%
bootstrap interval [0.0042, 0.0333].

At 67% missing provenance, TR-DCTA improved recovery by 24/240 over SC-DCTA
(difference 0.1000, interval [0.0542, 0.1458]) and by 22/240 over ENS
(difference 0.0917, interval [0.0458, 0.1375]).

## Budget robustness

| Missing provenance | Budget | TR-DCTA | SC-DCTA | ENS |
|---|---:|---:|---:|---:|
| 33% | 2 | **227 / 240** | 183 / 240 | 182 / 240 |
| 33% | 4 | **240 / 240** | 236 / 240 | 236 / 240 |
| 33% | 8 | 240 / 240 | 240 / 240 | 240 / 240 |
| 67% | 2 | **94 / 240** | 78 / 240 | 72 / 240 |
| 67% | 4 | **150 / 240** | 126 / 240 | 128 / 240 |
| 67% | 8 | **236 / 240** | 208 / 240 | 215 / 240 |

All three methods recovered 240/240 cases under complete provenance at every
budget, as expected from the easy reference condition.

## Interpretation

TR-DCTA transfers without adaptation and improves recovery at every
partial-provenance budget. As in UnlockPickup development, it often discovers
fewer harmful memories during replay than SC-DCTA or ENS. It instead uses clean
and harmful replay outcomes to identify the correct final three-memory
quarantine set. This repeat observation supports the paper's central
discovery-versus-remediation distinction.

The result does not replace the need for untouched confirmation. The next
clean test is the still-unopened 240-context UnlockPickup evaluation.

## Frozen artifacts

- Report SHA-256:
  `38b765ff85fd731bb167c8ccad7bf941de7c91c08fdee422905315e4b6380595`
- Report: `reports/babyai_opendoorcolor_terminal_recovery_transfer_v1.json`
- Verification: `reports/babyai_opendoorcolor_terminal_recovery_transfer_verified_v1.json`
