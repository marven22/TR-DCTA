# Meta-World quarantine utility protocol

## Question

Does the common post-audit quarantine rule preserve benign and locally useful
memory while preventing target-task harm?

## Frozen scope

- Splits: 10 development, 10 task-cross-fitted validation, and 29 held-out
  Meta-World tasks.
- Unit: one 25%-missing-provenance archive (three source rotations per task).
- Replay budgets: 2, 4, and 8.
- Primary method: SC-DCTA; the same common methods and aliases as the frozen
  forced-exposure study are retained.
- Existing replay paths are reused. No method is rerun or retuned.

## Quarantine semantics

The deployed rule is **task-scoped**: a memory whose replay fails for target
task `q` is excluded when serving `q`, but is not globally deleted. This matters
because the benchmark's corruptions are locally correct donor experiences that
fail to transfer to the target.

## Metrics

For every archive and budget report:

1. physical replay calls;
2. confirmed harmful replays and benign replay calls;
3. task-relevant harmful memories quarantined;
4. false quarantines of target-benign memories;
5. target-benign memory retention;
6. total target-context archive retention;
7. clean-counterfactual quarantines under the same replay IDs;
8. locally validated donor memories that a hypothetical global-delete policy
   would make unavailable;
9. task-scoped cross-context removals, which must be zero by construction.

Counts, archive means, and task-macro means are reported separately by split
and for all 49 tasks. The all-49 result is descriptive. No percentage alone is
reported without its count denominator.

## Claim boundary

This study measures memory availability and target-task behavioral safety. It
does not claim that a failed target transfer makes the underlying experience
globally corrupt, and it does not evaluate semantic rewriting of memory.
