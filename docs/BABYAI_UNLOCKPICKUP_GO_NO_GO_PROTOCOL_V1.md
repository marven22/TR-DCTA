# Frozen BabyAI UnlockPickup structural go/no-go protocol v1

Status: frozen after executor smoke testing and before the complete 60-context
transfer matrix.

## Purpose

Determine whether UnlockPickup supports a nontrivial second BabyAI memory-
corruption mechanism. This audit qualifies the executable substrate and archive
construction only. It does not execute SC-DCTA or any baseline.

## Environment

The audit uses the official `BabyAI-UnlockPickupDist-v0` environment from
MiniGrid 3.0.0. Each mission asks the agent to pick up a colored box in a second
room. The agent must find a key, unlock the intervening door, reach the box, and
pick it up. The registered distractor variant adds four irrelevant objects.

The official `BabyAIBot` supplies the mission-conditioned executor. Correctness
is judged by the untouched environment reward and termination state. Seeds
0–59 are fixed before the matrix is run.

## Memory mechanism

A source memory is a workflow learned for a particular box color. It performs
the mission's prerequisite navigation but retains a source-bound acceptance
guard. The guard is harmless when the source and target colors match and
harmful after transfer to a different target color.

Three descendants represent propagation of the same binding error to different
workflow stages:

- `early_bind`: abort after acquiring the key if the target differs from the
  remembered source;
- `post_unlock_bind`: abort after unlocking the door;
- `terminal_bind`: reach the target box but refuse pickup because its color
  differs from the remembered source.

This construction ensures that every harmful replay makes executable
prerequisite progress. The variants are behaviorally distinct: for every
mismatched source-target pair, early abort must precede post-unlock abort, which
must precede terminal abort.

## Transfer matrix and recovery

Every one of six source colors and three descendants is executed on every one
of 60 target contexts, producing 1,080 outcomes. Matching source-target
workflows must succeed and serve as three clean recovery alternatives.
Mismatched workflows must fail selectively while reaching their preregistered
milestone.

The audit also identifies one donor seed per source color and verifies all
three descendants there. Thirty fixed executions are repeated exactly in
success, stopping reason, actions, steps, and milestones.

## Frozen qualification gates

The audit passes only if:

- all 60 contexts execute without errors and contain at least four distractors;
- all six target colors and all six harmful source colors occur;
- all 180 matching transfers succeed;
- all 900 mismatched transfers fail;
- all 300 early descendants acquire the key before failing;
- all 300 middle descendants open the locked door before failing;
- all 300 late descendants reach the target box before refusing pickup;
- all 300 source-target mismatch pairs exhibit strict early < middle < late
  stopping order;
- every context retains three successful target-bound alternatives; and
- all 30 repeat executions match exactly.

Passing licenses method development. It is not evidence that SC-DCTA performs
well on UnlockPickup.
