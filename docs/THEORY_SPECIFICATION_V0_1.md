# Theory Specification v0.1

## Source-Conditioned Active Cascade Discovery under Uncertain Provenance

Date: 2026-08-04  
Status: pre-method specification; no held-out benchmark may be inspected while
this specification is being used to derive a successor method  
Relationship to prior work: ACIS-Risk v1 is frozen as an empirical baseline;
its probability-times-impact acquisition is not claimed as novel

## 1. Research question

An agent has learned a persistent archive of memories. One earlier memory is
now known to be invalid. Some later memories may have inherited its error, but
the archive's recorded provenance is incomplete and may contain false links.
Replaying every later memory is too expensive.

The primary question is:

> Given a known invalid source, an unreliable record of how later memories
> were formed, observable memory content, and a limited replay budget, which
> memories should be replayed adaptively to discover and repair the largest
> amount of source-caused contamination?

The theoretical object is called **Source-Conditioned Active Cascade
Discovery under Uncertain Provenance (SCACD-UP)**.

The phrase *source-conditioned* is essential. The target is not every bad,
unsafe, or low-quality memory. It is the set of later memories whose contents
would have been different under an intervention that corrected the known
source before those memories were formed.

## 2. Novelty boundary

SCACD-UP contains a classical active-search problem: replaying a memory is a
label query, an affected memory is a positive, and the budgeted objective is to
find positives. Bayesian active search, nonmyopic active search, graph active
search, value of information, troubleshooting, and graph-corruption theory are
therefore foundations and mandatory comparators.

In particular, ACIS-Risk v1 uses

`p_i * (1 + sum_j positive_probability_uplift(i,j))`.

At exploration coefficient one, this is algebraically the positive-branch
impact heuristic in Wang, Garnett, and Schneider's *Active Search on Graphs*
(KDD 2013). The directed temporal archive, calibrated signals, and unreliable
provenance are useful application structure, but they do not make that product
a new acquisition principle.

The candidate research gap is narrower:

1. the query target is the causal cascade of one known invalid source;
2. the true influence graph is latent;
3. the observed provenance graph has both missing and spurious edges;
4. content can provide evidence when provenance fails;
5. queries reveal individual counterfactual effects and permit repair; and
6. query decisions are adaptive and budgeted.

The literature review has not identified one prior formulation or result that
jointly covers all six items. This is a candidate gap, not by itself a novelty
claim. A publishable contribution must establish a nontrivial result about
their interaction.

## 3. Objects and notation

| Symbol | Meaning |
|---|---|
| `V = {s, 1, ..., n}` | Memories in creation-time order |
| `s` | Known invalid source memory |
| `V+ = V minus {s}` | Replay candidates |
| `G* = (V,E*)` | Latent true influence DAG |
| `G~ = (V,E~)` | Observed, potentially corrupted provenance DAG |
| `X_i` | Observable features of memory `i`, including content and formation context |
| `Z_i in {0,1}` | Whether memory `i` is causally affected by `s` |
| `Y_i` | Outcome returned by replaying `i` |
| `c_i > 0` | Replay cost |
| `w_i >= 0` | Value of discovering and repairing affected memory `i` |
| `B` | Total replay budget |
| `H_t` | Query-outcome history after `t` replays |
| `pi` | Adaptive replay policy |

Edges always respect creation time: `(u,v)` is permitted only when `u` was
created before `v`. Consequently, both `G*` and `G~` are DAGs.

The true influence graph is not the same as the affected set. An edge means
that an earlier memory influenced the formation of a later one. A true
influence need not transmit the source error. Conversely, an affected memory
must be connected to the source by a transmitting causal route under the base
model below.

## 4. Counterfactual affected label

Let `M_i(1)` be the memory produced by the original history in which source
`s` is invalid. Let `M_i(0)` be the memory produced by a paired intervention
that corrects `s` and regenerates all causally necessary later computations
while holding exogenous task conditions fixed.

Define

`Z_i = 1{D(M_i(1), M_i(0)) >= tau}`, for `i in V+`,

where `D` is a preregistered behavioral or semantic discrepancy measure and
`tau` is a preregistered threshold. In deterministic constructed archives,
`Z_i` may instead be the exact indicator that the paired memories differ in a
task-relevant way.

This definition prevents an unrelated bad memory from being labeled as a
descendant of the source merely because it also causes failure.

### Assumption A1: counterfactual consistency

The replay intervention used to obtain `Y_i` implements the same correction
contract used to define `Z_i`.

### Assumption A2: ideal replay feedback in the primary model

`Y_i = Z_i`.

Thus a replay perfectly identifies whether the source affected the candidate.
Noisy or abstaining replay is an extension, not part of the first theorem
model.

## 5. Latent cascade model

The general formulation allows any joint distribution

`P(G*, Z, X | s)`

