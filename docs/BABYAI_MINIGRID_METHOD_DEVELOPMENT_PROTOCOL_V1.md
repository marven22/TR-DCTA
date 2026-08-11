# Frozen BabyAI/MiniGrid method-development protocol v1

Status: frozen before running the complete 60-archive method comparison.

## Scientific question

Does SC-DCTA use limited replay evidence to identify and quarantine a harmful
memory lineage in a symbolic, language-conditioned embodied environment, and
does it improve robot recovery relative to budget-matched alternatives?

This is a development experiment. It can determine whether the domain and
archive construction deserve a held-out paper-facing evaluation. It is not a
held-out result.

## Environment and contexts

The experiment uses the official `BabyAI-OpenDoorColor-v0` environment from
MiniGrid 3.0.0. The 60 deterministic contexts are seeds 0 through 59. Each
mission asks the agent to open a door of one of six colors.

## Archive construction

One archive is built per target context. It contains six source families and
three descendants per family (`nearest`, `farthest`, and `middle`), for 18
replayable memories total. Exactly one source family is corrupted.

A clean descendant reads the current mission and opens the requested color. A
corrupted descendant retains a locally correct lesson from its source context
and opens the source color regardless of the current mission. The corrupted
source color is always different from the target color. Consequently:

- all three corrupted descendants are first verified as successful on a donor
  context requesting their source color;
- all three fail when transferred to the target context; and
- all 15 clean descendants succeed on the target context.

Thus corruption is an executable behavioral property, not a synthetic label.
The private truth contains the corrupted source and replay outcomes; methods
receive only the archive structure and source prior before querying.

## Source uncertainty

The 60 archives are balanced across four preregistered regimes:

- `known`: the true source has probability 1;
- `calibrated`: the true source has probability 0.65;
- `ambiguous`: true and decoy probabilities are 0.30 and 0.28;
- `misleading`: the decoy has probability 0.55 and the true source 0.25.

These regimes test whether confidence-aware source commitment is useful and
whether probabilistic inference can recover from misleading prior evidence.

## Methods and budgets

Methods are SC-DCTA, probabilistic DCTA, hard-source DCTA, ENS, source
information gain, static risk, random replay, and a known-source DCTA ceiling.
Random replay uses 50 deterministic replicates. Every method receives exactly
2, 4, or 8 replay queries. A replay reveals only whether that queried memory
succeeds on the target context.

All non-oracle structured methods use the same source prior, candidates,
lineages, weights, and observed replay history. The oracle-source method is an
upper reference and is not claimed as a deployable baseline.

## Metrics

The primary metric is corrupted-descendant recall. Secondary metrics are audit
yield, source-identification accuracy, quarantine precision, and robot recovery
success. Recovery is successful exactly when quarantining the predicted source
removes the true harmful family: the forced harmful retrieval then disappears
and an already environment-verified clean memory remains executable.

The first development run uses complete provenance. Missing-provenance testing
is deliberately deferred until method value is established.

## Development decision rule

The run is eligible only if all 60 archives and environment-derived replay
labels verify and every method-budget cell completes. The domain advances only
if, at budget 4, SC-DCTA is not worse than ENS and is better than random on the
primary metric. Ties with strong structured baselines are reported honestly;
they are evidence that this version of the domain may be too easy to
differentiate acquisition methods.
