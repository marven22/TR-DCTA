# Meta-World TR-DCTA 10-task bridge protocol v1

## Purpose and status

This locked bridge tests whether recovery-oriented DCTA transfers from BabyAI
to the existing 10-task Meta-World development split. It is a feasibility and
retrospective transfer study, not held-out evidence and not a tuning exercise.

## Why the terminal contract differs from BabyAI

Meta-World archives contain 2--10 affected memories. Existing recovery does not
require removing all of them. Each affected memory defines a forced-exposure
episode: it is placed at retrieval rank one, the audit quarantine is applied,
and the first surviving memory in the frozen semantic ranking is executed.

The frozen remediation rule quarantines only replay-confirmed harmful memories.
TR-DCTA must retain this rule. Applying BabyAI's capacity-three full-set rule
would make most Meta-World archives unrecoverable by definition and is forbidden.

## Frozen TR-DCTA instantiation

Use the corrected task-cross-fitted Meta-World posterior: fit source and cascade
estimators on the other nine tasks, sample 2,048 importance-corrected particles,
and evaluate the held task's three source rotations at 25% missing provenance.

At each decision, TR-DCTA evaluates every next replay, integrates positive and
negative outcomes, follows probabilistic DCTA for the remaining slots, and
scores the terminal confirmed-positive quarantine. Terminal utility is
lexicographic:

1. expected behavioral recovery averaged across the affected forced-exposure
   anchors in each posterior world;
2. expected fraction of affected anchors quarantined.

After the real outcome, TR-DCTA replans. The four-replay budget, posterior,
harm weights, semantic model/revision, rankings, policy outcomes, and
confirmed-positive remediation rule are frozen existing Meta-World objects.

For a hypothetical posterior world, memories in its affected set use their
corrupted policy and all other memories use their clean counterfactual policy.
Both mappings and every policy outcome already exist in the private recovery
ledger. No simulator or LLM generation is performed.

## Comparators and reporting

Reuse the existing forced-exposure results for SC-DCTA, shared-posterior ENS,
hard-source DCTA, source-then DCTA, floored probabilistic DCTA, known-source
DCTA, and full-information oracle. Reconstruct their rankings and outcomes
exactly before accepting the bridge.

Report behavioral recovery, anchor quarantine, weighted discovery recall,
model-relative rollout improvement, runtime, episode counts, and task-clustered
paired bootstrap intervals. A null or adverse result is retained.

## Go/no-go interpretation

The bridge is executable if all 30 archives, 182 forced-exposure episodes,
cross-fitted posteriors, four-replay trajectories, reconstructed baseline
outcomes, and rollout-dominance checks validate. Empirical superiority is a
result, not an integrity gate. Only an executable bridge licenses considering
the full 49-task retrospective transfer.
