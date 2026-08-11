# V6 MemoRepair Compatibility Results

## Result in one sentence

MemoRepair is the better mechanism when influence provenance is complete, but
its reachability-based scope collapses under missing provenance; ACIS-T recovers
most affected descendants at a fixed replay cost, and the hybrid converts those
discoveries into MemoRepair's barrier-and-validation workflow.

Canonical run: `results/memoryarena_v6_memorepair_20260803_r3`.

This is a development compatibility study, not an exact reproduction of the
authors' MemoryArena result and not a final held-out experiment.

## What was implemented

The reimplementation follows the public [MemoRepair paper](https://arxiv.org/abs/2605.07242):

- influence-reachability cascade construction;
- barrier-first withdrawal;
- deterministic artifact-aware repair modes;
- executability and predecessor-closure constraints;
- exact fixed-lambda (`lambda=0.3`) maximum closure via one min-cut;
- topological repair execution; and
- validation-gated republication with failure propagation.

The authors' code and benchmark-specific candidate values, costs, repair
operators, and validation suite are not public. We therefore label this
`MemoRepair reimplementation`, use the paired clean archive as the replay and
validation oracle, and freeze uniform `w_i=c_i=1`. Under this neutral adapter,
all executable candidates have positive utility, so MemoRepair is equivalent to
Repair all inside the cascade. We do not claim to reproduce the paper's reported
selector savings.

## Main comparison

Each noisy condition has 30 archives x 10 masks. Recall is the fraction of the
four truly affected descendants repaired. Cost is operations divided by the 49
post-source records required for full replay.

| Provenance condition | MemoRepair recall | ACIS-T recall | Hybrid recall | MemoRepair ops | ACIS-T ops | Hybrid ops |
|---|---:|---:|---:|---:|---:|---:|
| Complete | 1.000 | 1.000 | 1.000 | 4.00 | 13.00 | 17.00 |
| 25% records missing | 0.607 | 0.983 | 0.983 | 2.43 | 13.00 | 16.93 |
| 50% records missing | 0.293 | 0.951 | 0.951 | 1.17 | 13.00 | 16.80 |
| 75% records missing | 0.093 | 0.863 | 0.863 | 0.37 | 13.00 | 16.45 |
| 100% records missing | 0.000 | 0.667 | 0.667 | 0.00 | 13.00 | 15.67 |
| Direct edge forced missing + 75% others missing | 0.000 | 0.860 | 0.860 | 0.00 | 13.00 | 16.44 |
| Same + 25% spurious logical edges | 0.013 | 0.865 | 0.867 | 0.33 | 13.00 | 17.18 |

The paired archive-bootstrap interval for MemoRepair minus ACIS-T recall in the
forced-direct condition is `[-0.897, -0.822]`; the estimate is `-0.860`.

## Interpretation

With the complete graph, MemoRepair is ideal: it finds all four affected nodes
without searching the 49 candidates. It performs four repairs, compared with
13 ACIS-T replays. This confirms that ACIS-T is unnecessary when provenance is
perfect.

When an early link is absent, however, MemoRepair cannot know that the hidden
branch belongs in its withdrawal cascade. In the forced-direct condition it
repairs nothing and leaves all affected descendants stale. This is not an
implementation failure; it is the method's stated completeness assumption. The
paper itself identifies complete influence provenance as its principal system
invariant and reports strong leak amplification from small edge-drop rates.

ACIS-T pays more because it searches behaviorally: it replays 13 candidates and
validates whether each changes under the source correction. That lets it recover
0.860 recall even when the direct provenance link is guaranteed absent. Its
precision remains 1.0 because only replay-confirmed artifacts are repaired.

The hybrid does not materially exceed ACIS-T recall in these archives because
the discoveries supplied to MemoRepair are already the repaired items. Its value
is architectural: ACIS-T supplies missing scope; MemoRepair supplies withdrawal,
predecessor ordering, and validation-gated publication. Hybrid cost here is a
conservative upper bound that double-counts discovery replay and repair; a real
implementation should reuse successful replay outputs.

Spurious edges create unnecessary withdrawal and repair. In the combined-noise
condition MemoRepair alone scopes 0.283 clean artifacts per event on average,
while still recalling only 0.013 of affected descendants. The hybrid scopes
0.710 clean artifacts because discovered true nodes can connect to false
downstream edges. This exposes the next unsolved problem: robustly deciding
which recorded or inferred edges deserve enough trust to trigger cascade-wide
withdrawal.

## Claim boundary and next experiment

This result supports a sharper research claim than “our repair system beats
MemoRepair”: the two systems solve different layers. MemoRepair is a strong
repair contract conditional on reliable provenance. Our contribution is
provenance recovery under missing records, followed by safe repair. The credible
next method is therefore uncertainty-aware cascade repair: ACIS discoveries and
recorded edges receive calibrated confidence, and the system jointly chooses
additional probes and a conservative withdrawal/repair set under asymmetric
stale-leak versus collateral-repair costs.

Before a paper-level comparison, we still need (1) author clarification or code
for MemoRepair's unpublished `w_i,c_i` and validation details, (2) held-out
archives, and (3) cost curves rather than the single 25% ACIS-T budget.

