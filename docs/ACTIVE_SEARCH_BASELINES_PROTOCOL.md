# ENS and Graph Active Search baseline protocol

## Status

Implementation specification frozen before either baseline is joined to the
LIBERO external-test labels.

## Sources and fidelity

- **ENS:** Jiang et al., *Efficient Nonmyopic Active Search* (ICML 2017).
  The authors release MATLAB code in
  `shalijiang/efficient_nonmyopic_active_search`. The native implementation in
  `src/mcx/active_search_baselines.py` preserves the sequential acquisition:
  immediate positive probability plus the expected sum of the largest
  conditional probabilities available under the remaining budget. Because the
  DCTA posterior enumerates finite worlds exactly, label-outcome integration is
  exact rather than Monte Carlo.
- **Graph Active Search:** Wang et al., *Active Search on Graphs* (KDD 2013).
  No author implementation specific to this paper was located. The native
  implementation follows equations 1--3: the soft-label graph model with prior,
  positive-conditioned impact, and `probability + alpha * impact` acquisition.

## Shared evaluation contract

- Known invalid source is the initial positive label.
- A replay reveals one candidate label only after the method selects it.
- Budgets are 2, 4, 6, and 9; the locked primary budget remains 4.
- Deterministic lexical candidate-id tie breaking is used.
- ENS receives the same frozen finite-world posterior as DCTA for the
  acquisition-only comparison.
- Graph Active Search uses the formation DAG symmetrized into the undirected
  graph assumed by the paper.

## Graph Active Search development-only parameters

- `eta = 0.5`, as fixed in the paper.
- `prior_strength = 1 / n`, as fixed in the paper.
- The positive prior is estimated from the old development archives only.
- `alpha` is selected on the old development archives only from the paper's
  grid `{0, 0.1, 0.01, 0.001, 0.0001}` and then frozen.
- Ties are resolved by higher mean discoveries and then smaller `alpha`.

No LIBERO external-test label may be used to choose the prior or `alpha`.
