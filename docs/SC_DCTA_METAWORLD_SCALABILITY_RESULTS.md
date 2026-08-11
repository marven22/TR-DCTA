# SC-DCTA Meta-World archive-scalability results

## Status and reporting boundary

This document closes the frozen archive-scalability study defined in
`SC_DCTA_METAWORLD_SCALABILITY_PROTOCOL.md`. The 29-task evaluation panel is
disjoint from the 20 tasks used to fit SC-DCTA, but it had already been
inspected in preceding baseline and recovery studies. These results are
therefore a **frozen post-hoc stress test**, not a new confirmatory evaluation.

The study expands each original 21-memory archive to 50, 100, and 200 memories
with nested, same-task, causally connected benign distractors. The original
memories, harmful labels, causal cascade, timestamps, and harm weights remain
unchanged. Replay budget stays fixed.

## Evidence volume and verification

- Development: 10 tasks, 90 base archive/mask conditions, 6,480 audit rows.
- Validation: 10 tasks, 90 base archive/mask conditions, 6,480 audit rows.
- Evaluation: 29 tasks, 261 base archive/mask conditions, 18,792 audit rows.
- Behavioral evaluation: 182 development, 172 validation, and 565 evaluation
  exposure episodes, yielding 66,168 method/size/budget recovery rows.
- Construction audit: 1,764 scaled archive instances across all splits.
- Memory profile: all 12 archive-size/provenance-mask cells.

The executable verification audit passed all 20 checks. It confirmed frozen
input hashes, complete and duplicate-free grids, aggregate recomputation,
successful distractor outcomes, legacy reproduction, and memory-profile
coverage. At 21 memories, SC-DCTA, ENS, hard-source DCTA, ACIS-Risk, and
floored Prob-DCTA reproduce the prior corrected-ledger run exactly over 783
conditions per method: replay IDs and metrics are identical. The random row is
a separately named deterministic control draw and therefore does not reproduce
the earlier random ordering; this exception is recorded in the verification
artifact and does not affect substantive comparisons.

## Primary evaluation condition

Four replays and 25% missing provenance:

| Archive memories | SC-DCTA | ENS | Hard-source | ACIS-Risk | Floored Prob-DCTA | Random |
|---:|---:|---:|---:|---:|---:|---:|
| 21 | 0.6297 | 0.6198 | 0.6335 | 0.5488 | 0.6149 | 0.1482 |
| 50 | 0.6090 | 0.6149 | 0.6245 | 0.3832 | 0.5996 | 0.0665 |
| 100 | 0.5948 | 0.6041 | 0.5998 | 0.1967 | 0.5590 | 0.0269 |
| 200 | 0.5487 | 0.5935 | 0.5703 | 0.0255 | 0.5054 | 0.0120 |

Values are weighted harmful-memory recall, macro-averaged over archives.
SC-DCTA declines by 0.0810 from 21 to 200 memories, with a task-clustered 95%
bootstrap interval of [-0.1276, -0.0365]. This is degradation, but not collapse:
the method retains 54.87% weighted recall while the candidate set grows by
approximately 9.5 times under the same four-replay budget.

At 200 memories, SC-DCTA exceeds ACIS-Risk by 0.5232 [0.4632, 0.5820], floored
Prob-DCTA by 0.0432 [0.0217, 0.0667], and random by 0.5366 [0.4803, 0.5898]. It
is statistically tied with hard-source DCTA (-0.0216 [-0.0516, 0.0057]) but
trails ENS by 0.0449 [-0.0810, -0.0109]. The large-archive claim must therefore
be robustness relative to weaker ranking approaches, not superiority to ENS.

## Behavioral recovery

Task-macro recovery under forced harmful-descendant exposure:

| Archive memories | SC-DCTA | ENS | Hard-source | ACIS-Risk | Floored Prob-DCTA | Random |
|---:|---:|---:|---:|---:|---:|---:|
| 21 | 0.5103 | 0.5069 | 0.5093 | 0.4590 | 0.5020 | 0.1519 |
| 50 | 0.5020 | 0.5110 | 0.5121 | 0.3325 | 0.4959 | 0.0708 |
| 100 | 0.4939 | 0.5065 | 0.4986 | 0.1735 | 0.4639 | 0.0316 |
| 200 | 0.4515 | 0.4983 | 0.4746 | 0.0186 | 0.4110 | 0.0137 |

