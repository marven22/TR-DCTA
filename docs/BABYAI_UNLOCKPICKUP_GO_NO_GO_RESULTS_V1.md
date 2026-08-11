# BabyAI UnlockPickup structural go/no-go results v1

## Decision

**GO.** The distractor-enabled UnlockPickup environment supports a selective,
locally correct, multistage memory-corruption benchmark. Every frozen gate and
every independent verification check passed.

This result licenses method development. SC-DCTA and baselines were not run and
no performance claim follows from this audit.

## Executed scope

- Official environment: `BabyAI-UnlockPickupDist-v0`
- Fixed development contexts: 60 seeds
- Target colors represented: all six
- Source colors tested per context: six
- Descendants per source: three
- Complete transfer executions: 1,080
- Matching source-target executions: 180
- Mismatched source-target executions: 900
- Environment execution errors: zero
- Stored deterministic repeats: 30
- Independent stratified re-executions: 18

Every context contained the required key, locked door, target box, and at least
four distractor objects.

## Memory behavior

The source-bound memory follows the target mission's prerequisite workflow but
retains the box color accepted by its source experience. When source and target
match, all descendants complete the mission. After transfer to a different box
color, descendants fail at different propagation stages:

| Descendant | Required progress before failure | Harmful transfers | Mean executed actions |
|---|---|---:|---:|
| `early_bind` | Required key acquired | 300/300 | 6.70 |
| `post_unlock_bind` | Locked door opened | 300/300 | 14.03 |
| `terminal_bind` | Target box reached, pickup refused | 300/300 | 26.40 |

For all 300 mismatched source-target pairs, stopping order was strictly
`early_bind < post_unlock_bind < terminal_bind`. The variants therefore encode
distinct causal depths rather than duplicated failures.

## Local correctness and harm

All 180 matching source-target transfers succeeded. One donor context per color
was identified, and all 18 color-variant donor checks succeeded. Thus every
harmful transferred workflow is executable and correct when its remembered
source binding matches the task.

All 900 mismatched transfers failed through the preregistered source guard. No
failure was caused by timeout, expert-planner failure, missing key acquisition,
or an inability to unlock the door. Every target retained its three successful
target-bound descendants as recovery alternatives.

## Why this adds value beyond OpenDoorColor

OpenDoorColor tests a wrong transferred target in a short navigation policy.
UnlockPickup tests the same generalization error inside a causal prerequisite
workflow:

```text
key acquisition -> door unlocking -> target-room access -> box acceptance
```

The harmful memory may execute much of the workflow correctly before its stale
source binding becomes consequential. This supports depth-stratified harm,
partial progress, and provenance masking in a way that the single-step task
does not.

## Limitations and claim boundary

The source guard is a controlled corruption injection, not a claim that a
trained BabyAI policy naturally learns this exact bug. The official expert
provides the executable workflow so that planner errors do not contaminate the
memory-auditing label. The audit demonstrates benchmark validity, not natural
attack prevalence and not SC-DCTA effectiveness.

## Next licensed experiment

Construct 60 development archives with one active three-descendant corrupted
source family, mission-conditioned clean alternatives, uncertain source priors,
and complete/partial provenance. Then compare SC-DCTA with the already frozen
BabyAI baseline family at replay budgets 2, 4, and 8. A held-out UnlockPickup
panel should be opened only after that method-development comparison.
