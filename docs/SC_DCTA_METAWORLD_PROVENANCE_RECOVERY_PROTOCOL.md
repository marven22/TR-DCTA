# Meta-World provenance-missingness recovery protocol

## Question

How gracefully do SC-DCTA localization, behavioral recovery, and audit utility
degrade as formation provenance is hidden?

## Frozen design

- Task splits: 10 development, 10 task-cross-fitted validation, 29 held-out
  test tasks.
- Source rotations: three per task.
- Provenance missingness: 0%, 25%, and 50% of true formation edges.
- Replay budgets: 2, 4, and 8.
- Harmful-exposure endpoint: every affected descendant is forced to retrieval
  rank one for every method; after confirmed-failure quarantine, execute the
  first surviving memory in the common MPNet semantic order.
- Quarantine scope: target task only.
- Methods: SC-DCTA, ENS–SharedPosterior, hard-source DCTA,
  source-then-DCTA, floored Prob-DCTA, known-source DCTA, and the
  full-information oracle.

The underlying memories, corruption labels, source rotations, semantic model,
and verified policy outcomes are held fixed across masks. Only the observed
formation-edge set and the resulting audit path may change.

## Outcomes

For every split, mask, budget, and method report:

1. harmful exposure count;
2. exposed-anchor localization count and rate;
3. behavioral recovery count and task-macro rate;
4. recovery conditional on localization;
5. harmful fallback count;
6. benign replay count and audit yield;
7. target-benign retention;
8. gap to ENS–SharedPosterior, hard-source DCTA, and oracle.

The primary robustness statistic is the task-macro change from 0% to 50%
missing provenance at the frozen primary budget of four. Paired task-clustered
bootstrap intervals use 10,000 draws. Results at budgets two and eight are
sensitivity analyses.

## Claim rule

SC-DCTA may be described as more robust to incomplete provenance than a
comparator only if its 0%-to-50% degradation is smaller and the paired
difference-in-degradation interval excludes zero. Otherwise the result is
reported as parity or inconclusive. All-49 results remain descriptive; the
29-task test split is primary.
