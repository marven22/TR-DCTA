# Meta-World missing-provenance failure-strata protocol

## Status

Post-hoc diagnostic frozen after the provenance sensitivity result. This
analysis explains failures and may not be used to alter SC-DCTA or reclaim the
existing Meta-World test split.

## Paired unit

Pair each harmful descendant at budget four between the 0%-missing and
50%-missing archive with the same task and source rotation. Analyze the change
in localization and behavioral recovery for SC-DCTA and ENS–SharedPosterior.

## Predeclared strata

- **Observed source path:** the active source can or cannot reach the descendant
  through the 50%-masked observed graph.
- **True cascade depth:** shallow (one or two edges) versus deep (three or more
  edges). Exact depths are also reported.
- **Source ancestry:** one true source ancestor versus multiple source
  ancestors.
- **Source confidence at complete provenance:** maximum fitted source
  probability below 0.8 versus at least 0.8.
- **Source top-1 correctness:** fitted most likely source equals or does not
  equal the private active source.
- **Cascade size:** at most six versus more than six affected descendants.

The depth and cascade cut points were selected from the development split only.
The 0.8 confidence threshold was already frozen in the earlier SC-DCTA
evaluation protocol.

## Statistics and interpretation

Report episode counts, task counts, mask-0 and mask-50 recovery, and the paired
task-macro change with 10,000 task-clustered bootstrap draws. Also report the
SC-DCTA-minus-ENS difference in change inside every stratum.

The primary mechanistic diagnostic is disconnected versus still-connected
descendants. Confidence and source-correctness strata with small counts are
descriptive and may not support inferential claims. No multiple-comparison
significance claims will be made.
