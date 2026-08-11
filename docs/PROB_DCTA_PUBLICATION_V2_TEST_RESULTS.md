# Prob-DCTA Publication v2 Frozen Test Results

## Outcome

The frozen publication gate **did not fully pass**. Prob-DCTA establishes a
clear advantage over hard source commitment and the prior ACIS-Risk baseline,
but narrowly misses the ENS noninferiority margin and does not retain the
predeclared fraction of known-source performance.

## Primary endpoint (budget 4, 25% missing provenance)

| Method | LIBERO recall | Meta-World recall | Pooled recall |
|---|---:|---:|---:|
| DCTA-Top1 | 0.262 | 0.254 | 0.256 |
| ACIS-Risk | 0.203 | 0.270 | 0.250 |
| ENS | 0.349 | 0.486 | 0.446 |
| Prob-DCTA | 0.299 | 0.457 | 0.411 |
| Source-then-DCTA | 0.307 | 0.489 | 0.435 |
| Known-source reference | 0.488 | 0.618 | 0.580 |

Prob-DCTA minus Top1 is 0.154
(task-cluster 95% CI [0.100,
0.210]). Prob-DCTA minus
ACIS-Risk is 0.161. The
ENS gap is -0.035, versus the frozen -0.030 noninferiority margin.

Source Brier improves from 0.781 to 0.075, and final
source top-1 accuracy is 95.122%. Prob-DCTA retains 70.9%
of known-source recall.

## Pre-specified budget sensitivity

At budget 8 with the same 25% missing-provenance condition, Prob-DCTA reaches
0.772 recall, versus
0.469 for Top1,
0.790 for ENS, and
0.870 for the known-source
reference. Thus, at budget 8 the ENS gap is
-0.019
and known-source retention is
88.7%.
This sensitivity was pre-specified, but it does not replace the failed budget-4
primary gate.

## Integrity and scale

- 41 independent test tasks: 12 LIBERO and 29 Meta-World.
- 123 task/origin rotations and 369 rotation/provenance-mask archives.
- Affected-set size 2–10; mean 6.60.
- 118/123 rotations contain shared functional harm.
- All contamination and harm have a directed causal path.
- 9 of 2460 writer records used the logged deterministic format sanitizer.

## Interpretation

The central scientific result survives: preserving origin uncertainty and
conditioning on negative replay evidence materially beats committing to one
suspected source. The current acquisition rule is not yet the best finite-
budget search policy: ENS is stronger, especially on LIBERO, and the
predeclared known-source retention target is missed. `Source-then-DCTA` also
outperformed the frozen primary method on this test set, but it was secondary
and cannot be promoted post hoc. The next method-development iteration should
target the exploration/exploitation objective on development data and then be
tested on a new untouched benchmark—not retuned on these labels.
