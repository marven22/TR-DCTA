# BabyAI UnlockPickup TR-DCTA held-out protocol v1

## Status

Frozen after method development on seeds 0--59 and OpenDoorColor transfer, and
before any TR-DCTA execution or archive construction on seeds 60--299.

## Population and archive contract

Run exactly 240 `BabyAI-UnlockPickupDist-v0` contexts, seeds 60--299. Each
context contains 18 executable memories: six source families and three ordered
procedural stages. One source family is corrupted and its affected prefix has
length one, two, or three, rotating deterministically and equally across seeds.

An affected memory executes the source-bound workflow and must fail at its
declared procedural stage. Every unaffected memory executes the mission-bound
workflow and must succeed. Any label mismatch invalidates the experiment.

## Frozen uncertainty and replay design

Known, calibrated, ambiguous, and misleading source priors rotate equally.
Every archive receives complete, 33%-missing, and 67%-missing provenance views.
All source, cascade-length, and graph-completion worlds are enumerated exactly.
Opaque identifiers hide family membership. Replay budgets are 2, 4, and 8,
with 4 primary. Quarantine capacity is three.

## Methods and terminal decision

The frozen method is TR-DCTA with exact full-remaining-budget DCTA rollout.
Comparators are SC-DCTA, probabilistic and hard-source DCTA, ENS, source
information gain, source-then DCTA, positive-only DCTA, static risk, 50 random
replicates, oracle-source DCTA, and full-information hindsight.

Every deployable method uses the identical terminal rule: maximize posterior
probability that a capacity-three quarantine contains every harmful memory,
then maximize expected captured harm. Full-information hindsight alone receives
the true affected set and is explicitly privileged.

## Confirmatory estimands

For the primary analysis, average each method's two partial-provenance outcomes
within each held-out context at budget four, then compare TR-DCTA with SC-DCTA,
probabilistic DCTA, hard-source DCTA, ENS, and random replay. Primary estimands
are robot recovery and weighted quarantine recall. Ten thousand paired cluster
bootstrap draws over the 240 contexts produce 95% intervals. Superiority is
supported when the interval for TR-DCTA minus a comparator excludes zero.

Condition-specific results, complete-provenance reference, discovery recall,
source accuracy, clean removals, and budgets 2/8 are secondary. All estimates
and intervals are reported regardless of outcome. No method, prior, mask,
weight, capacity, budget, or claim may be altered after held-out execution.

## Execution discipline

Runner smoke testing is restricted to already-open development seeds 0--3.
Held-out seeds are executed only by the complete run. The final artifact must
pin the config, runner, TR-DCTA implementation, development report,
OpenDoorColor transfer report, and structural go/no-go report.
