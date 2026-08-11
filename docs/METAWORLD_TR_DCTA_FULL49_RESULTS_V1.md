# MetaWorld TR-DCTA full-49 results v1

## Status and claim boundary

**Complete and independently verified.** The frozen MetaWorld instantiation of
TR-DCTA was executed on all 49 tasks, 147 primary archives, and 919
forced-exposure episodes. No TR-DCTA parameter was changed after the 10-task
bridge.

The 29-task test split is the primary locked transfer evaluation. The pooled
49-task result is descriptive because development and validation were observed
during the broader MetaWorld research process.

## Primary 29-task test result

| Method | Harmful anchors quarantined | Robot recoveries | Safe fallback after quarantine | Harmful fallbacks |
|---|---:|---:|---:|---:|
| **TR-DCTA** | **326/565** | **322/565** | **322/326** | **4** |
| SC-DCTA | 305/565 | 289/565 | 289/305 | 16 |
| ENS (shared posterior) | 302/565 | 287/565 | 287/302 | 15 |
| Hard-source DCTA | 304/565 | 288/565 | 288/304 | 16 |
| Source-then DCTA | 283/565 | 268/565 | 268/283 | 15 |
| Floored probabilistic DCTA | 300/565 | 284/565 | 284/300 | 16 |
| Known-source DCTA | 313/565 | 297/565 | 297/313 | 16 |
| Full-information comparator | 329/565 | 325/565 | 325/329 | 4 |

TR-DCTA recovered 33 more episodes than SC-DCTA, 35 more than ENS, and 25 more
than known-source DCTA. It was three recoveries below the frozen full-information
comparator. The latter knows the affected set and uses the original weighted-harm
hindsight rule; it is a strong reference comparator, not a proof of the globally
optimal terminal-recovery ceiling.

## Task-clustered paired inference on test

| Recovery contrast | Task-macro difference | 95% interval | Task wins/ties/losses |
|---|---:|---:|---:|
| TR-DCTA minus SC-DCTA | +0.0642 | [0.0301, 0.1048] | 14 / 15 / 0 |
| TR-DCTA minus ENS | +0.0675 | [0.0319, 0.1096] | 16 / 12 / 1 |
| TR-DCTA minus hard-source DCTA | +0.0652 | [0.0306, 0.1062] | 14 / 15 / 0 |
| TR-DCTA minus source-then DCTA | +0.0984 | [0.0693, 0.1328] | 24 / 5 / 0 |
| TR-DCTA minus floored probabilistic DCTA | +0.0724 | [0.0379, 0.1122] | 15 / 14 / 0 |
| TR-DCTA minus known-source DCTA | +0.0484 | [0.0203, 0.0831] | 13 / 16 / 0 |
| TR-DCTA minus full-information comparator | -0.0053 | [-0.0119, 0.0000] | 0 / 26 / 3 |

For harmful-anchor quarantine, TR-DCTA also improved over SC-DCTA by +0.0400
[0.0184, 0.0687] and over ENS by +0.0451 [0.0238, 0.0694]. Thus the recovery
gain is not due solely to lucky fallback behavior: TR-DCTA both finds more of
the retrieved harmful anchors and leaves fewer harmful fallbacks.

## Split and pooled results

| Scope | Episodes | TR-DCTA | SC-DCTA | ENS | Full-information comparator |
|---|---:|---:|---:|---:|---:|
| Development, 10 tasks | 182 | **106** | 93 | 92 | 108 |
| Validation, 10 tasks | 172 | **106** | 98 | 100 | 106 |
| Test, 29 tasks | 565 | **322** | 289 | 287 | 325 |
| All 49 tasks | 919 | **534** | 480 | 479 | 539 |

On validation, TR-DCTA exactly matched the full-information comparator. Across
all 49 tasks, it produced 54 more recoveries than SC-DCTA and 55 more than ENS,
while finishing five recoveries below the full-information comparator.

Archive-macro weighted corruption-discovery recall for TR-DCTA was 0.721 on
development, 0.740 on validation, 0.694 on test, and 0.709 across all 147
archives. Optimizing terminal recovery therefore did not collapse the method's
ability to discover harmful memories.

## Interpretation

The result supports the objective-alignment thesis. Earlier DCTA variants spend
replays to maximize an intermediate quantity: expected harmful-memory discovery.
TR-DCTA instead asks which complete replay sequence is most likely to leave the
agent able to act successfully after confirmed corruptions are removed. On the
test tasks, that change yields both more quarantined harmful anchors and a
fourfold reduction in harmful fallbacks relative to SC-DCTA (4 versus 16).

The effect is broad rather than being driven by a few large wins: TR-DCTA never
lost to SC-DCTA on any of the 29 test tasks. Against ENS it won 16 tasks, tied 12,
and lost one. The paired intervals exclude zero against every deployable
comparator, including the known-source adaptation.

## Verification

Every frozen integrity gate passed:

- 49 tasks, 147 archives, and 919 TR-DCTA exposure episodes;
- exact reconstruction of the existing semantic retrieval endpoints;
- four distinct physical replays per archive;
- replay-confirmed harmful memories were the only memories quarantined;
- modeled rollout value weakly dominated the base acquisition at every archive;
- development results exactly reproduced the earlier 10-task bridge;
- 113 independently reconstructed terminal episodes matched exactly;
- all summaries and paired task-clustered intervals recomputed exactly.

The full run required 82.59 seconds. Independent verification required about
10 seconds.

## Artifacts

- Protocol: `docs/METAWORLD_TR_DCTA_FULL49_PROTOCOL_V1.md`
- Frozen config: `configs/metaworld_tr_dcta_full49_freeze_v1.json`
- Runner: `scripts/run_metaworld_tr_dcta_full49_v1.py`
- Verifier: `scripts/verify_metaworld_tr_dcta_full49_v1.py`
- Raw report: `results/metaworld_tr_dcta_full49_v1.json`
- Verification report: `results/metaworld_tr_dcta_full49_verified_v1.json`
- Raw report SHA-256: `60275b76c7480c4a411f629e57a54177a74eb04a372316c1c9e57c423076b837`
- Verification report SHA-256: `ab97cc6b8f47a7dbbfd886aaeb801412b6529b04e7c958443f873c9b779e01ab`

