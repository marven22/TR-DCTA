# Frozen Meta-World archive scalability protocol

## Status and claim boundary

This protocol is frozen before inspecting any archive-scaling outcome. The
construction may be debugged mechanically, but archive sizes, methods, replay
budgets, provenance masks, metrics, and aggregation rules may not be selected
from performance results.

The 29-task evaluation panel was untouched for the original SC-DCTA study but
has since been inspected in the baseline, recovery, provenance, and diagnostic
analyses. Consequently, this scalability experiment is a **frozen post-hoc
stress test**, not a new untouched confirmatory test. Development, validation,
and evaluation-panel results will be separated. The 29-task panel remains the
primary scalability estimate because it is the largest disjoint-from-fit task
panel, but the paper must use the preceding qualification.

## Question

As the number of candidate memories grows while physical replay budget remains
fixed, how do SC-DCTA's harmful-memory recall, audit efficiency, behavioral
recovery, compute time, and memory use change relative to strong budget-matched
alternatives?

## Frozen archive construction

Candidate-memory counts are 21 (the unmodified archive), 50, 100, and 200.
Scaling is nested: every smaller archive is a prefix of every larger archive
for the same task, rotation, and provenance mask.

Every added memory is a **hard benign distractor**:

1. Its text is copied from a clean counterfactual memory for the same Meta-World
   task.
2. Its recommended policy has a stored successful target-task outcome.
3. It receives one causally plausible parent selected without using harmful
   labels.
4. Its new edge is observed or placed in the latent-edge set using a stable
   hash at the archive's 0%, 25%, or 50% missing-provenance rate.
5. It is labeled benign. The original harmful source, affected descendants,
   memories, edges, timestamps, and labels are unchanged.

Disconnected padding is prohibited because it would receive zero cascade risk
and create a trivial scalability result. Original harm weights are frozen at
their 21-memory values. A distractor inherits its clean template's weight, so
adding benign memories cannot redefine the outcome denominator.

## Splits and frozen method

- Development: 10 tasks.
- Validation: 10 tasks.
- Evaluation panel: 29 tasks disjoint from the 20 tasks used to fit SC-DCTA.
- SC-DCTA fit: the already-frozen 20-task Meta-World source and cascade fit.
- Particles: 2,048 with proposal floor 0.05.

No model, coefficient, confidence threshold, particle count, or acquisition
rule is refit as archive size changes.

## Methods

- SC-DCTA (proposed method).
- ENS using the same posterior (strong nonmyopic active-search control).
- Hard-source DCTA (source-uncertainty ablation).
- ACIS-Risk (external risk-ranking baseline).
- Floored Prob-DCTA (superseded probability-floor ablation).
- Deterministic random replay.

Privileged-information oracles are omitted because the question is deployable
accuracy-cost scaling, not the finite-budget recall ceiling.

## Conditions and metrics

- Replay budgets: 2, 4, and 8.
- Missing provenance: 0%, 25%, and 50%.
- Primary condition: four replays and 25% missing provenance.

Accuracy and utility:

- weighted harmful-memory recall;
- audit yield;
- fraction of replay calls spent on added benign distractors;
- exposure-conditioned behavioral recovery at 25% missing provenance; and
- recovery conditional on localizing the forced harmful descendant.

Efficiency:

- posterior-construction wall time;
- acquisition wall time by method;
- number of posterior worlds; and
- peak traced Python allocation for a deterministic representative archive in
  each size/mask cell. This is not total GPU or native-library memory.

## Statistics and decision rule

Archive metrics are aggregated within task and compared with task-clustered
10,000-draw bootstrap intervals. SC-DCTA is not required to win every cell.
The method is considered practically scalable if increasing the archive from
21 to 200 candidates does not produce catastrophic recall collapse at the
primary fixed budget and its compute/memory growth remains executable on the
development machine. Exact degradation and runtime growth will be reported
regardless of direction.

No method modification follows from this Meta-World panel. Any new scaling
extension suggested by the result must be evaluated in a different domain or
new archive population.

