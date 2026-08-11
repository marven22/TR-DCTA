# MetaWorld TR-DCTA 10-task bridge: verified results

## Status

**EXECUTABLE and independently verified.** This is a frozen retrospective bridge on the 10-task MetaWorld development partition. TR-DCTA was not tuned on MetaWorld. The experiment tests whether the terminal-recovery objective selected on BabyAI transfers to the previously frozen MetaWorld recovery contract.

This is evidence for cross-domain transfer and a gate for the full MetaWorld retrospective. It is not a new held-out MetaWorld result.

## Frozen experimental unit

- 10 MetaWorld tasks.
- 3 source rotations per task, giving 30 archives.
- 25% missing provenance and a budget of 4 distinct physical replays.
- 182 forced-exposure episodes: each affected memory is forced to be the retrieved rank-1 memory once.
- Only replay-confirmed harmful memories may be quarantined.
- After quarantine, the robot executes the first surviving memory in the frozen semantic ranking.

The MetaWorld adapter preserves the TR-DCTA principle but uses the domain's existing endpoint. It plans across the full replay budget to maximize expected behavioral recovery, with expected anchor quarantine as the tie-break. It does not import BabyAI's fixed quarantine-capacity abstraction.

## Main results

| Method | Harmful anchors quarantined | Robot recoveries | Successful fallback after quarantine | Harmful fallbacks |
|---|---:|---:|---:|---:|
| **TR-DCTA** | **110/182** | **106/182** | **106/110** | **4** |
| SC-DCTA | 101/182 | 93/182 | 93/101 | 8 |
| SC-ENS | 100/182 | 92/182 | 92/100 | 8 |
| Source-then DCTA | 95/182 | 87/182 | 87/95 | 8 |
| Full-information oracle | 112/182 | 108/182 | 108/112 | 4 |

TR-DCTA therefore produced 13 more recoveries than SC-DCTA and 14 more than SC-ENS. It reached 106 of the oracle's 108 recoveries, while requiring no full-information provenance oracle.

TR-DCTA also retained strong corruption discovery: its archive-macro weighted affected-memory recall was 0.721, versus 0.650 for SC-DCTA, 0.640 for SC-ENS, and 0.748 for the full-information oracle in the frozen development audit.

## Task-clustered paired inference

The bootstrap resamples the 10 tasks, keeping rotations and exposure episodes clustered within their task.

| Behavioral-recovery contrast | Task-macro difference | 95% interval | Task wins/ties/losses |
|---|---:|---:|---:|
| TR-DCTA minus SC-DCTA | +0.0701 | [0.0349, 0.1121] | 8 / 2 / 0 |
| TR-DCTA minus SC-ENS | +0.0767 | [0.0378, 0.1191] | 8 / 2 / 0 |
| TR-DCTA minus full-information oracle | -0.0121 | [-0.0301, 0.0000] | 0 / 8 / 2 |

| Anchor-quarantine contrast | Task-macro difference | 95% interval | Task wins/ties/losses |
|---|---:|---:|---:|
| TR-DCTA minus SC-DCTA | +0.0501 | [0.0235, 0.0826] | 7 / 3 / 0 |
| TR-DCTA minus SC-ENS | +0.0567 | [0.0266, 0.0926] | 7 / 3 / 0 |
| TR-DCTA minus full-information oracle | -0.0121 | [-0.0301, 0.0000] | 0 / 8 / 2 |

## Interpretation

The bridge supports the intended mechanism: planning for the terminal action improves both stages needed for robot recovery. TR-DCTA finds and quarantines more of the harmful retrieved memories, and it leaves a safe fallback more often after quarantine. This is stronger evidence than showing only better corruption recall.

The honest limitation is sample scope. Ten tasks are sufficient for a transfer bridge, and the paired task-level differences are consistent, but they are not a substitute for the locked full MetaWorld task matrix. No additional MetaWorld tuning should occur before that run.

## Integrity and reproducibility

All verification gates passed:

- pinned inputs and artifact hashes;
- exactly 10 tasks, 30 archives, and 182 exposure episodes;
- exact reconstruction of the frozen semantic rankings;
- four distinct replays in every archive;
- confirmed-positive-only quarantine;
- rollout value no worse than the base action under TR-DCTA's own posterior model in every archive;
- sampled behavioral endpoints exactly reproduced from the private recovery ledger;
- summaries and task-clustered bootstrap recomputed exactly.

Runtime was 24.92 seconds end to end, including 5.80 seconds of planning.

## Artifacts

- Protocol: `docs/METAWORLD_TR_DCTA_10TASK_BRIDGE_PROTOCOL_V1.md`
- Freeze config: `configs/metaworld_tr_dcta_10task_bridge_freeze_v1.json`
- Raw report: `results/metaworld_tr_dcta_10task_bridge_v1.json`
- Verification report: `results/metaworld_tr_dcta_10task_bridge_verified_v1.json`
- Raw report SHA-256: `b4850f3e4a20cc37ea97cdb78a58c5ed97c8db177ce96e1840599d31da454c3b`
- Verification report SHA-256: `290e8cc87ed823bdcfd56c4ed5e162be95418c7ef5e749b49c2a01fa5cf46a23`

