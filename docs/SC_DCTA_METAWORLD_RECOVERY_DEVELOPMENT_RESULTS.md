# Meta-World recovery: development results

## Result

The leakage-safe end-to-end pipeline completed on the 10-task Meta-World
development split (30 archives: three source rotations per task, 25% missing
provenance, four replay means). All 160 deduplicated Qwen selections were valid.

The proposed behavioral endpoint is not sufficiently informative in its current
form and therefore did **not** pass the development gate:

- clean-reference success: 30/30 (100%);
- corrupted-archive success before auditing: 28/30 (93.3%);
- recoverable harmful archives: 2/30 (6.7%);
- archives whose retrieved top five contained any behaviorally harmful memory:
  4/30;
- mean harmful memories in the retrieved top five: 0.167 of 5;
- archives where Qwen selected a harmful memory: 2/30.

Thus the bottleneck is mostly exposure, not Qwen's ability to reject a visible
bad experience: in 26 of 30 archives, semantic retrieval never surfaced a
harmful memory in the first place.

At the common four-replay quarantine budget, SC-DCTA and all non-oracle
development comparators recovered 0/2 harmful cases. The full-information oracle
recovered 1/2. These two cases are too few for method comparison; the associated
bootstrap intervals are not substantively meaningful.

## Interpretation

This is not evidence that SC-DCTA fails at audit localization. It shows that the
current archive construction plus ordinary semantic retrieval rarely turns the
known latent corruption into an actual downstream task failure. Consequently,
weighted harmful-memory recall and end-to-end behavioral recovery answer
different questions in this benchmark.

Running the held-out 29 tasks now would spend the test set on an endpoint that
the development split has shown to be underpowered. The held-out behavioral run
is therefore deferred.

## Required next design step

Define an exposure-conditioned behavioral test without changing SC-DCTA. A
valid design should create queries for which a harmful descendant is genuinely
retrieved, then compare every auditor under the same query, replay budget,
quarantine rule, and execution model. The construction must be frozen on the
development tasks and must report both:

1. unconditional real-world-like incidence (how often ordinary retrieval is
   harmful), and
2. conditional recovery given harmful exposure (whether auditing repairs a
   failure once exposure occurs).

This separates the prevalence of dangerous retrieval from the quality of the
audit method and avoids manufacturing a favorable result by relabeling all
latent corruptions as behavioral failures.

## Artifacts

- `results/metaworld_recovery_development_observable.json`
- `results/metaworld_recovery_development_private.json`
- `results/metaworld_recovery_development_events.json`
- `results/metaworld_recovery_development_evaluation.json`
