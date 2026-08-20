# DDXPlus TR-DCTA transfer results v1

## Status and claim boundary

**Complete and independently verified.** The frozen terminal-recovery
instantiation of TR-DCTA was executed on 44 DDXPlus pathologies, 132 primary
archives, and 7098 method-episodes. No TR-DCTA
parameter was tuned on DDXPlus.

The 26-task test split is the primary locked evaluation. DDXPlus is
synthetically generated and supports no clinical claim.

## Primary 26-task test result

| Method | Recoveries | Recovery rate | Anchor quarantine rate | Harmful fallbacks |
|---|---:|---:|---:|---:|
| **TR-DCTA** | 240/284 | 0.8451 | 0.8592 | 4 |
| SC-DCTA | 217/284 | 0.7641 | 0.7782 | 4 |
| Probabilistic DCTA | 216/284 | 0.7606 | 0.7746 | 4 |
| ENS (shared posterior) | 216/284 | 0.7606 | 0.7746 | 4 |
| Hard-source DCTA | 214/284 | 0.7535 | 0.7535 | 0 |
| Source-then DCTA | 214/284 | 0.7535 | 0.7676 | 4 |
| Static risk | 161/284 | 0.5669 | 0.5704 | 1 |
| Random replay | 259/1420 | 0.1824 | 0.1937 | 16 |
| Known-source DCTA | 235/284 | 0.8275 | 0.8415 | 4 |
| Full-information comparator | 241/284 | 0.8486 | 0.8627 | 4 |

Random replay is reported over five replicates per archive.

## Task-clustered paired inference on test

| Recovery contrast | Task-macro difference | 95% interval | Task wins/ties/losses |
|---|---:|---:|---:|
| TR-DCTA minus SC-DCTA | +0.0810 | [+0.0365, +0.1365] | 10 / 16 / 0 |
| TR-DCTA minus Probabilistic DCTA | +0.0839 | [+0.0373, +0.1403] | 10 / 16 / 0 |
| TR-DCTA minus ENS (shared posterior) | +0.0822 | [+0.0359, +0.1372] | 10 / 16 / 0 |
| TR-DCTA minus Hard-source DCTA | +0.0899 | [+0.0381, +0.1517] | 9 / 17 / 0 |
| TR-DCTA minus Source-then DCTA | +0.0936 | [+0.0500, +0.1462] | 16 / 10 / 0 |
| TR-DCTA minus Static risk | +0.2844 | [+0.1838, +0.3921] | 20 / 6 / 0 |
| TR-DCTA minus Random replay | +0.6869 | [+0.6380, +0.7349] | 26 / 0 / 0 |
| TR-DCTA minus Known-source DCTA | +0.0217 | [+0.0013, +0.0477] | 5 / 20 / 1 |
| TR-DCTA minus Full-information comparator | -0.0026 | [-0.0077, +0.0000] | 0 / 25 / 1 |

Every interval against a deployable comparator excludes zero, and TR-DCTA loses
no test task to SC-DCTA, probabilistic DCTA, or ENS.

TR-DCTA also exceeds known-source DCTA, which receives the realized corrupt
origin. This reproduces the MetaWorld ordering: privileged origin information
does not compensate for optimizing discovery instead of terminal recovery.

## Archive composition

Across all 396 materialized archives, a mean of 3.84 of 21
memories are harmful and 5.27 are contaminated, leaving
1.42 contaminated but behaviourally safe. No
archive is fully harmful and every archive contains at least one harmful memory.

Donor procedures whose observable description is identical to the native
procedure's are rejected by the screen. Such a donor makes the corrupted memory
indistinguishable from a clean one in everything the auditor can observe, which
is an unlearnable example rather than a hard one. Both generators assert that no
such memory survives.

## Posterior quality

| Quantity | Development | Validation | Chance |
|---|---:|---:|---:|
| Source top-1 accuracy | 0.8148 | 0.8889 | 0.3333 |
| Mean true-source probability | 0.6405 | 0.7484 | 0.3333 |

Pre-replay posterior harm ranking reaches a mean AUC of
0.9190 against a chance value of 0.5.

## Limitations

1. **The domain is close to saturated.** TR-DCTA is 1 episode(s) below the
   full-information comparator, with 0 task
   wins and 1 task losses against it. The
   advantage over deployable baselines is real and interval-separated, but the
   remaining headroom is small, so this domain confirms the method rather than
   stressing it.
2. **SC-DCTA barely separates from probabilistic DCTA.** The confidence gate
   almost never selects hard mode here, so the two are nearly the same policy and
   should not be presented as two independent comparisons.
3. **Template-written memories.** Memory text is composed deterministically
   rather than by the pinned Qwen checkpoint. A model-written archive is
   implemented in `scripts/build_ddxplus_generation_qwen_v1.py` and is the
   intended realism upgrade; less separable prose would lower the pre-replay
   posterior AUC and open headroom.
4. **Declared deviations.** Token-overlap retrieval and 512 particles, as
   recorded in the protocol.

## Verification

`scripts/verify_ddxplus_tr_dcta_v1.py` re-derives replay labels, the
confirmed-positive quarantine, every retrieval ranking, and every non-random
forced-exposure outcome from the ledgers and the generation record, then
recomputes the summaries and the task-clustered bootstrap. All 13 checks pass
and 4,563 episodes were independently recomputed.
