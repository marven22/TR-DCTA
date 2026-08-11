# Theory specification v0.4: terminal-recovery DCTA

## Status

This extension was specified on the already-open UnlockPickup development set
after the frozen SC-DCTA method failed its development gate. It does not alter
the earlier Meta-World or BabyAI OpenDoorColor results, and it has not yet been
evaluated on held-out UnlockPickup seeds.

The Bellman and rollout machinery below is standard approximate dynamic
programming. We do not claim rollout itself as a new mathematical invention.
The paper-facing contribution is the causal-memory decision formulation,
method instantiated for uncertain provenance and latent corruption origin,
model-relative guarantee, and executable recovery evaluation.

## Terminal decision objective

Let `P_t` be the posterior after replay history `H_t`, `A` the latent set of
harmful descendants, `C` the quarantine capacity, and

`Q_C = {Q subseteq V : |Q| = C}`.

For a quarantine decision `Q`, define

`u_rec(Q,A) = 1{A subseteq Q}`

and

`u_harm(Q,A) = sum_{i in Q} w_i 1{i in A}`.

The terminal decision is lexicographic:

`Q*(P_t) = argmax_{Q in Q_C} (E_Pt[u_rec(Q,A)], E_Pt[u_harm(Q,A)]).`

Thus full recovery is primary. Expected captured harm resolves recovery ties.
Opaque identifier order resolves any remaining tie. This avoids an arbitrary
scalar coefficient between recovery and harm.

## Base policy and rollout value

Let `mu` be probabilistic DCTA and let `V_b^mu(P,R)` be its expected terminal
utility with posterior `P`, remaining candidates `R`, and `b` replays left. At
`b=0`, this is the utility of `Q*(P)`. For candidate replay `i`, define

`Q_b^mu(P,R,i) = sum_{y in {0,1}} P(Y_i=y|P)
                 V_{b-1}^mu(P|Y_i=y, R minus {i}).`

TR-DCTA selects

`pi_b(P,R) = argmax_{i in R} Q_b^mu(P,R,i)`

and replans after observing the actual replay outcome. The implementation
integrates every positive-probability binary outcome exactly over the supplied
finite posterior and uses the complete remaining replay budget.

## Theorem: model-relative rollout dominance

For every finite posterior, ideal binary replay feedback, finite budget `B`,
and bounded terminal utility ordered as above, online TR-DCTA has expected
terminal utility no smaller than base probabilistic DCTA:

`V_B^TR(P,R) >=_lex V_B^mu(P,R).`

### Proof

Proceed by induction on remaining budget. At zero budget both policies apply
the same optimal terminal decision, so their values are equal. Assume rollout
dominance holds for `b-1` at every reachable posterior state. At budget `b`,
TR-DCTA selects the action maximizing expected `V_{b-1}^mu`. Therefore its
chosen action has rollout value at least that of the action selected by `mu`.
After the observation, TR-DCTA replans; by the induction hypothesis its
continuation value is no smaller than `V_{b-1}^mu` in every reachable child
state. Taking the posterior expectation preserves the lexicographic ordering.
Thus `V_b^TR >=_lex V_b^mu`. Induction proves the statement through `B`.

### Claim boundary

This is a guarantee under the modeled posterior. A misleading or misspecified
posterior can still make both policies choose poor actions. The theorem does
not claim Bayes-optimality because TR-DCTA evaluates each first action using a
DCTA continuation rather than recursively optimizing every future action.

## Computational boundary

For each possible current action, rollout branches over positive and negative
replay outcomes through the remaining budget. Worst-case work is exponential
in `B`; terminal quarantine enumerates `binomial(|V|,C)` sets. Caching and
posterior collapse make the 18-memory, capacity-three, budget-eight
UnlockPickup experiment practical, but larger archives require pruning,
limited-horizon rollout, or sampling. This limitation is explicit rather than
hidden behind the empirical results.

## Empirical correspondence

Every deployable method receives the identical terminal quarantine optimizer.
TR-DCTA differs only in replay acquisition. The full-information hindsight
ceiling alone receives the true affected set and is explicitly nondeployable.

The development result provides an objective-alignment check: TR-DCTA obtains
higher recovery and quarantine recall while replay-confirming less weighted
harm than ENS and SC-DCTA. This is expected rather than contradictory—replays
are selected for their decision value, not counted as the final remediation
objective.