that respects temporal order and source conditioning. For constructive
theorems and simulation, the first restricted model is an independent-edge
cascade on a rooted temporal tree or polytree:

1. `Z_s = 1`;
2. every true edge `(u,v)` has an unobserved transmission variable
   `T_uv ~ Bernoulli(theta_uv)`;
3. `Z_v = 1` if and only if at least one affected parent `u` has `T_uv = 1`;
4. conditional on `Z`, observable features follow preregistered emissions
   `X_i ~ P_1` when affected and `X_i ~ P_0` when clean.

The tree/polytree restriction is a tractability device, not a claim that real
agent archives are trees. The general-DAG setting remains the target empirical
setting.

### Assumption A3: no source-independent positives

Under the primary model, `Z_i = 1` only through transmission from `s` in `G*`.
Background defects may exist in an archive but receive label zero for this
source-conditioned task.

### Assumption A4: calibrated model or declared misspecification

Any theorem using posterior probabilities assumes that the stated graph,
transmission, and feature-emission model is correctly specified. Experiments
must separately measure performance under misspecification.

## 6. Uncertain-provenance observation channel

The true graph is never directly supplied to the policy. A baseline stochastic
channel produces the observed graph independently across temporally legal
edges:

`P((u,v) in E~ | (u,v) in E*) = q_uv`,

`P((u,v) in E~ | (u,v) not in E*) = r_uv`.

Here, `q_uv` is edge-retention probability and `r_uv` is false-edge insertion
probability. Homogeneous experiments use `q_uv = q` and `r_uv = r`.

The theory must also admit a distributionally robust version in which the
channel is unknown but belongs to an uncertainty set, for example

`q_uv in [q_min,q_max]` and `r_uv in [r_min,r_max]`.

The policy observes

`O_0 = (s, G~, X, creation_order, c, w)`

and maintains a posterior or robust belief over both `G*` and `Z`. Treating a
missing observed edge as proof of no influence is prohibited unless `q=1` and
`r=0` are known.

## 7. Queries, histories, and policies

At time `t`, a policy selects an unreplayed candidate

`I_t = pi(H_t, O_0)`.

It pays `c_{I_t}`, observes `Y_{I_t}`, repairs the memory if `Y_{I_t}=1`, and
updates its belief. The history is

`H_t = ((I_1,Y_{I_1}), ..., (I_t,Y_{I_t}))`.

The selected set must satisfy

`sum_{i in Q_pi} c_i <= B`.

Policies may be randomized, but they may not inspect an unqueried `Z_i` or the
latent graph. In the current unit-cost benchmark, all `c_i=1`.

## 8. Primary and secondary objectives

### 8.1 Primary: replay-confirmed repair value

The primary utility is

`U_B(pi) = E[sum_{i in Q_pi(B)} w_i Z_i]`.

For `w_i=1`, this is the expected number of affected memories discovered and
repaired under budget `B`, exactly the active-search utility.

The corresponding affected-set recall is

`Recall_B(pi) = (sum_{i in Q_pi(B)} Z_i) / max(1, sum_{i in V+} Z_i)`.

Expected discovery count is the theorem objective because the random
denominator makes expected recall less convenient. Recall remains the primary
empirical reporting metric when every archive has a controlled affected-set
size.

### 8.2 Secondary: residual downstream harm

Where a validated behavioral evaluator exists, define

`L_after(pi) = E[downstream_loss after replay-confirmed repairs]`.

This connects discovery to agent safety. It must not replace the primary
objective unless the mapping from repairs to downstream loss is formally
specified. Discovery recall and behavioral repair are distinct claims.

### 8.3 Precision contract

Only replay-confirmed positives are repaired. Under A2, repair precision is
one. Methods that proactively repair unqueried candidates require a different
utility with collateral-repair cost and are outside v0.1.

## 9. Exact finite-instance Bayes oracle

For small instances with unit costs, the Bayes-optimal value satisfies

`V_0(H) = 0`,

`V_b(H) = max over unqueried i of [`

`  p_i(H) * (w_i + V_(b-1)(H union {(i,1)}))`

`  + (1-p_i(H)) * V_(b-1)(H union {(i,0)}))`

`]`,

where `p_i(H) = P(Z_i=1 | O_0,H)`.

This dynamic program is exponential and is intended only for archives of
roughly 8--12 candidates. It gives:

1. a correctness oracle for implementations;
2. an upper comparator for practical policies on small instances;
3. exact examples showing when one-step heuristics fail; and
4. a way to test conjectured structural results before attempting proofs.

The oracle itself is established Bayesian active search, not a contribution.

## 10. Initial formal results

The following results are part of the specification. They establish basic
limits and prevent invalid theorem claims; they are not sufficient alone for a
top-tier theory contribution.

### Proposition 1: no-evidence exchangeability bound

