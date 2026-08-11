# Theory Specification v0.2: Directional Causal-Transition Auditing

## Status and scope

This document specifies a restricted theoretical problem for auditing corrupted agent memories. It supersedes the method-level emphasis of `THEORY_SPECIFICATION_V0_1.md`; it does not invalidate the earlier definitions or counterexamples.

The specification was developed using only the 12 v0.4.1 development archives. The six consumed `libero_goal` held-out archives are excluded from method selection. No claim below treats the current directional method as the final proposed method.

## 1. The scientific distinction

A formation edge means that one memory was available when another memory was formed. It does not prove that harmful content actually travelled across that edge.

We therefore distinguish:

- the **formation graph**, which records possible exposure;
- the **functional corruption process**, which determines whether corruption actually propagated;
- the **audit policy**, which chooses memories to inspect under a budget.

This distinction is the proposed theoretical core. Existing provenance masks describe where propagation could have happened. The latent transition process describes where it did happen.

## 2. Problem definition

Let `G = (V, E)` be an observed directed acyclic formation graph. A known source `s` is corrupted. Each memory `v` has observed features `X_v` and a hidden binary state

`Z_v = 1` if memory `v` is functionally affected, and `Z_v = 0` otherwise.

An ideal audit of `v` reveals `Z_v`. Given budget `B`, a policy adaptively selects at most `B` non-source memories and maximizes

`E[sum_{v audited} Z_v]`.

The primary model uses these assumptions:

1. **Complete formation DAG.** The primary experiment observes every formation edge. Missing or incorrect provenance is a later robustness condition.
2. **Known root intervention.** The initially corrupted source is known and `Z_s = 1`.
3. **No spontaneous downstream corruption.** If all parents of `v` are clean, then `Z_v = 0`.
4. **Local Markov transmission.** Conditional on parent states and local observed features, `Z_v` is independent of non-descendant states.
5. **Ideal audits.** An audit reveals the true binary state without error. Noisy audits are outside the primary theory.

Under these assumptions,

`P(Z | G, X) = 1[Z_s = 1] product_{v != s} P(Z_v | Z_pa(v), X_v, X_pa(v))`.

## 3. Transition models

### 3.1 Homogeneous noisy-OR model

For an affected-parent set `A_v = {u in pa(v): Z_u = 1}`, the prototype uses

`P(Z_v = 1 | A_v) = 0`, when `A_v` is empty,

and otherwise

`P(Z_v = 1 | A_v) = 1 - product_{u in A_v}(1 - theta_type(u,v))`.

The implementation estimates separate root, ordinary, and merge transition parameters.

### 3.2 Local transition model

The second prototype estimates

`logit P(Z_v = 1 | A_v != empty) = beta_0 + beta_r R_v + beta_m M_v + beta_s S_v + beta_a(|A_v|-1)`,

where:

- `R_v` indicates an affected root parent;
- `M_v` indicates a merge in the observed formation graph;
- `S_v` is the maximum parent-child content similarity among affected parents;
- `|A_v|-1` represents additional affected-parent exposure.

This is a conditional transmission model, not a direct classifier of corruption.

## 4. Exact posterior and Bayes oracle

For a small graph, enumerate every causally valid hidden assignment `z`, assign it its transition-and-emission probability, and normalize. After audit history `h`, remove inconsistent assignments and renormalize.

The finite-horizon Bayes value is

`V(h, b) = max_{v not audited} [p_v(h)(1 + V(h union {(v,1)}, b-1)) + (1-p_v(h))V(h union {(v,0)}, b-1)]`.

This gives an exact oracle for small graphs. It is exponential in the number of unaudited variables and the audit horizon; it is a diagnostic oracle, not the scalable policy.

## 5. Established propositions

### Proposition 1: formation exposure does not identify functional corruption

For any source-connected affected subset that is closed under at least one affected-parent path from the source, deterministic open/closed edge transitions can produce that subset on the same observed formation graph.

**Consequence.** Reachability, depth, or provenance alone cannot identify which reachable memories are affected. A formation edge is evidence of opportunity, not proof of transmission.

### Proposition 2: directional screening and amplification on a chain

Consider `s -> a -> b`, with `Z_s = 1`, `P(Z_a=1)=p`, and `P(Z_b=1 | Z_a=1)=theta`, while spontaneous corruption is forbidden. Then

