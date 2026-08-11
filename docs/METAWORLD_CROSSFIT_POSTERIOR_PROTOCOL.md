# Meta-World Cross-Fitted Posterior Study Protocol

## Scope and boundary

This study uses only the 10 Meta-World development tasks from publication v2.
Each fold holds out one complete task, including all source rotations and
provenance masks.  No validation or test artifact may be read.

The primary condition is four replays with 25% missing provenance.  Weighted
recall is primary.  All uncertainty intervals and win counts cluster by task.

## Fixed variants

1. **Frozen current model:** old-study source estimator and the existing
   all-development cascade fit.  This is the exact current-method reference,
   but its cascade fit is in-sample on development.
2. **External-source cross-fit:** old-study source estimator plus a cascade
   refit on the other nine Meta-World tasks.  This isolates cascade
   cross-fitting.
3. **Uniform-source cross-fit:** uniform source prior plus the same fold-specific
   cascade.  This tests whether the external source estimator adds value.
4. **Adapted-source cross-fit:** the unchanged six-feature source estimator and
   cascade are both fit on the other nine Meta-World tasks.  L2 remains 1.0 and
   the per-source probability floor remains 0.05.
5. **Known-source cross-fit:** fold-specific cascade with the true source,
   retained only as a diagnostic reference.

No feature, regularization value, mixture weight, or probability floor will be
selected after observing fold outcomes.

For every deployable variant, evaluate initial harm-label Brier score, log loss,
average precision, source Brier/top-1, Prob-DCTA weighted recall, source-then-DCTA,
ENS, and exact four-step posterior planning.  Budgets 2 and 8 and masks 0%, 25%,
and 50% are sensitivity conditions for implemented policies; exact planning is
restricted to the primary budget.

## Development continuation gate

The adapted source model is a promising replacement only if, relative to the
external-source cross-fit reference, it:

- improves primary weighted recall by at least 0.03;
- improves both source Brier and harm-label average precision;
- wins on at least six of ten held-out tasks; and
- does not lose more than 0.03 at budgets 2 or 8 or under the 0% and 50%
  provenance masks.

Failure of this gate means the existing six source features are insufficient;
it does not authorize post-hoc feature addition.

## Provenance leakage audit

The v2 public artifact retains `cited_memory_ids` even when the corresponding
formation edge is masked.  In the Meta-World development archives, 616 masked
true edges are explicitly cited, 104 masked true edges are not cited, and no
decoy edge is cited.  Direct citation membership would therefore reveal most
hidden edges almost perfectly.

This study will not use citation membership to infer latent edges.  A future
archive release must either remove a citation whenever its edge is masked or
declare cited edges observed and mask a different set of genuinely unobserved
relationships.

