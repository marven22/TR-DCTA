# Memory-LIBERO Multi-Origin v2 Publication Protocol

Status: feasibility stage frozen before fresh simulator screening  
Protocol: `memory-libero/multi-origin-publication-v2`

## 1. Objective

Produce a publication-grade, independently generated robotics memory-auditing benchmark for uncertain corruption origins. The benchmark must be harder than v1, preserve a real held-out boundary, and support claims about joint origin localization and harmful-descendant recovery under limited replay.

## 2. Held-out boundary

The candidate population contains exactly 40 LIBERO tasks for which no persistent-memory archive has previously been generated in this repository:

- `libero_90`: 23 tasks;
- `libero_spatial`: 4 tasks;
- `libero_object`: 3 tasks;
- `libero_goal`: 4 tasks;
- `libero_10`: 6 tasks.

Prior simulator screening does not disqualify a task; prior memory generation, method fitting, or memory-label evaluation does. The frozen manifest records every task index.

Fresh policy interventions use demonstrations 2 and 3 for `libero_90`, whose earlier external generation used demonstrations 0 and 1. The four 10-task suites use demonstrations 0 and 1 because their previous broad screens used demonstrations 2 through 9. No previously generated memory text is reused.

## 3. Feasibility screen

For every held-out target:

1. replay both native demonstrations twice on their corresponding target initial states;
2. retain the target only when every native replay succeeds;
3. order same-suite donor tasks by SHA-256 of protocol, suite, target, and donor;
4. replay both donor demonstrations twice on the target initial states;
5. retain a donor only when all four transfers fail;
6. stop after three verified failing donors or exhaust the suite.

The production study proceeds only if at least 24 targets have three verified donors, at least three suites contribute, and no single suite contributes more than 75% of eligible targets. A failed gate requires a genuinely external robotics benchmark; it may not be weakened after outcomes are observed.

## 4. Fresh archive design

Each eligible task receives three independently generated source-conditioned branches, one per verified donor:

- three opaque candidate origins;
- five private descendants per origin;
- six cross-branch/shared descendants with merge, bridge, and revival motifs;
- at least 21 replayable memories total;
- one hash-selected active origin for the primary archive;
- the other origin rotations retained only as clustered robustness variants.

For each node, Qwen2.5-14B writes paired factual and corrected-counterfactual memories from prompts that differ only through source-descended state. Policy identifiers are removed from the public artifact. Simulator success determines functional labels; the model never labels its own memory.

Shared descendants are generated once for each possible active origin plus one all-clean counterfactual, so overlap is behavioral rather than merely graph decoration.

## 5. Provenance and source uncertainty

The public graph includes timestamps and observed formation links. Source-to-gateway and selected internal links are masked at frozen rates of 0%, 25%, and 50%; the 25% mask is primary. Candidate missing links remain explicit latent hypotheses rather than being treated as impossible.

The primary source prior is produced by a frozen observable estimator trained only on the old 67 LIBERO-90 archives. Features may include source/descendant content similarity, formation-task compatibility, observed link support, branch coherence, and timestamp consistency. No v2 private label may fit or select the estimator.

Uniform, calibrated controlled, and deliberately misspecified priors are secondary robustness conditions.

## 6. Frozen methods

- random;
- static calibrated risk;
- prior-weighted ACIS-Risk;
- positive-only joint Risk;
- DCTA-Top1;
- Source-IG active localization;
- Source-then-DCTA;
- ENS on the shared joint posterior;
- Prob-DCTA;
- known-source DCTA reference;
- exact Bayes/model oracle on projected subgraphs where tractable.

Prob-DCTA is the primary method. The v2 test set may not be used to choose between Prob-DCTA and Source-then-DCTA.

## 7. Splits and execution

Eligible targets are hash-split by task, stratified by suite, into development, validation, and test after the feasibility screen. Only development may diagnose generation failures. Validation freezes the observable source estimator and any scalable-posterior approximation. The test split is joined once after all code and configurations are hash-frozen.

Budgets are 2, 4, and 8; budget 4 is primary. Statistical resampling is clustered by underlying LIBERO target, keeping origin rotations and provenance masks together.

## 8. Endpoints

Primary:

- affected-memory recall at budget 4;
- depth-weighted harmful-memory capture;
- paired task-cluster difference between Prob-DCTA and DCTA-Top1.

Secondary:

- comparisons with positive-only Risk, ACIS-Risk, ENS, and Source-then-DCTA;
- source top-1/top-2 accuracy, Brier score, and entropy reduction;
- oracle regret on projected graphs;
- performance by provenance missingness, overlap, depth, source-prior quality, and budget;
- runtime, memory use, and posterior approximation error.

## 9. Publication gate

The main empirical claim requires:

1. Prob-DCTA exceeds DCTA-Top1 and the task-cluster 95% interval excludes zero.
2. Prob-DCTA exceeds prior-weighted ACIS-Risk.
3. Prob-DCTA is noninferior to ENS within 0.03 recall.
4. Prob-DCTA retains at least 85% of known-source recall.
5. Prob-DCTA improves source Brier score on all test archives, not only positive archives.
6. The negative-evidence advantage persists under the primary 25% provenance mask.
7. At least 15 independent positive test tasks contribute to the primary endpoint.

Failure is reported without retuning. Passing does not remove the need for a second writer model or external robotics-domain validation before the strongest generality claim.

