# BabyAI UnlockPickup terminal-recovery development results v1

## Decision

**Verified GO.** TR-DCTA passed every frozen development gate. Held-out seeds
60--299 remain unopened.

## Scale and controls

- 60 development contexts and 180 provenance views
- complete, 33%-missing, and 67%-missing provenance
- replay budgets 2, 4, and 8
- 12 methods, including 50 random replicates per context-condition-budget
- 32,940 method runs
- identical terminal quarantine optimizer for every deployable method
- unchanged baseline replay trajectories from the pinned v1 report
- independently reconstructed terminal decisions and development metrics

## Primary result

The primary endpoint pools the 120 partial-provenance views at budget four.

| Method | Recoveries | Weighted quarantine recall | Weighted replay-discovery recall |
|---|---:|---:|---:|
| **TR-DCTA** | **110 / 120** | **0.9514** | 0.5958 |
| ENS | 100 / 120 | 0.9056 | **0.8139** |
| SC-DCTA | 95 / 120 | 0.8736 | 0.7139 |
| Prob-DCTA | 95 / 120 | 0.8764 | 0.6903 |
| Hard-source DCTA | 86 / 120 | 0.7944 | 0.7083 |
| Random | mean 75.7 / 120 | 0.7379 | 0.2152 |
| Oracle-source DCTA | 99 / 120 | 0.8944 | 0.8000 |
| Full-information hindsight | 120 / 120 | 1.0000 | 1.0000 |

TR-DCTA improved recovery by 10 cases over ENS, 15 over SC-DCTA, and 34 over
hard-source DCTA. It remained 10 cases below the privileged hindsight ceiling.

## Provenance stress result at budget four

| Missing provenance | TR-DCTA | ENS | SC-DCTA |
|---|---:|---:|---:|
| 33% | 60 / 60 | 60 / 60 | 60 / 60 |
| 67% | **50 / 60** | 40 / 60 | 35 / 60 |

The advantage is entirely concentrated in the harder 67%-missing condition,
where a budget-aware terminal decision has room to matter.

## Budget robustness

Across both partial-provenance conditions:

| Budget | TR-DCTA | ENS | SC-DCTA |
|---|---:|---:|---:|
| 2 | **92 / 120** | 85 / 120 | 79 / 120 |
| 4 | **110 / 120** | 100 / 120 | 95 / 120 |
| 8 | **119 / 120** | 117 / 120 | 116 / 120 |

## Interpretation

TR-DCTA replay-confirmed less weighted corruption than ENS, yet recovered more
robots. This is the central objective-alignment result. A diagnostic replay can
be valuable because its positive or negative outcome distinguishes which
three memories should be quarantined; it need not itself be harmful. ENS is
stronger at collecting positives, while TR-DCTA is stronger at choosing the
final recovery-producing quarantine set.

This does not establish generalization. The result licenses freezing the
method and running the untouched 240-context UnlockPickup held-out study. It
also exposes a computational limitation: exact full-budget rollout took about
five minutes for this development grid and scales exponentially with replay
budget in the worst case.

## Frozen artifacts

- Development report SHA-256:
  `e4a4f6958d02bfa60e745b81818ee6d9b4688e75b0b31b08638a7a3687faec5b`
- Report: `reports/babyai_unlockpickup_terminal_recovery_development_v1.json`
- Verification: `reports/babyai_unlockpickup_terminal_recovery_development_verified_v1.json`
- Method: `src/mcx/terminal_recovery_dcta.py`
- Theory: `docs/THEORY_SPECIFICATION_V0_4_TERMINAL_RECOVERY.md`