Suppose there are `n` candidates, exactly `k` are affected, the affected set is
uniform over all size-`k` subsets, provenance supplies no information, and
`P(X_i | Z_i=1) = P(X_i | Z_i=0)`. Then every adaptive policy making `B`
distinct unit-cost queries has

`U_B(pi) = Bk/n`.

#### Proof sketch

Before any query, candidate labels are exchangeable. After any history, the
unqueried candidates remain exchangeable with the remaining positives
uniformly distributed among them. Hence query identity cannot change the
conditional chance of success. Equivalently, symmetry gives each of the `k`
positives inclusion probability `B/n`; linearity of expectation yields
`Bk/n`. Adaptivity does not break the symmetry.

#### Meaning

Without informative provenance or content, no clever acquisition rule can
beat random replay. Recoverability requires an explicit source of asymmetry.

### Lemma 1: path visibility under independent deletion

If every true edge is independently retained with probability `q`, a specified
true path of length `d` is completely visible in `G~` with probability `q^d`.

#### Meaning

Graph-only reachability degrades exponentially with causal depth even before
false edges are considered. This motivates, but does not prove the optimality
of, combining topology with node evidence.

### Proposition 2: the primary utility is not adaptively submodular in general

Consider two candidates `a` and `b` with

`P(Z_a=1,Z_b=1)=p` and `P(Z_a=0,Z_b=0)=1-p`, where `0<p<1`.

This distribution is realizable by the restricted cascade model: let the
source-to-`a` edge transmit with probability `p` and let the `a`-to-`b` edge
transmit with probability one.

For unit discovery utility, the expected marginal value of querying `b` before
any observation is `p`. After observing `Z_a=1`, its expected marginal value is
one. Thus

`Delta(b | empty) = p < 1 = Delta(b | Z_a=1)`.

This violates the diminishing-returns inequality required for adaptive
submodularity.

#### Meaning

Confirming an affected gateway can increase the value of querying a likely
descendant. Consequently, the standard adaptive-greedy approximation guarantee
cannot be invoked for the general cascade model.

### Proposition 3: ACIS-Risk v1 is a restricted prior impact heuristic

Let the KDD 2013 graph-active-search score be

`score_i = f_i + alpha f_i sum_j(f'_j-f_j)`.

With `alpha=1`, `f_i=p_i`, and the comparison restricted to the same temporally
later candidates, the scores are identical whenever those probability uplifts
are nonnegative:

`score_i = p_i * (1 + sum_later_j (p'_j-p_j))`.

ACIS-Risk v1 additionally clips each negative uplift to zero. It is therefore
the same probability-times-positive-branch-impact construction with a temporal
restriction and clipping, not a wholly different acquisition principle.

#### Meaning

V1 remains a useful baseline and empirical result. Its acquisition algebra
cannot be the paper's new theoretical method.

## 11. Unresolved theoretical targets

The paper needs at least one result materially stronger than Section 10.
Targets are ordered by scientific value.

### T1. Identifiability threshold

Characterize when the affected set can be recovered better than the
exchangeability bound as a function of:

- retention `q` and insertion `r`;
- cascade depth and branching;
- affected-set size;
- separation between `P_1` and `P_0`; and
- replay budget.

An acceptable theorem must state necessary or sufficient conditions, not only
show monotonic trends in simulation.

### T2. Hybrid-evidence separation

Exhibit a nondegenerate regime in which every graph-only policy loses
information through deleted paths and every content-only policy is confounded
by task-matched distractors, while a joint policy has strictly lower query
complexity or regret.

This is the result most directly aligned with the empirical archive design.

### T3. Tractable structured policy

For a tree or polytree latent cascade, derive either:

- an exact polynomial-time policy for a restricted horizon/model;
- an approximation to the finite-horizon Bayes oracle; or
- a regret bound expressed through topology-posterior error and content
  calibration error.

### T4. Robustness to provenance misspecification

For a policy using an approximate posterior `P_hat(G*,Z | O,H)`, bound utility
regret in terms of a declared discrepancy between `P_hat` and the true model.
A ranking-stability inequality alone is insufficient; the result must account
for adaptive belief updates.

### T5. General-DAG hardness

Determine whether SCACD-UP remains hard under source conditioning and temporal
DAG structure. Existing active-search and value-of-information hardness cannot
simply be relabeled; any theorem must reduce to the exact model and utility in
this document.

## 12. Candidate successor policy: design contract, not final method

No ACIS-Risk v2 is defined or claimed in this specification. A candidate must
operate on a posterior or robust belief over latent graphs rather than use
`G~` as ground truth.

A minimal topology-uncertainty-aware prototype will:

1. maintain particles or structured marginals for plausible `G*` and cascade
   states `Z`;
