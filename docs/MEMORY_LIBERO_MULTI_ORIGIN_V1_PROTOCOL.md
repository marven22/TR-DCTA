# Memory-LIBERO Multi-Origin Probability Study v1

Status: frozen before construction or evaluation of composite private labels  
Protocol: `memory-libero/multi-origin-probability-v1`

## 1. Research question

When the invalid origin of a propagated agent-memory cascade is uncertain, does maintaining a joint posterior over origin identity and descendant corruption recover more harmful memories than committing to one origin first?

## 2. Empirical substrate

The study reuses the 67 strict Qwen2.5-14B Memory-LIBERO external archives. Each archive contains paired factual and counterfactual memories generated from the same LIBERO task, prompts, formation regime, and parent structure. The paired records supply real model-written memory text and simulator-grounded policy outcomes.

This is a new composite evaluation over previously generated archives, not a second untouched-domain claim. Base-archive identity is the bootstrap and split unit.

## 3. Multi-origin construction

For each base archive:

- use the first three pre-existing three-level formation branches;
- create three opaque candidate origin records with identical observable source text;
- connect each candidate origin to one branch gateway;
- create three rotations, each making a different origin active;
- instantiate the active branch from its factual Qwen records and the other two branches from their paired counterfactual records;
- remove policy identifiers and raw positional IDs from the public artifact;
- derive affected labels solely from the frozen simulator success map and factual/counterfactual policy difference.

The resulting archive has three plausible origins, nine replayable descendant memories, equal branch topology, and exactly one active origin. Some active cascades can have zero harmful descendants; these remain in calibration analyses but not positive-archive recall.

## 4. Observable source evidence

Source probabilities come from an explicit noisy forensic signal. A signal names one candidate origin. Assuming a uniform source prior and a symmetric channel, its declared accuracy is also the posterior probability of the signaled source.

Conditions:

- known: accuracy 1.00, upper-reference condition;
- high: true and assumed accuracy 0.75;
- medium: true and assumed accuracy 0.50;
- uniform: no source signal, probability 1/3 each;
- wrong60: true signal accuracy 0.20 but assumed accuracy 0.60.

Signal correctness is fixed by a SHA-256 draw from protocol, base archive, rotation, and condition. No memory labels are read when drawing the signal. The wrong60 condition is a stress test and cannot support the primary claim.

## 5. Posterior

For each possible origin, the frozen DCTA-Risk-Local v1 transition model generates an exact source-conditioned cascade posterior over the nine descendants. The source-conditioned posteriors are mixed using the observable source prior. Replays reveal only the selected descendant label and condition the full mixture.

No LIBERO-90 label is used to fit transition parameters, source-channel parameters, or acquisition weights.

## 6. Frozen methods

- random;
- static joint Risk, with no replay update;
- positive-only joint Risk, which ignores negative replays;
- DCTA-Top1, which hard-commits to the maximum-prior origin;
- Source-IG, which uses every replay for expected source-entropy reduction;
- Source-then-DCTA, one information-gain replay followed by DCTA-Risk;
- ENS on the same joint posterior;
- Prob-DCTA, DCTA-Risk on the full joint posterior;
- known-source DCTA, using the private active origin as an upper reference;
- exact Bayes oracle under the fitted joint posterior, reported as a model oracle rather than a truth oracle.

All risk acquisitions use unit harm weights. Ties are lexicographic. Random uses a fixed archive-specific SHA-256 ranking.

## 7. Splits and budgets

Base archives are hash-sorted before label construction into 10 development, 10 validation, and 47 test archives. Rotations and evidence conditions inherit the base split. The method and all parameters are already frozen; development and validation are used only for construction QA and stratified diagnostics. The larger test allocation is used because the prior external study established that harmful cascades are sparse.

Replay budgets are 2, 4, and 6 of nine descendants. Budget 4 is primary.

## 8. Metrics

Primary:

- positive-archive affected-memory recall at budget 4;
- discoveries per archive;
- audit yield.

Secondary:

- depth-weighted harm recall with weights 1, 2, and 3;
- source top-1 accuracy, Brier score, and entropy;
- performance by evidence condition, cascade regime, and budget;
- recovery under wrong60 prior misspecification;
- runtime and posterior world count.

Uncertainty uses 10,000 paired cluster-bootstrap draws over base archives. All rotations remain together within a resampled cluster.

## 9. Primary test and success criteria

The primary population is the untouched composite test split, calibrated ambiguous conditions (high, medium, uniform), positive archives, and budget 4.

The probability path is externally supported only if:

1. Prob-DCTA exceeds DCTA-Top1 in mean recall and its 95% paired cluster-bootstrap interval excludes zero.
2. Prob-DCTA exceeds positive-only joint Risk in mean recall.
3. Prob-DCTA is no worse than ENS by more than 0.03 recall.
4. At least one joint probability technique, declared in advance as Prob-DCTA or Source-then-DCTA, retains at least 90% of known-source DCTA recall.
5. Prob-DCTA improves source Brier score relative to the initial forensic prior.
6. The test split contains 47 base archives, at least 10 positive base-archive clusters, and at least 30 positive composite rows in the primary population.

Prob-DCTA remains the primary named method. Source-then-DCTA is a frozen secondary variant because it was identified in the preceding go/no-go study. Selecting whichever wins after this test is prohibited.

## 10. Validity limits

This study tests uncertain single-origin cascades with simulator-grounded outcomes and model-written memories. It does not yet test simultaneous multiple origins, noisy replay labels, online memory writing, cross-model transfer, or a second untouched robotics benchmark.
