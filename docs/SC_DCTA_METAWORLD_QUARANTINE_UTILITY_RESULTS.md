# Meta-World task-scoped quarantine utility results

## Result

The frozen utility analysis covers 49 tasks, 147 primary-condition archives,
3,087 candidate-memory instances, and replay budgets 2, 4, and 8. It reuses the
same task-cross-fitted and held-out audit paths as the recovery study.

## SC-DCTA utility and cost

| Replays per archive | Total replay calls | Harmful replays | Benign replays | Audit yield | Target-benign memories retained | Total target-context memories retained |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 294 | 273 | 21 | 92.9% | 2,168 / 2,168 | 2,814 / 3,087 |
| 4 | 588 | 504 | 84 | 85.7% | 2,168 / 2,168 | 2,583 / 3,087 |
| 8 | 1,176 | 803 | 373 | 68.3% | 2,168 / 2,168 | 2,284 / 3,087 |

All quarantined memories were confirmed target-task failures, so the
deterministic benchmark produced zero false quarantines and 100% retention of
target-benign memory. All clean-counterfactual candidate policies succeeded;
the same replay IDs would therefore quarantine zero clean memories.

The zero-false-quarantine result is a consequence of the confirmed-failure
quarantine contract under deterministic stored replay outcomes. It is not a
claim that real stochastic robot replay can never falsely fail. Fresh-seed or
outcome-noise robustness is required to estimate that deployment risk.

## Why quarantine must be task-scoped

Every identified harmful transfer was backed by a non-`NONE` donor policy that
had been locally validated on its formation task. A global-delete rule would
therefore have made the following locally useful memory instances unavailable:

| Replays per archive | Locally valid memories placed at global-delete risk | Cross-context withdrawals under task-scoped quarantine |
|---:|---:|---:|
| 2 | 273 | 0 |
| 4 | 504 | 0 |
| 8 | 803 | 0 |

This is the core collateral-utility result: the same experience can be unsafe
for the current target and useful in its original context. SC-DCTA's downstream
policy must attach the quarantine to the target context rather than erase the
artifact globally.

## Baseline audit efficiency

At the primary budget of four, the 147 archives yield:

| Method | Harmful replays | Benign replays | Audit yield |
|---|---:|---:|---:|
| SC-DCTA | 504 | 84 | 85.7% |
| ENS–SharedPosterior | 502 | 86 | 85.4% |
| Hard-source DCTA | 506 | 82 | 86.1% |
| Source-then-DCTA | 470 | 118 | 79.9% |
| Floored Prob-DCTA | 497 | 91 | 84.5% |
| Known-source DCTA | 515 | 73 | 87.6% |
| Full-information oracle | 547 | 41 | 93.0% |

SC-DCTA is efficient and competitive, but it is again statistically and
practically close to ENS–SharedPosterior and hard-source DCTA.

## Interpretation

Increasing replay budget improves harmful coverage and behavioral recovery,
but produces diminishing audit yield because the highest-risk memories are
tested first. The utility tradeoff is therefore primarily physical audit cost,
not loss of target-benign memory under the deterministic task-scoped rule.

The result also establishes a necessary implementation constraint for any
paper or deployed system: quarantine must be indexed by task or applicability
context. Describing the operation as global memory deletion would be both
scientifically inaccurate and harmful to locally valid experience.

## Artifacts

- Protocol: `docs/SC_DCTA_METAWORLD_QUARANTINE_UTILITY_PROTOCOL.md`
- Result ledger: `results/metaworld_quarantine_utility_all49.json`
- Analysis: `scripts/analyze_metaworld_quarantine_utility.py`
