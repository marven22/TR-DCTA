# Meta-World Development Oracle Diagnostic

## Scope

This diagnostic uses only the 10 Meta-World development tasks from the frozen
publication-v2 split.  It covers 90 related archive conditions: three active
source rotations and three provenance masks per task.  Statistical comparisons
cluster all variants by the underlying task.  No validation or test label was
read by the diagnostic.

The primary condition remains four replays with 25% of provenance edges hidden.
There are 21 replayable memories per archive.

## What was computed

- **Full-information oracle:** knows the realized harmful set and selects the
  exact best four-memory subset.  All 5,985 subsets were evaluated in every
  primary archive.  This is the unconditional four-replay ceiling.
- **Posterior-optimal planner:** receives the same sampled posterior as
  Prob-DCTA and exactly solves the finite adaptive decision problem.  This is
  optimal under the fitted model, not an unconditional ceiling when the model
  is misspecified.
- **Known-source planner:** exact posterior planning after revealing the true
  source.
- **Known-provenance planner:** exact posterior planning with the complete
  formation graph while retaining source uncertainty.
- **Known-source-and-provenance planner:** reveals both kinds of structural
  information but not the harmful labels.

Every adaptive policy observes a label only after selecting a memory.  No
posterior-support collapse occurred in the experiment.

## Primary result

Weighted recall is the frozen primary metric.

| Method or reference | Weighted recall | Raw fraction of hindsight ceiling | Incremental gap closure over random |
|---|---:|---:|---:|
| Full-information oracle | 0.748 | 100.0% | 100.0% |
| Known source + provenance, exact planning | 0.665 | 88.9% | 83.1% |
| Existing known-source DCTA reference | 0.617 | 82.4% | 73.3% |
| Known source, exact posterior planning | 0.590 | 78.8% | 67.8% |
| Known provenance, exact posterior planning | 0.566 | 75.7% | 63.0% |
| Source-then-DCTA | 0.479 | 64.0% | 45.4% |
| Exact planner under deployable posterior | 0.476 | 63.5% | 44.6% |
| Prob-DCTA | 0.469 | 62.6% | 43.3% |
| ENS | 0.427 | 57.0% | 34.7% |
| Random | 0.256 | 34.2% | 0.0% |

The exact deployable-posterior planner improves over Prob-DCTA by only 0.0067.
The 95% task-cluster bootstrap interval is [-0.0468, 0.0652], with five task
wins, one tie, and four losses.  In contrast, the hindsight oracle exceeds
Prob-DCTA by 0.2796, with interval [0.2072, 0.3859] and a positive gap in every
development task.

Therefore, the primary four-replay shortfall is not mainly caused by the
greedy acquisition rule.  Exact sequential planning under the current
posterior recovers almost none of the remaining realized gap.

## Where the gap comes from

Revealing the source to the exact planner adds 0.1141 over deployable posterior
planning, with interval [0.0524, 0.1714].  Revealing complete provenance adds
0.0908, with interval [0.0166, 0.1661].  Revealing both raises the score to
0.665, leaving only 0.083 below the hindsight ceiling.

Initial belief quality supports the same diagnosis:

| Information condition | Harm-label Brier (lower is better) | Harm ranking AP (higher is better) | Source top-1 |
|---|---:|---:|---:|
| Deployable information | 0.231 | 0.464 | 0.400 |
| Complete provenance | 0.209 | 0.544 | 0.267 |
| Known source | 0.086 | 0.855 | 1.000 |
| Known source + provenance | 0.065 | 0.957 | 1.000 |

The deployable posterior predicts the average amount of harm accurately—6.02
predicted versus 6.07 actual affected memories—but ranks the particular harmful
memories much less accurately.  This is a localization problem, not a total
harm-count problem.  Source uncertainty is the larger single contributor, and
missing provenance is also material.

The existing known-source DCTA heuristic realized a higher development score
than the model-optimal known-source planner.  This is not a contradiction: the
exact planner is optimal in expectation under the fitted posterior, whereas the
heuristic can outperform it on realized labels when the posterior differs from
reality.  This is additional evidence that posterior quality, rather than
search depth alone, deserves attention.

## Budget and provenance sensitivity

| Budget | Missing provenance | Full-information ceiling | Posterior-optimal | Prob-DCTA | ENS |
|---:|---:|---:|---:|---:|---:|
| 2 | 0% | 0.438 | 0.281 | 0.156 | 0.280 |
| 2 | 25% | 0.440 | 0.225 | 0.177 | 0.234 |
| 2 | 50% | 0.444 | 0.180 | 0.181 | 0.143 |
| 4 | 0% | 0.748 | 0.579 | 0.524 | 0.550 |
| 4 | 25% | 0.748 | 0.476 | 0.469 | 0.427 |
| 4 | 50% | 0.750 | 0.433 | 0.435 | 0.428 |
| 8 | 0% | 0.947 | not computed exactly | 0.840 | 0.877 |
| 8 | 25% | 0.947 | not computed exactly | 0.825 | 0.811 |
| 8 | 50% | 0.949 | not computed exactly | 0.823 | 0.857 |

Four replays cannot attain literal 100% recall even with hindsight because half
of the primary archives contain more than four harmful memories.  The exact
weighted ceiling is about 0.748.  Eight replays raise it to about 0.947.

Planning depth matters at budget two and when the graph is complete.  It adds
only 0.007 in the frozen primary condition and essentially nothing with 50%
missing provenance.  As graph information disappears, deeper planning cannot
recover information that the posterior does not possess.

The budget-eight posterior-optimal policy was not computed because exact
adaptive dynamic programming grows exponentially with horizon.  The exact
hindsight ceiling and all implemented-method results are included at budget
eight; no approximation is mislabeled as a ceiling.

## Decision

Do not build an ENS-specific replay-selection patch for the primary setting.
Prob-DCTA is already close to the exact policy induced by its current posterior.
The next method iteration should target **earlier and better localization of the
active source and missing formation links**, followed by exact or approximate
budget-aware planning once those beliefs improve.

The appropriate next development-only analysis is task-level cross-fitted
posterior calibration.  It should determine which observable source and edge
features fail to rank harmful descendants, without increasing the number of
free acquisition weights.  Any revised posterior must then be frozen on
validation and assessed on fresh Meta-World archive instances.

## Reproducibility

- Result artifact: `results/prob_dcta_metaworld_development_oracle_diagnostic.json`
- Runner: `scripts/run_prob_dcta_metaworld_development_diagnostic.py`
- Oracle implementation: `src/mcx/publication_v2_oracle.py`
- Unit tests: `tests/test_publication_v2_oracle.py`
- Runtime: approximately 91 seconds on the development machine
- Test suite after implementation: 152 passed

