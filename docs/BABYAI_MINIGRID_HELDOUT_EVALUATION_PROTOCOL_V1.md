# Frozen BabyAI/MiniGrid held-out evaluation protocol v1

Status: frozen after development on seeds 0–59 and before executing any archive
or method on held-out seeds 60–299.

## Objective

Evaluate SC-DCTA without further tuning on 240 unseen symbolic embodied
contexts. The evaluation tests executable corruption discovery, strict
quarantine, recovery, source uncertainty, provenance incompleteness, and replay
budget sensitivity using the method and archive construction fixed during
development.

## Held-out population

The official `BabyAI-OpenDoorColor-v0` environment supplies seeds 60 through
299. No seed from the development range 0–59 is permitted. Each seed produces
one independent 18-memory archive: six source families, three descendants per
family, and exactly one locally correct but non-transferable corrupted family.

The true source is selected by the already developed deterministic seed rule.
Confidence regimes rotate by seed and are balanced across known, calibrated,
ambiguous, and misleading priors. Every corrupted memory must first succeed on
a source-matched donor mission, fail on its target mission, and have 15 clean
target-successful alternatives. Otherwise the evaluation is invalid.

## Paired provenance and inference

Every archive receives complete, 33%-missing, and 67%-missing provenance views.
The latter two hide two or four of six links at each graph layer, respectively.
Opaque candidate identifiers prevent source leakage. All one-to-one lineage
completions consistent with visible links are enumerated exactly and duplicate
source-descendant worlds are aggregated.

Methods receive identical posteriors, candidates, observed links, harm weights,
and replay budgets. They never receive the private completion or an unqueried
outcome. The methods are SC-DCTA, its probabilistic and hard-source ablations,
ENS, source-information gain, static risk, random replay, and a known-source
ceiling. Random replay uses 50 deterministic replicates.

## Budgets, quarantine, and outcomes

Budgets are 2, 4, and 8, with 4 primary. After replay, every method quarantines
exactly three memories ranked by final posterior corruption probability. Robot
recovery requires all three true harmful memories to be quarantined.

Primary estimands are corrupted-descendant recall and robot-recovery success.
Additional outcomes are audit yield, source accuracy, quarantine recall and
precision, clean removal, and regret to the known-source ceiling.

## Statistical specification

All comparisons are paired by held-out seed. Random-replay outcomes are first
averaged within seed-condition-budget. Ten thousand paired bootstrap draws over
seeds produce 95% confidence intervals.

At budget 4, SC-DCTA superiority over hard-source DCTA and random replay is
tested directly. SC-DCTA noninferiority to ENS and probabilistic DCTA uses a
fixed absolute margin of 0.05. Complete provenance is a reference, 33% missing
provenance is the primary practical condition, and 67% is a severe stress test.

The study reports estimates and confidence intervals regardless of whether a
claim passes. No method, threshold, mask, budget, or archive rule may be changed
after held-out execution.