2. update both graph and label beliefs after each replay;
3. score both possible replay outcomes, not only the positive branch;
4. optimize a fixed finite horizon or a theoretically justified surrogate;
5. reduce to a clearly stated special case when `q=1` and `r=0`; and
6. expose its computational approximation error.

For horizon `h`, the exact target is the recursion in Section 9 truncated to
`h`, with a declared terminal value approximation when `h<B`. Merely
marginalizing the old probability-times-impact score over graph particles is
not automatically novel. The successor must either obtain a new guarantee,
resolve a proved v1 failure, or exploit structure to approximate the two-branch
Bayes value in a way not equivalent to the 2013 heuristic.

## 13. Smallest required falsification instance

Before developing the successor, construct the smallest archive satisfying all
of the following:

1. one known invalid source;
2. at least two plausible latent provenance graphs compatible with the same
   observed graph;
3. a missing gateway edge or a spurious distractor edge;
4. content evidence that is informative but imperfect;
5. a budget small enough that the first replay matters;
6. ACIS-Risk v1 chooses a strictly suboptimal first replay; and
7. the Bayes oracle chooses another replay with strictly greater expected
   discovery utility.

The instance must be specified analytically and verified by exhaustive
enumeration. If no such small instance can be found under a reasonable model,
the motivation for a new policy weakens substantially.

## 14. Evaluation contract implied by the theory

Theory-facing experiments must vary the quantities that appear in the model:

- `q`: true-edge retention;
- `r`: false-edge insertion;
- cascade depth and branching;
- feature separation between affected memories and task-matched clean
  distractors;
- graph-model misspecification;
- affected prevalence;
- budget and nonuniform replay cost; and
- archive size.

Required comparisons are:

1. random and chronological replay;
2. content-only and observed-provenance-only selection;
3. ACIS variants, with ACIS-Risk v1 frozen;
4. graph active-search impact;
5. a nonmyopic active-search method such as ENS where its model is applicable;
6. the exact Bayes oracle on small instances;
7. the successor policy; and
8. complete replay as the recall ceiling.

MemoRepair addresses repair selection after affected descendants are known
under its provenance contract. It is a downstream repair comparator, not a
substitute for discovery under uncertain provenance.

All method choices, priors, uncertainty sets, horizons, and approximation
budgets must be frozen before the larger held-out archive suite is generated.
The current 30 archives remain development data.

## 15. Success and failure criteria

### Theory phase succeeds if

- the formal model yields a defensible identifiability, separation, query, or
  adaptive-regret result;
- a small proved failure of v1 exists;
- a tractable policy follows from the model rather than a parameter sweep;
- the policy approaches the exact oracle in the regime covered by theory; and
- empirical advantages occur in the regimes predicted by the theorem.

### Theory phase fails or requires repositioning if

- the formulation reduces completely to an existing active-search model with
  renamed variables;
- the only result is `q^d` path visibility or a one-line score perturbation
  bound;
- the successor is only the v1 score with another fitted feature;
- gains occur only on the 30 development archives or only after tuning on
  final data; or
- discovery gains do not translate into validated repair or downstream
  behavioral benefit.

If these failure conditions hold, the honest publication route is a benchmark
or agent-memory systems paper rather than a new learning-theory method paper.

## 16. Immediate work products

The next theory milestone consists of four artifacts:

1. an executable exact Bayes oracle for 8--12 candidates;
2. a machine-checkable version of the exchangeability and
   non-adaptive-submodularity examples;
3. the smallest analytically specified uncertain-provenance failure case for
   ACIS-Risk v1; and
4. a theorem notebook exploring T1 and T2 first on rooted trees.

No successor method should be named or evaluated at scale until these four
artifacts clarify what the method must solve.

## 17. Primary theoretical references

- Garnett et al., *Bayesian Optimal Active Search and Surveying*, ICML 2012:
  <https://arxiv.org/abs/1206.6406>
- Wang, Garnett, and Schneider, *Active Search on Graphs*, KDD 2013:
  <https://www.cs.cmu.edu/~schneide/kdd-wang2013.pdf>
- Jiang et al., *Efficient Nonmyopic Active Search*, ICML 2017:
  <https://proceedings.mlr.press/v70/jiang17d.html>
- Jiang et al., *Cost Effective Active Search*, NeurIPS 2019:
  <https://proceedings.neurips.cc/paper_files/paper/2019/hash/df0e09d6f25a15a815563df9827f48fa-Abstract.html>
- Golovin and Krause, *Adaptive Submodularity*, JAIR 2011:
  <https://arxiv.org/abs/1003.3967>
- Krause and Guestrin, *Optimal Value of Information in Graphical Models*:
  <https://arxiv.org/abs/1401.3474>
- Bressan et al., *Active Learning on Adversarially Corrupted Graphs*, COLT
  2026: <https://proceedings.mlr.press/v336/bressan26b.html>
- MemoRepair, 2026: <https://arxiv.org/abs/2605.07242>
