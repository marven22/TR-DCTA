# SC-DCTA Particle Validation Protocol

Use only the 10 task-cross-fitted Meta-World development folds at the primary
four-replay, 25%-missing-provenance condition.  Compare the frozen 2,048-particle
SC posterior with an 8,192-particle reference generated from its own fixed seed.

Validation passes if mean marginal absolute difference is at most 0.015, worst
marginal difference is at most 0.05, worst source-probability difference is at
most 0.04, and mean absolute weighted-recall difference is at most 0.02.  These
thresholds are fixed before running the reference and do not select model
parameters.