SC-DCTA recovery declines by 0.0588 from 21 to 200 memories
[-0.0981, -0.0225]. At 200 memories it trails ENS by 0.0468
[-0.0721, -0.0238]. Localization remains the limiting step: at 200 memories,
SC-DCTA recovers 125 of 129 localized episodes at budget two, 252 of 260 at
budget four, and 426 of 430 at budget eight. Conditional recovery is therefore
96.90%, 96.92%, and 99.07%, respectively.

## Replay-budget and provenance sensitivity

SC-DCTA weighted recall at 25% missing provenance:

| Archive memories | 2 replays | 4 replays | 8 replays |
|---:|---:|---:|---:|
| 21 | 0.3426 | 0.6297 | 0.8958 |
| 50 | 0.3362 | 0.6090 | 0.8719 |
| 100 | 0.3198 | 0.5948 | 0.8415 |
| 200 | 0.2836 | 0.5487 | 0.8102 |

SC-DCTA behavioral recovery follows the same pattern: at 200 memories it is
0.2239, 0.4515, and 0.7566 for budgets two, four, and eight. A larger replay
budget substantially offsets archive growth, but the study does not select a
new budget post hoc.

At budget four, SC-DCTA recall for 0%, 25%, and 50% missing provenance is:

| Archive memories | 0% missing | 25% missing | 50% missing |
|---:|---:|---:|---:|
| 21 | 0.6648 | 0.6297 | 0.6091 |
| 50 | 0.6443 | 0.6090 | 0.6198 |
| 100 | 0.6273 | 0.5948 | 0.5832 |
| 200 | 0.6064 | 0.5487 | 0.5261 |

## Distractor validity and nontriviality

All added memories have stored successful target-task outcomes. They are not
disconnected padding: every distractor has a causally plausible parent and its
edge is observed or masked according to the frozen condition. At the primary
evaluation condition, mean posterior harmful probability assigned to
distractors rises from 0 at 21 memories to 0.0301, 0.0400, and 0.0418 at 50,
100, and 200 memories. SC-DCTA spends 0%, 1.44%, 6.03%, and 12.07% of replay
calls on these benign distractors. Thus the added memories are plausible
competitors that increasingly consume a fixed diagnostic budget.

## Computational scaling

Mean acquisition time from the full evaluation run:

| Archive memories | SC-DCTA seconds | ENS seconds | SC-DCTA / N=21 | ENS / N=21 |
|---:|---:|---:|---:|---:|
| 21 | 0.0268 | 0.0030 | 1.0x | 1.0x |
| 50 | 0.2489 | 0.0102 | 9.3x | 3.4x |
| 100 | 1.5184 | 0.0327 | 56.7x | 10.9x |
| 200 | 7.3836 | 0.1072 | 275.9x | 35.9x |

These absolute wall times were collected under shared parallel CPU load and
must not be presented as isolated latency benchmarks. The within-run scaling
ratios show a real computational limitation: SC-DCTA's acquisition rule grows
much faster than ENS.

For one deterministic development archive, traced Python peak allocation for
posterior construction plus SC-DCTA acquisition at 25% missing provenance was
0.26, 0.40, 0.67, and 0.99 MiB at 21, 50, 100, and 200 memories. Profiled time
was 1.63, 3.23, 6.79, and 15.03 seconds. This is incremental traced Python
allocation, not total process RSS, native-library memory, or GPU memory.

## Conclusion for the paper

SC-DCTA remains useful under a nearly tenfold increase in task-matched archive
size, substantially outperforms ACIS-Risk and the superseded probability-floor
formulation, and continues to enable recovery once the harmful lineage is
localized. However, localization accuracy degrades and acquisition cost grows
rapidly; ENS becomes both more accurate and much faster at 200 candidates.
This is a credible scalability result and an equally important limitation. No
Meta-World method modification should be made in response to this evaluation.

## Authoritative artifacts

- Frozen protocol: `docs/SC_DCTA_METAWORLD_SCALABILITY_PROTOCOL.md`
- Frozen configuration: `configs/metaworld_scalability_freeze_v1.json`
- Audit aggregates: `results/metaworld_scalability_{development,validation,test}.json`
- Recovery aggregates: `results/metaworld_scalability_recovery_{development,validation,test}.json`
- Consolidated analysis: `results/metaworld_scalability_analysis.json`
- Memory profile: `results/metaworld_scalability_memory_profile.json`
- Verification record: `results/metaworld_scalability_verification.json`
- Verification code: `scripts/verify_metaworld_scalability.py`
