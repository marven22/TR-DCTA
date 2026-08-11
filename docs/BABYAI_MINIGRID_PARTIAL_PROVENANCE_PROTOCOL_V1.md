# Frozen BabyAI/MiniGrid partial-provenance protocol v1

Status: frozen before running the paired partial-provenance method matrix.

## Question

Can SC-DCTA still find and quarantine a harmful three-memory lineage when some
formation links are unavailable, and how does its degradation compare with
budget-matched posterior-aware and non-adaptive methods?

## Paired design

The experiment reuses the 60 independently verified executable archives from
the frozen BabyAI/MiniGrid method-development result. Target missions, true
corrupted sources, source priors, memory behaviors, and replay labels never
change. Each archive is evaluated under three method-visible provenance views:

- `complete`: no links hidden;
- `partial_33`: two of six links hidden independently at each of three graph
  layers (6/18 links hidden);
- `partial_67`: four of six links hidden at each layer (12/18 links hidden).

At least two links are hidden per affected layer because a single missing link
in a known one-to-one layer can be recovered by elimination and does not create
real lineage ambiguity. Hidden subsets rotate deterministically by archive and
layer. Candidate identifiers are opaque to the methods and do not encode their
private source family.

## Inference

For every observed graph, the runner enumerates all one-to-one lineage
completions consistent with the visible links. Completions receive equal prior
mass conditional on the source prior. Worlds that yield the same source and
three-descendant set are aggregated exactly. No method sees the private
completion or an unqueried replay label.

SC-DCTA, probabilistic DCTA, hard-source DCTA, ENS, source information gain,
static risk, random replay, and a known-source ceiling share the same candidate
set, posterior support, observed links, and budgets of 2, 4, and 8. Random uses
50 deterministic replicates.

## Quarantine and recovery

After replay, every method may quarantine exactly three memories—the number of
corrupted descendants—ranked by its final posterior marginal corruption risk.
Quarantine therefore cannot use the hidden lineage merely because the predicted
source is correct. Quarantine precision/recall measure overlap with the three
truly corrupted descendants. Robot recovery succeeds only if all three harmful
memories are removed; otherwise forced harmful retrieval remains possible.

The primary acquisition metric remains corrupted-descendant recall among
replayed memories. Secondary metrics are audit yield, source identification,
quarantine recall/precision, and executable recovery.

## Development decision

Execution and grid completeness are mandatory. Averaging only the two partial
conditions at budget 4, SC-DCTA must not trail ENS, must beat random replay, and
must recover at least 80% of archives. Passing licenses a held-out symbolic
evaluation; it does not turn a tie with ENS into a superiority claim.
