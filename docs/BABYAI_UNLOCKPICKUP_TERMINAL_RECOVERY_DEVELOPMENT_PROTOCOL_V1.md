# BabyAI UnlockPickup terminal-recovery development protocol v1

## Purpose

Resolve the objective mismatch exposed by the frozen UnlockPickup development
run without opening held-out seeds. The candidate method is Terminal-Recovery
DCTA (TR-DCTA). It optimizes the final capacity-limited quarantine/recovery
decision rather than treating replay-confirmed discoveries as the endpoint.

## Decision problem

For posterior `P_t`, remaining replay budget `b`, affected set `A`, and a
quarantine set `Q` of capacity three, terminal utility is lexicographic:

1. maximize `P_t(A subseteq Q)`, the probability that quarantine removes every
   harmful descendant and therefore permits recovery;
2. among recovery-equivalent decisions, maximize
   `E_t[sum_{i in Q} w_i Z_i]`, expected captured harm;
3. break remaining ties by opaque memory identifier.

The terminal quarantine optimizer is supplied identically to every deployable
method. The explicitly privileged full-information hindsight ceiling receives
the true affected set at terminal time and is not a deployable comparator.
Consequently, an advantage for TR-DCTA must arise from replay selection rather
than a privileged remediation rule.

## TR-DCTA acquisition

Probabilistic DCTA is the base rollout policy. At every decision point,
TR-DCTA evaluates each candidate next replay. For both possible binary replay
outcomes it conditions the complete posterior, follows the base DCTA policy
through every remaining replay slot, and evaluates the optimal terminal
quarantine. It chooses the action with the best posterior expected terminal
utility. After observing the real outcome, it replans.

This is a full-remaining-budget rollout, not a one-step discovery score. It is
exact for the supplied finite posterior and deterministic replay observation
model, conditional on the DCTA continuation policy.

## Policy-improvement property

At any belief state, the first action prescribed by the base DCTA policy is in
TR-DCTA's candidate action set. TR-DCTA chooses the action with the largest
expected terminal value when followed by that same base continuation. Its
rollout value is therefore no smaller than the base policy's value. Replanning
at later states preserves this inequality by backward induction. Thus, under
the modeled posterior and ideal replay feedback, TR-DCTA weakly improves the
base DCTA policy on the declared terminal utility. This is a model-relative
guarantee, not a claim of robustness to posterior misspecification and not a
claim of global Bayes optimality.

## Frozen development evaluation

Use only the already-open seeds 0--59 and the exact archive, provenance views,
source priors, corruption labels, budgets, and random trajectories from the
verified v1 development report. No environment or label is regenerated.

Methods are TR-DCTA and all v1 comparators. Every method receives its own final
posterior after its replay trajectory and the same terminal quarantine
optimizer. Conditions are complete, 33% missing, and 67% missing provenance;
budgets are 2, 4, and 8, with four primary.

## Frozen gate

Across the 120 partial-provenance views at budget four:

- TR-DCTA recovery must be no more than 0.05 below ENS;
- TR-DCTA recovery must be at least SC-DCTA recovery;
- TR-DCTA weighted quarantine recall must be no more than 0.05 below ENS; and
- TR-DCTA recovery must exceed random replay.

Only a verified pass licenses freezing TR-DCTA and opening seeds 60--299.
