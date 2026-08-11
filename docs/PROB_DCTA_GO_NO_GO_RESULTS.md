# Prob-DCTA Go/No-Go Results v0.1

## Decision

**GO on the latent-origin probability path. Do not yet lock vanilla Prob-DCTA as the sole final acquisition rule.**

The frozen primary gate passed all five criteria. Joint origin/descendant conditioning is useful and materially better than committing to one source. However, a simple one-information-query-then-DCTA hybrid slightly outperformed Prob-DCTA at the primary budget, revealing a better acquisition-design question for the full study.

## Primary frozen experiment

The benchmark used 60 exact finite-world instances: four propagation levels, three forensic signals, four calibrated source-confidence conditions, and one wrong-prior stress condition. Each instance had three structurally matched possible origins, nine replayable descendants, and a replay budget of four. No sampling or LLM calls were used.

### Pooled calibrated ambiguous origins

| Method | Weighted utility | Harm recall | Source Brier |
|---|---:|---:|---:|
| DCTA-Top1 | 2.025 | 0.753 | 0.944 |
| Positive-only Risk | 2.648 | 0.845 | 0.239 |
| ENS | 2.928 | 0.944 | 0.170 |
| **Prob-DCTA** | **3.030** | **0.920** | **0.201** |
| Source-then-DCTA | 3.088 | 0.949 | 0.186 |
| Exact Bayes oracle | 3.127 | — | — |

Prob-DCTA gained 1.005 weighted discoveries over DCTA-Top1 and 0.382 over Positive-only Risk. It closed 91.2% of the Top1-to-oracle gap and exceeded ENS by 0.102 weighted utility. Source Brier improved from an initial 0.566 to 0.201.

### Gate

| Frozen criterion | Result |
|---|---|
| Exact reduction to current DCTA at source probability 1 | Pass |
| Beat Top1 and Positive-only under ambiguity | Pass |
| Close at least 20% of Top1-to-oracle gap | Pass: 91.2% |
| Remain within 0.02 of ENS | Pass: exceeded ENS by 0.102 |
| Improve source Brier score | Pass |

## Wrong-prior stress test

When the model assigned 0.60 probability to an origin whose true probability was only 0.20, Prob-DCTA still achieved 2.894 weighted utility, compared with 1.238 for DCTA-Top1 and 2.696 for ENS. The hybrid reached 2.943. Thus full posterior support allows recovery from a bad prior, while hard Top1 commitment cannot recover discarded origins.

This is a controlled stress result, not evidence that arbitrary prior misspecification is harmless.

## Exploratory budget robustness

| Budget | DCTA-Top1 | ENS | Prob-DCTA | Source-then-DCTA | Oracle |
|---:|---:|---:|---:|---:|---:|
| 2 | 1.397 | 1.140 | **1.582** | 1.357 | 1.688 |
| 3 | 1.806 | 2.323 | 2.480 | **2.568** | 2.661 |
| 4 | 2.025 | 2.928 | 3.030 | **3.088** | 3.127 |
| 5 | 2.328 | **3.262** | 3.236 | 3.255 | 3.262 |

The preferred information/utility tradeoff depends on budget. Under a very tight budget, spending a replay purely on localization is too expensive and Prob-DCTA's integrated risk rule wins. At moderate budgets, one explicit information-gain replay improves later DCTA choices. At budget five, the small benchmark nearly saturates and ENS reaches the oracle.

## Scientific interpretation

The important result is not merely that probabilities help. It is that **hard source commitment destroys recoverable support**, while joint inference lets negative descendant evidence redirect the audit. The hybrid result further shows that source identification and harmful-memory capture should be treated as a coupled, budget-dependent decision problem.

The current controlled benchmark is intentionally favorable to exact inference and uses matched synthetic branches. It does not establish performance on realistic LLM-agent archives, incomplete provenance, semantic ambiguity, multiple simultaneous origins, or noisy replay labels.

## Next experiment

Proceed to the realistic multi-root archive study with both Prob-DCTA and Source-then-DCTA carried forward. The full study should not choose between them using these development results. Instead, predeclare either:

1. both as frozen variants with budget-stratified hypotheses; or
2. a unified acquisition rule that explicitly trades expected harmful-memory capture against source information gain, calibrated only on a development split.

Required comparators remain DCTA-Top1, Positive-only/ACIS-Risk, ENS, active source localization, and an oracle on tractable archives.

## Artifacts

- Protocol: `docs/PROB_DCTA_GO_NO_GO_PROTOCOL.md`
- Primary output: `results/prob_dcta_go_no_go_v0_1.json`
- Budget robustness: `results/prob_dcta_budget_robustness_v0_1.json`
- Implementation: `src/mcx/prob_dcta_benchmark.py`
- Runner: `scripts/run_prob_dcta_go_no_go.py`
- Tests: `tests/test_prob_dcta_benchmark.py`