`P(Z_b=1)=p theta`,

`P(Z_b=1 | Z_a=1)=theta`, and

`P(Z_b=1 | Z_a=0)=0`.

Thus a positive audit of `a` amplifies belief in `b`, while a negative audit screens `b` off completely. This is the simplest formal account of why directional audit outcomes matter.

### Proposition 3: the objective is not generally adaptively submodular

In the same chain, if `p < 1`, the marginal probability of finding corruption at `b` increases from `p theta` to `theta` after observing `Z_a=1`. Information can therefore increase, rather than only decrease, a future action's marginal value.

**Consequence.** Standard adaptive-greedy approximation guarantees based on adaptive submodularity do not apply to this problem in general.

### Proposition 4: pointwise acquisition regret under calibrated marginals

At any common audit history `h`, suppose every posterior estimate satisfies

`|p_hat_v(h) - p_v(h)| <= epsilon`.

If `v_hat` maximizes `p_hat_v(h)` and `v_star` maximizes `p_v(h)`, then

`p_v_star(h) - p_v_hat(h) <= 2 epsilon`.

Summed along the realized histories of the approximate policy, its gap to a same-history best-marginal comparator is at most `2 B epsilon`.

This is deliberately not a regret bound against the globally Bayes-optimal adaptive policy: different policies generate different histories, and information value is not captured by marginal calibration alone.

### Proposition 5: inference and planning have different complexity

On a rooted tree with binary local transition and emission factors, sum-product message passing computes posterior node marginals in linear time per full pass. Exact finite-budget policy planning can still require an exponential search over audit histories.

**Consequence.** Better probabilistic inference does not by itself solve acquisition. The policy must value how an audit changes later choices.

## 6. Relation to ACIS

ACIS uses a positive audit to move attention toward related memories. It behaves like a strong local approximation to directional posterior updating, without specifying a complete joint cascade distribution.

Directional Causal-Transition Auditing (DCTA) attempts to replace this heuristic with a fitted joint model. Its intended advantages are calibrated counterfactual updates, negative screening, and a well-defined exact small-graph oracle.

The current development experiment does **not** show a performance advantage for DCTA. It therefore remains a theoretical and diagnostic framework, not the paper's frozen method.

## 7. What is proved, measured, and still conjectural

### Proved within the stated model

- exposure does not identify functional influence;
- positive amplification and negative screening on a chain;
- failure of adaptive submodularity;
- the pointwise `2 epsilon` acquisition-regret bound;
- exact finite-state Bellman recursion;
- tractable marginal inference on trees versus potentially exponential planning.

### Measured on development archives

- all 12 ground-truth assignments lie in the support of both fitted directional models;
- root exposure and local similarity receive positive fitted weights;
- merge exposure receives a negative fitted weight in this small development sample;
- neither directional acquisition policy beats ACIS.

### Still conjectural

- that edge- or context-specific transition uncertainty yields a measurable advantage over ACIS;
- that merge and branch interventions expose failure modes hidden by archive-level recall;
- that a scalable policy can approximate the Bayes oracle with a useful guarantee in the relevant graph class.

## 8. Publication gate

Before another held-out experiment, a successor method must satisfy all of the following on development data:

1. arise from the specified latent transition model or a clearly stated relaxation;
2. beat static source scoring and match or beat ACIS under leave-one-archive-out evaluation;
3. exhibit a nontrivial synthetic or exact-oracle regime where its added machinery is necessary;
4. declare its training information, provenance assumptions, and computational cost;
5. freeze its formula and hyperparameters before evaluation on a fresh domain split.

The gate was subsequently met by DCTA-Risk in the frozen exact causal-regime benchmark and robustness audit. `DCTA_DECISIVE_TEST_RESULTS.md` records the method lock. ACIS-Risk remains the strongest comparator on the earlier development archives, while DCTA-Risk-Local v1 is the frozen primary method for the next fresh evaluation.

## 9. Primary theoretical grounding

- Garnett et al., *Bayesian Optimal Active Search* (ICML 2012).
- Wang et al., *Active Search on Graphs* (KDD 2013).
- Golovin and Krause, *Adaptive Submodularity* (JAIR 2011).
- Jiang et al., *Efficient Nonmyopic Active Search* (ICML 2017).
- Krause and Guestrin, *Optimal Value of Information in Graphical Models* (JAIR 2009).
