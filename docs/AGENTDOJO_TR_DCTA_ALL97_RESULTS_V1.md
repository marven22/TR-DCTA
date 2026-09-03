# AgentDojo TR-DCTA all-97 results v1

## Status and coverage

**Complete and independently verified.** This descriptive full-dataset run
includes all 97 official AgentDojo v1.2.2 user tasks and screens all 949
within-suite user/injection combinations. It contains 78 three-stage archives
and 19 two-stage archives; no official user task is excluded.

Three executable corruption origins rotate as truth for every user task. The
study contains 291 truth instances, 3,201 provenance views, and 585,783 method
runs. Complete, 33%-missing, and 67%-missing provenance are evaluated at
budgets 2/4/8, with five masks per partial condition and 50 random repetitions.

## Pooled all-97 result at budget four

| Missing provenance | TR-DCTA | ENS | SC-DCTA | Prob-DCTA | Random |
|---:|---:|---:|---:|---:|---:|
| 0% | **1.0000** | 1.0000 | 1.0000 | 1.0000 | 0.9850 |
| 33% | **1.0000** | 0.9952 | 0.9952 | 0.9952 | 0.9554 |
| 67% | **1.0000** | 0.9595 | 0.9567 | 0.9567 | 0.8961 |

At 67% missingness, the paired task-bootstrap difference was +0.0405 over ENS
with 95% interval [0.0282, 0.0543], +0.0433 over SC-DCTA [0.0302, 0.0577],
and +0.1039 over random [0.0936, 0.1141]. TR-DCTA had no task-level losses:
it beat ENS on 35 tasks and tied 62, beat SC-DCTA on 34 and tied 63, and beat
random on all 97.

In raw source-mask cases, TR-DCTA recovered 1,455/1,455 at both partial levels.
At 67%, ENS recovered 1,396/1,455 and SC-DCTA 1,392/1,455. Random recovered
65,189/72,750 replicated cases.

## Stage breakdown at 67% missingness and budget four

| Archive type | Tasks | TR-DCTA | ENS | SC-DCTA | Random |
|---|---:|---:|---:|---:|---:|
| Two-stage | 19 | **1.0000** | 1.0000 | 1.0000 | 0.9805 |
| Three-stage | 78 | **1.0000** | 0.9496 | 0.9462 | 0.8755 |
| All tasks | 97 | **1.0000** | 0.9595 | 0.9567 | 0.8961 |

The two-stage tasks are indeed easier and contribute no TR-DCTA advantage over
the posterior-aware baselines. The separation is carried by the harder
three-stage tasks rather than created by adding short workflows.

## Interpretation and reporting boundary

This result permits the precise statement that TR-DCTA was evaluated on every
official AgentDojo user task. It does not mean that all 949 user/injection
pairs are independent experimental units. All 949 were screened, 589 met the
appropriate executable two- or three-stage qualification rule, and three
origins were deterministically selected per user task. The statistical unit is
the user task, avoiding pseudoreplication of correlated attack pairs.

The original balanced 32-task study remains the method-held-out confirmatory
analysis. This all-97 experiment was designed after those results were seen and
is therefore a descriptive full-coverage analysis. Both agree: TR-DCTA reaches
1.000 primary recovery, and the advantage appears primarily under severe
provenance uncertainty in three-stage archives.

## Verification

The independent verifier accounted for all 97 official tasks and all 949
screened pairs, recomputed all 585,783 row outcomes, and re-executed 1,632
positive/negative workflows. There were zero row or semantic replay failures.

- Raw report: `reports/agentdojo_tr_dcta_all97_v1.json`
- Verification: `reports/agentdojo_tr_dcta_all97_verified_v1.json`
- Report SHA-256: `fd086a5b6c590f35c3f3d96a22f6e4e7f76f5dca2127c128a15407a5b1bb8d63`
