# MetaWorld TR-DCTA full-49 transfer protocol v1

## Purpose

Execute the frozen MetaWorld terminal-recovery instantiation of TR-DCTA on the
complete existing MetaWorld paper matrix. This follows the successful 10-task
bridge. No method, posterior, utility, mask, replay budget, archive, retrieval
ranking, or behavioral endpoint may be changed after opening this run.

## Scope and primary condition

- 49 tasks: 10 development, 10 validation, and 29 test.
- Three source rotations per task: 147 primary archives.
- Twenty-five percent missing provenance.
- Four distinct physical replays per archive.
- One forced-exposure episode for every affected memory: 919 episodes in total.
- Quarantine is restricted to replay-confirmed harmful memories.
- Behavioral recovery executes the first surviving memory in the frozen
  semantic ranking after quarantine.

## Frozen method

Use the adapter frozen and verified by the 10-task bridge. At each replay,
TR-DCTA evaluates the complete remaining four-replay horizon under its current
posterior. Its terminal utility is expected forced-exposure behavioral recovery,
with expected anchor quarantine as the tie-break. The real label is then
observed and the method replans. There is no MetaWorld parameter tuning.

## Posterior fitting contract

- Development: for each held task, fit on zero-missing-provenance archives from
  the other nine development tasks.
- Validation: for each held task, fit on zero-missing-provenance archives from
  the other 19 development-plus-validation tasks.
- Test: fit once on zero-missing-provenance archives from all 20 development and
  validation tasks; the 29 test tasks remain excluded.

All other posterior settings remain frozen: 2,048 particles, proposal floor
0.05, L2 regularization 1.0, and stable archive-derived seeds.

## Comparators

Reuse the already frozen forced-exposure endpoints for SC-DCTA, ENS with the
shared posterior, hard-source DCTA, source-then DCTA, floored probabilistic
DCTA, known-source DCTA, and the full-information oracle. Do not rerun or enhance
the comparators.

## Reporting and inference

Report exact counts and micro rates for each split and all 49 tasks. The primary
transfer comparison is the 29-task test split. Use paired task-clustered
bootstrap intervals for TR-DCTA minus every comparator. The all-49 aggregation
is descriptive because development and validation tasks previously influenced
the broader MetaWorld research process.

## Integrity gates

The run is valid only if:

1. all pinned artifacts match their hashes;
2. there are exactly 49 tasks, 147 archives, and 919 episodes;
3. every archive has four distinct replays;
4. every quarantined memory was replayed and labeled harmful;
5. reconstructed semantic rankings reproduce the frozen baseline endpoints;
6. rollout value is never below the base acquisition under TR-DCTA's own model;
7. every split and all-49 comparison contains the expected task clusters; and
8. an independent verifier reproduces counts, terminal behavior, summaries,
   and paired inference.

