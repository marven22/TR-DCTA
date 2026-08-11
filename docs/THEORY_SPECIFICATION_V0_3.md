# Theory Specification v0.3: Budgeted Causal Memory Auditing

## 1. Status and claim discipline

This specification is the theory-facing description of the already-frozen
SC-DCTA method. It does not modify the method, refit its posterior, or authorize
additional Meta-World tuning. The completed Meta-World experiments are evidence
for the frozen method; they are not data from which the following theorem
statements may be altered.

The specification separates three categories:

- **proved identities and propositions**, for which a proof is supplied here;
- **standard foundations**, which justify implementation correctness but are
  not claimed as original mathematical ideas; and
- **open headline targets**, which must be proved before being presented as a
  theoretical contribution.

SC-DCTA is not claimed to be Bayes optimal. Its acquisition rule is a scalable
positive-branch surrogate. ENS evaluates both replay outcomes more fully and
outperformed SC-DCTA in the largest Meta-World archive stress condition.

## 2. Research question

An agent stores memories created over time. One of several earlier memories may
be the origin of a harmful error. Some later memories may have inherited that
error, but recorded provenance is incomplete, semantic resemblance is
imperfect, and replaying every memory is costly.

The theoretical question is:

> Given uncertain corruption origin, partially observed formation provenance,
> correlated downstream corruption, observable content/context evidence, and a
> finite replay budget, how much source-caused harmful memory can an adaptive
> auditor discover and quarantine?

The target is not arbitrary poor-quality memory. A candidate is positive only
when it is causally affected by the latent origin under the declared
counterfactual correction contract.

## 3. Formal objects

Let memories be temporally ordered. Candidate origins and replayable descendants
are separated because the frozen experiments treat candidate sources as
forensic origins rather than spending the descendant replay budget on them.

| Symbol | Meaning |
|---|---|
| `S in S_set` | Latent corrupted origin |
| `V` | Replayable descendant memories |
| `G*` | Latent temporal influence DAG |
| `G_tilde` | Observed, incomplete formation DAG |
| `X` | Observable memory content and formation context |
| `Z_i in {0,1}` | Memory `i` is causally affected by `S` |
| `Y_i` | Outcome of replaying memory `i` |
| `w_i >= 0` | Harm/remediation value of finding `i` affected |
| `B` | Replay budget under unit costs |
| `H_t` | Replay/outcome history through step `t` |
| `P_t` | Posterior `P(S,G*,Z | G_tilde,X,H_t)` |
| `Q_pi(B)` | Memories replayed by adaptive policy `pi` |

The primary theoretical utility is weighted replay-confirmed discovery:

`U_B(pi) = E[sum_{i in Q_pi(B)} w_i Z_i]`.

This matches the numerator of empirical weighted harmful-memory recall. The
random recall denominator is retained as an empirical metric but is not needed
for the principal expectation-based theorems.

Behavioral recovery is a downstream utility and remains distinct from
localization. The theory does not equate finding a harmful memory with repairing
every possible future failure.

## 4. Assumptions and empirical scope

### A1. Temporal causal consistency

Every influence edge points from an earlier to a later memory. `Z_i=1` means
that correcting origin `S` before formation would change memory `i` in a
preregistered task-relevant way.

### A2. Ideal replay feedback in the primary model

`Y_i=Z_i`. Noisy or abstaining replay is an extension. The current deterministic
Meta-World outcome ledgers implement the ideal-feedback abstraction.

### A3. Source-caused target

Source-independent defects receive `Z_i=0` for this audit. The task is lineage
localization, not generic anomaly detection.

### A4. Nonnegative bounded value

`0 <= w_i <= w_max`. Only replay-confirmed candidates are quarantined in the
primary theory.

### A5. Posterior-calibration boundary

Results stated under the true posterior require correct model specification.
Approximation results compare a particle posterior with a declared target
posterior. They do not establish that the fitted target model equals reality.

### A6. Proposal coverage

If the target source prior is `p(s)` and particles are sampled from `q(s)`, then
`q(s)>0` whenever `p(s)>0`.

### A7. Provenance boundary

The completed Meta-World robustness study masks true formation edges. It does
not establish robustness to arbitrary false-edge insertion. A general
observation channel may later include false edges, but such a theorem must not
be described as empirically validated by the present benchmark.

## 5. Frozen SC-DCTA posterior and acquisition

The fitted model defines a target source prior `p(s)` and a conditional cascade
distribution over latent edge, contamination, and harmful-effect states. To
ensure finite-particle coverage, SC-DCTA samples origins from

`q(s) = lambda + (1 - |S_set| lambda) p(s)`

with `lambda=0.05` in the frozen three-source experiment. A particle whose
origin is `s` receives importance weight `p(s)/q(s)`. Conditional simulation is
otherwise unchanged.

At history `H_t`, write

- `p_i = P_t(Z_i=1)`;
- `p_j^(i+) = P_t(Z_j=1 | Z_i=1)`.

For remaining candidate set `R_t`, the frozen acquisition score is

`A_i(P_t) = p_i [w_i + sum_{j in R_t minus {i}} w_j (p_j^(i+) - p_j)_+]`,

where `[x]_+ = max(0,x)`. SC-DCTA chooses the largest score, replays that
memory, conditions the full posterior on the observed outcome, and repeats.

The acquisition rule itself is the established probability-times-positive-
impact construction used in graph active search. The new theory must not claim
that this algebra alone is novel.

## 6. Proposition 1: exact positive-covariance representation

For every finite posterior `P_t`, nonnegative harm weights, and candidate `i`,

`A_i(P_t) = w_i p_i + sum_{j != i} w_j [Cov_t(Z_i,Z_j)]_+`.

### Proof

If `p_i>0`,

`p_i (p_j^(i+) - p_j)`

`= p_i [P(Z_i=1,Z_j=1)/p_i - p_j]`

`= P(Z_i=1,Z_j=1) - p_i p_j`

`= Cov(Z_i,Z_j)`.

Because multiplication by nonnegative `p_i` commutes with the positive-part
operator, the equality holds term by term. If `p_i=0`, both the implemented
score and every covariance involving `Z_i` are zero. Substitution proves the
claim.

### Meaning

SC-DCTA rewards two quantities:

1. immediate expected harm found by replaying `i`; and
2. positive dependence between `i` and the remaining harmful lineage.

It is not simply a marginal-risk ranker. However, the acquisition score omits
explicit value assigned to the negative replay branch. Full posterior
conditioning still uses a negative observation after it occurs.

### Verification

`src/mcx/sc_dcta_theory.py` independently implements both score forms.
`tests/test_sc_dcta_theory.py` verifies equality and identical replay selection
on finite latent-source posteriors.

## 7. Proposition 2: support-correction identity and consistency

Let a latent particle be `Omega=(S,C)`, where `C` contains all conditional
graph/cascade draws. Let the target distribution be

`P(Omega)=p(S) P(C|S)`

and proposal distribution be

`Q(Omega)=q(S) P(C|S)`.

Under A6, define `W(Omega)=p(S)/q(S)`. For every bounded function `f`,

`E_Q[W f] = E_P[f]` and `E_Q[W]=1`.

Consequently, the self-normalized estimate

`sum_k W_k f(Omega_k) / sum_k W_k`

converges almost surely to `E_P[f]` as the number of iid proposal particles
goes to infinity.

### Proof

Expanding the finite source sum and conditional expectation,

`E_Q[W f]`

`= sum_s q(s) E[f(s,C)|s] p(s)/q(s)`

`= sum_s p(s) E[f(s,C)|s]`

`= E_P[f]`.

Setting `f=1` gives `E_Q[W]=1`. The strong law applied to numerator and
denominator, followed by the continuous-mapping theorem, gives consistency of
their ratio.

### Claim boundary

This is a standard importance-sampling result specialized to the SC-DCTA
source proposal. It validates the implementation but is not the paper's
headline mathematical novelty. The finite self-normalized estimator is
generally not exactly unbiased; consistency, not finite-sample unbiasedness, is
claimed.

Without weighting, proposal samples converge to expectations under `Q`, which
contains the artificial source floor, rather than the calibrated target `P`.

## 8. Proposition 3: posterior-to-score stability

Let `P` and `P_hat` be two distributions over the same binary affected vector,
and let their total-variation distance be at most `delta`. Define total
remaining harm weight `W_R=sum_{j in R} w_j`. Then, for every candidate `i`,

`|A_i(P_hat)-A_i(P)| <= 3 W_R delta`.

If the best exact score is unique and its margin over the second-best score is

`Delta > 6 W_R delta`,

then `P_hat` and `P` select the same replay.

### Proof

Total variation bounds the error of every event probability by `delta`, so
each marginal and pairwise joint probability differs by at most `delta`.
Furthermore,

`|p_i p_j - p_hat_i p_hat_j| <= |p_i-p_hat_i| + |p_j-p_hat_j| <= 2 delta`.

Therefore each covariance differs by at most `3 delta`. The positive-part map
is one-Lipschitz. The immediate-risk term differs by at most `w_i delta`, and
the remaining covariance terms by at most
`3 delta sum_{j != i}w_j`; their sum is at most `3 W_R delta`.

If every score moves by at most that radius, the best-versus-runner-up ordering
cannot reverse when its exact margin exceeds twice the radius.

### Meaning and limitation

This is a deterministic certificate conditional on posterior total-variation
error. The next two corollaries translate particle count into simultaneous
moment, score, and trajectory bounds under bounded importance ratios and an
explicit minimum probability for conditioned replay histories.

## 8.1 Corollary: finite-particle concentration at a fixed replay history

Let `Omega_1,...,Omega_N` be iid particles from proposal `Q`, with importance
weights `rho(Omega)=dP/dQ` satisfying `0 <= rho <= R`. Fix a replay history `h`
whose event has target probability `pi_h=P(h)>0`. Let `n_h` candidates remain,
and define

`M_h = n_h(n_h+1)/2`,

the number of marginal and unordered pairwise probabilities used by every
SC-DCTA score at that history. For failure probability `alpha`, define

`a_h = R sqrt(log(2(M_h+1)/alpha)/(2N))`.

If `a_h < pi_h`, then with probability at least `1-alpha`, all self-normalized
particle estimates of the required conditional marginal and pairwise moments
are simultaneously within

`eta_h = 2 a_h/(pi_h-a_h)`

of their exact target-posterior values. Consequently, for every remaining
candidate,

`|A_hat_i(h)-A_i(h)| <= 3 W_h eta_h`,

where `W_h` is total remaining harm weight. If the exact best-versus-second
best score margin satisfies

`Delta_h > 6 W_h eta_h`,

the finite-particle and infinite-particle SC-DCTA policies select the same
replay at history `h`.

### Proof

For each required conditional event `E`, its particle numerator is the sample
average of `rho 1{h and E}` and its denominator is the sample average of
`rho 1{h}`. Each random variable lies in `[0,R]`. Hoeffding's inequality gives

`P(|mean - expectation| > a) <= 2 exp(-2Na^2/R^2)`.

There are `M_h` moment numerators and one history denominator. A union bound
with the stated `a_h` makes their simultaneous failure probability at most
`alpha`.

Write the exact numerator as `x`, denominator as `d=pi_h`, and their estimates
as `x_hat,d_hat`. Since `0<=x/d<=1`, on the concentration event,

`|x_hat/d_hat - x/d|`

`<= (|x_hat-x| + (x/d)|d_hat-d|)/(d-a_h)`

`<= 2a_h/(pi_h-a_h)`.

Proposition 3 then supplies the score bound and margin certificate.

### Frozen proposal ratio

For `K` candidate sources and the affine support proposal

`q(s)=lambda+(1-K lambda)p(s)`,

the importance ratio is bounded by

`R <= 1/[1-(K-1)lambda]`.

To see this, `p/[lambda+(1-K lambda)p]` is increasing in `p` and reaches its
maximum at `p=1`. With the frozen `K=3` and `lambda=0.05`,

`R <= 1/0.90 = 10/9`.

This bound applies to the full latent particle because the proposal changes
only the source marginal; conditional edge, cascade, and effect draws are the
same under target and proposal.

### Numerical scale, not a certificate of observed decisions

At the initial history (`pi_h=1`), 2,048 particles, 95% confidence, and
`R=10/9`, the simultaneous worst-case moment-error bounds are approximately
0.111, 0.121, 0.129, and 0.137 for 21, 50, 100, and 200 candidates. These are
distribution-free bounds over every marginal and pairwise moment. They are
conservative and, without observed exact score margins, do not certify that a
particular Meta-World replay choice was unchanged.

## 8.2 Corollary: finite-budget trajectory agreement

Let `H_B` be the set of positive-probability decision histories reachable in
the exact infinite-particle SC-DCTA policy tree before each of `B` binary
replays. Then

`L=|H_B| <= 2^B-1`.

Let `n` be the initial candidate count,
`M=n(n+1)/2`, and suppose every history in `H_B` has target probability at
least `gamma>0`. Define

`a = R sqrt(log(2L(M+1)/alpha)/(2N))`

and, when `a<gamma`,

`eta = 2a/(gamma-a)`.

If at every reachable exact-policy history `h`,

`Delta_h > 6 W_h eta`,

then, with probability at least `1-alpha`, finite-particle SC-DCTA chooses the
same action as infinite-particle SC-DCTA at every step through budget `B`.

### Proof

Apply the fixed-history argument simultaneously to the history denominator and
all marginal/pairwise numerators for every history in `H_B`. There are at most
`L(M+1)` bounded averages, yielding the stated union bound. On this event, the
margin condition forces agreement at the root. After either replay outcome,
the corresponding child history is also covered, so agreement follows at the
next step. Induction over the `B` levels proves trajectory agreement.

### Scope and limitation

This is a high-probability guarantee relative to **infinite-particle SC-DCTA**,
not Bayes-optimal planning or ENS. The condition exposes a real limitation:
conditioning on a rare replay history makes self-normalized estimates unstable
unless particle count grows accordingly. A guarantee based only on the
realized empirical effective sample size would require additional assumptions;
ESS is retained as a diagnostic rather than substituted for the rigorous
bounded-ratio/history-mass conditions.

## 9. Proposition 4: directional screening, amplification, and failure of
adaptive submodularity

Consider the chain `S -> A -> B`, with `P(Z_A=1)=p`,
`P(Z_B=1|Z_A=1)=theta`, and no spontaneous downstream corruption. Then

`P(Z_B=1)=p theta`,

`P(Z_B=1|Z_A=1)=theta`, and

`P(Z_B=1|Z_A=0)=0`.

A negative audit of `A` screens `B` out; a positive audit amplifies belief in
`B` from `p theta` to `theta`. For `0<p<1` and `theta>0`, observing a positive
parent increases the marginal value of auditing its child. Thus the general
utility is not adaptively submodular and a standard adaptive-greedy guarantee
cannot be invoked.

This proposition was established in theory v0.2 and remains part of v0.3.

## 10. Proposition 5: localization-to-recovery bridge

Let `L` denote successful localization and quarantine of the exposed harmful
memory. Let `F` denote availability of a clean fallback that succeeds after
quarantine. Suppose recovery occurs whenever `L` and `F` occur, and

`P(F=0 | L) <= delta_F`.

Then

`P(recovery) >= P(L)(1-delta_F)`.

### Proof

`P(recovery) >= P(L and F) = P(L)P(F|L) >= P(L)(1-delta_F)`.

### Meaning

This does not guarantee that localization always produces recovery. It states
the exact interface between the auditing and remediation components. The
frozen Meta-World result that recovery conditional on localization remains
approximately 97--99% indicates a small benchmark-specific `delta_F` and makes
localization the observed bottleneck.

## 11. Foundation: no-evidence exchangeability bound

If `n` replay candidates contain exactly `k` positives uniformly distributed
over all size-`k` subsets, and neither provenance nor features breaks
exchangeability, every adaptive policy making `B` distinct unit-cost queries
has expected discoveries `Bk/n`.

This proposition from theory v0.1 is retained as an impossibility baseline. It
is not sufficient novelty: it simply proves that useful auditing requires an
observable source of asymmetry.

## 12. Theorem 6: transverse joint-evidence separation

For integers `r>=2`, `1<=B<=r`, and `L>=B`, there exists a temporal causal
memory-archive family with `r^2` possible origins and `L` replayable descendants
per origin such that:

1. a policy observing provenance and content jointly obtains expected utility
   `B`;
2. every provenance-only policy and every content-only policy obtains expected
   utility at most

   `B(B+1)/(2r)`;

3. a single-view policy's probability of replay-confirming even one affected
   memory within `b<=r` replays is at most `b/r`; and
4. a policy that collapses uniform source uncertainty to one origin before
   replay and cannot restore excluded support obtains expected utility `B/r^2`.

Thus, for fixed `B`, the joint-to-single-view expected-utility ratio is

`2r/(B+1)`,

which grows linearly with the residual single-view ambiguity `r`.

### Construction

Let the latent origin be the uniformly distributed pair

`S=(U,V) in {1,...,r} x {1,...,r}`.

Origin `s_uv` has a branch `D_uv` containing `L` later memories. If
`S=(u,v)`, deterministic causal propagation makes every memory in `D_uv`
affected and every memory outside `D_uv` clean. All replay costs and harm
weights equal one.

The provenance observation identifies `U` but not `V`. This models missing
formation information that leaves `r` source-compatible branches in the same
provenance class. The content/context observation identifies `V` but not `U`.
This models task-matched memories for which `r` branches occupy the same
semantic class. The two induced partitions are transverse: a provenance row
and content column intersect at the single origin `(U,V)`.

The joint policy and both restricted policies receive identical binary replay
feedback. Their only difference is whether they observe both initial evidence
views or one.

### Proof of the joint value

The joint observations reveal the singleton intersection `(U,V)`. Because
`L>=B`, the policy replays `B` distinct memories from `D_UV`; all are affected.
No policy can discover more than one affected memory per replay, so utility
`B` is optimal.

### Proof of the single-view upper bound

Conditioned on either one view, exactly `r` branches remain exchangeable and
one is uniformly positive. Before the first positive replay, testing a second
memory in a branch that already returned negative has zero value, while testing
a new branch has positive value. After the first positive, the all-or-none
cascade structure identifies the branch and every remaining replay can obtain
one discovery. Hence an optimal policy tests distinct branches until the first
positive and then exploits that branch.

Let `T` be the positive branch's position in this search order. Symmetry makes
`T` uniform on `{1,...,r}`. If `T=t<=B`, the policy obtains `B-t+1`
discoveries; otherwise it obtains zero. Therefore

`E[U_single]`

`= (1/r) sum_{t=1}^B (B-t+1)`

`= B(B+1)/(2r)`.

Randomization cannot improve the result because it only randomizes an ordering
of exchangeable branches. This proves the bound for all adaptive policies in
either single-view class.

### Localization query consequence

A single-view policy replay-confirms a positive within `b<=r` distinct branch
tests with probability exactly `b/r`. Achieving probability at least
`1-delta` therefore requires at least

`ceil((1-delta)r)`

replays. The joint policy replay-confirms a positive in one replay. This is an
explicit linear query-complexity separation.

### Early hard-source collapse

Under uniform uncertainty over `r^2` origins, a support-collapsing policy picks
the correct origin with probability `1/r^2`. If it is correct, its `B` branch
replays are positive; if it is wrong, its restricted posterior assigns the
true branch zero support and the `B` replays are clean. Its expected utility is
therefore `B/r^2`.

This fourth statement is an algorithmic restriction corresponding to the
hard-source ablation, not an information-theoretic lower bound on every policy
that eventually reports one source. A method that uses both evidence views to
identify the source before collapsing is the joint policy, not this ablation.

## 12.1 Corollary: robustness to imperfect evidence decoders

Suppose a provenance decoder returns the correct row with error probability at
most `epsilon_G`, and a content decoder returns the correct column with error
probability at most `epsilon_X`. The provenance view contains no information
about the column beyond its row output, and the content view contains no
information about the row beyond its column output; decoder errors need not be
independent of one another. The policy that audits the branch at their decoded intersection obtains

`E[U_joint] >= B(1-epsilon_G-epsilon_X)`.

### Proof

By the union bound, both decoders are correct with probability at least
`1-epsilon_G-epsilon_X`. On that event all `B` replays are positive; utility is
nonnegative otherwise.

Even a perfect single view retains the upper bound `B(B+1)/(2r)` because its
unobserved coordinate remains uniform. Therefore the noisy joint policy has a
strict guaranteed advantage whenever

`epsilon_G+epsilon_X < 1-(B+1)/(2r)`.

## 12.2 Corollary: exact-posterior SC-DCTA realizes the separation

In the noiseless construction with unit weights, exact-posterior SC-DCTA
achieves the joint value `B` and the optimal single-view value
`B(B+1)/(2r)`.

### Proof

Under both views, affected-branch memories have marginal probability one and
all other memories have marginal zero, so SC-DCTA selects only the affected
branch.

Under one view, every memory in each of the `r` plausible branches has marginal
`1/r`. Memories within the same branch have positive covariance; memories in
different mutually exclusive branches have negative covariance, which the
frozen score clips to zero. All untested branches therefore tie. A negative
replay removes its branch; a positive replay makes that branch certain and its
remaining memories are selected. This is precisely the optimal search-then-
exploit policy in the proof above.

### Executable verification

`orthogonal_partition_posterior` constructs the finite family in
`src/mcx/sc_dcta_theory.py`. The test suite:

- checks the closed form against an independent Bellman recursion for every
  `1<=B<=r<10`;
- exhaustively averages frozen SC-DCTA over every latent world;
- verifies identical graph-only and content-only bounds;
- verifies the joint value and early-collapse penalty; and
- checks the noisy sufficient condition and localization probability.

This is deterministic verification of the proof witness, not a new empirical
benchmark.

## 12.3 Strength and limitation of the theorem

The theorem resolves the minimal joint-evidence separation target: neither
view alone identifies the causal branch, their intersection does, and the
advantage is stated in audit utility and query complexity. It does not yet
cover partially overlapping cascades, heterogeneous weights, noisy replay, or
general DAGs. Its all-or-none propagation assumption is relaxed by the
stochastic causal-transmission extension below. The theorem must not be
advertised as the first general result that multiple views can be synergistic.

## 12.4 Theorem 7: separation under stochastic causal transmission

Use the same transverse archive family, but replace deterministic branch
propagation as follows. Conditional on true origin `(U,V)`, each of its `L`
descendants is independently affected with probability `theta in (0,1]`.
Every other branch remains clean. This is a causal star in which each
source-to-descendant edge independently transmits corruption with probability
`theta`.

For `1<=B<=r` and `L>=B`:

1. the joint-evidence policy has expected utility

   `U_joint = B theta`;

2. every provenance-only or content-only adaptive policy has expected utility
   at most

   `U_single <= theta B(B+1)/(2r)`;

3. the joint-to-single-view utility ratio is therefore at least

   `2r/(B+1)`; and

4. irreversible early collapse under uniform uncertainty over `r^2` origins
   has expected utility `B theta/r^2`.

### Proof of the joint value

Joint evidence identifies the true branch. The policy replays `B` distinct
memories from that branch. Each is affected independently with probability
`theta`, so linearity of expectation gives `B theta`. No independence across
the *replay rewards* is needed for linearity, although independence is part of
the stated causal construction.

### Branch-revealing oracle for the single-view upper bound

Give the single-view policy strictly more information than replay normally
provides: after its first replay from any branch, an oracle reveals whether
that branch is the true branch, even if the replay returned negative. Any
ordinary single-view policy can be simulated while ignoring this revelation,
so the optimal oracle value upper-bounds every ordinary policy.

Before locating the true branch, the oracle policy tests distinct exchangeable
branches. After locating it, every remaining replay is allocated there. Let
`T` be the true branch's uniform position in the test order. Conditional on
`T=t<=B`, there are `B-t+1` true-branch replays, each with expected reward
`theta`. Thus

`E[U_oracle]`

`= (theta/r) sum_{t=1}^B (B-t+1)`

`= theta B(B+1)/(2r)`.

Because the actual single-view policy has no branch-identity oracle, its value
cannot exceed this quantity. Dividing `B theta` by the upper bound proves the
ratio. The early-collapse result follows because the retained source is
correct with probability `1/r^2`, after which `B` true-branch replays have
expected reward `B theta`.

### Stochastic localization probability

The joint policy replay-confirms at least one affected memory with probability

`P_joint(positive) = 1-(1-theta)^B`.

The branch-revealing single-view oracle has upper bound

`P_single(positive)`

`<= (1/r) sum_{q=1}^B [1-(1-theta)^q]`.

Here `q=B-t+1` is the number of true-branch replays remaining when the true
branch occurs at position `t`. The actual single-view probability is no larger.
For `B<=r`, the joint probability is at least this oracle bound and is strictly
larger except at degenerate boundary cases.

### Imperfect evidence decoders

Under the no-cross-coordinate-leakage condition of Section 12.1, decoder error
rates `epsilon_G` and `epsilon_X` give the stochastic joint lower bound

`E[U_joint,noisy] >= B theta(1-epsilon_G-epsilon_X)`.

The single-view oracle upper bound is unchanged. Consequently, the same
sufficient condition

`epsilon_G+epsilon_X < 1-(B+1)/(2r)`

guarantees a strict expected-utility advantage; `theta` cancels from the
comparison.

## 12.5 Corollary: exact-posterior SC-DCTA on the stochastic family

With joint evidence, exact-posterior SC-DCTA obtains `B theta`. Every true-
branch candidate has marginal `theta`; all other candidates have marginal
zero. Independent transmissions make within-branch covariance zero after the
origin is known, so SC-DCTA selects arbitrary unreplayed true-branch memories
and conditions correctly after either outcome.

With one view, exact-posterior SC-DCTA remains an ordinary single-view adaptive
policy and is therefore bounded by the branch-oracle value in Theorem 7. The
executable finite-state enumeration confirms this for graph-only and content-
only posteriors and verifies that `theta=1` reduces exactly to Theorem 6.

This result relaxes the most immediate all-or-none criticism. It still uses a
star-shaped cascade with conditionally independent transmissions. General
multi-hop DAGs, overlapping sources, and correlated edge transmission remain
outside the theorem rather than hidden assumptions.

## 13. Remaining finite-particle theory target

Sections 8.1--8.2 resolve the distribution-free bounded-ratio concentration
target. The remaining opportunity is a tighter variance-sensitive bound that
is useful when the Hoeffding/history-union certificate is conservative. Any
such result must control source-composition error and conditioning on rare
histories; empirical ESS alone is not automatically a valid replacement.

The comparator remains infinite-particle **SC-DCTA**. No particle bound in this
specification implies regret against Bayes-optimal planning or ENS.

## 14. Code, theory, and evidence correspondence

| Theoretical object | Frozen implementation/evidence | Boundary |
|---|---|---|
| Target source prior `p(s)` | fitted source estimator in `sc_dcta_metaworld_evaluation.json` | calibrated model estimate, not known truth at deployment |
| Proposal `q(s)` | `support_proposal` with floor 0.05 | computational sampling device |
| Importance ratio `p/q` | `sample_importance_posterior` | corrects source marginal only |
| Posterior `P_t` | weighted `LatentSourcePosterior` particles | approximate fitted posterior |
| Score `A_i` | `risk_choice` | positive-branch surrogate, not Bayes oracle |
| Replay feedback | stored deterministic counterfactual outcome | ideal-feedback benchmark abstraction |
| Utility numerator | weighted harmful memories discovered | theory objective |
| Weighted recall | utility divided by realized total harmful weight | empirical metric |
| Behavioral recovery | forced exposure, quarantine, and fallback | downstream validation, not identical to discovery |
| Posterior approximation | 2,048/8,192 particle validation | empirical stability, not a universal theorem |
| Archive scaling | 21 to 200 task-matched memories | frozen post-hoc stress test |
| Transverse separation family | `orthogonal_partition_posterior` and exact Bellman tests | mathematical witness, not benchmark evidence |
| Stochastic separation family | `stochastic_orthogonal_partition_posterior` and exact enumeration | independent star transmission, not a general DAG claim |

## 15. Novelty boundary

The following are foundations, not standalone novelty claims:

- Bayesian active search and its Bellman recursion;
- graph active search's probability-times-impact score;
- importance sampling and self-normalized consistency;
- path-visibility probability under independent edge deletion;
- the exchangeability lower bound; and
- the observation that exact nonmyopic planning is expensive.

The candidate theoretical contribution is their interaction in a causal memory
archive with uncertain origin, incomplete provenance, task-matched semantic
distractors, adaptive replay, and behavioral remediation. Theorems 6--7 supply
explicit deterministic and stochastic query-separation results for this
interaction.

Adjacent primary work prevents a broader novelty claim. Bayesian co-training
jointly models multiple views and includes active sensing of missing views:
<https://www.jmlr.org/papers/v12/yu11a.html>. Kim et al. formalize synergistic
feature interactions across views using interaction information:
<https://proceedings.mlr.press/v235/kim24ag.html>. Graph and hypergraph active
learning already obtain query-complexity benefits from structural side
information, for example:
<https://proceedings.mlr.press/v89/chien19a.html>. Therefore the defensible
novelty is not "multiple views help." It is the specific transverse ambiguity
result for replay-confirmed discovery of a latent-origin causal corruption
branch, together with its realization by SC-DCTA and connection to downstream
memory remediation.

A targeted primary-source search did not identify this exact causal-memory
auditing theorem. That is evidence for a candidate gap, not proof of priority;
the literature audit must continue during paper drafting.

## 16. Theory success and failure criteria

The current theory package has met the following internal gates:

- a joint-evidence separation theorem is proved under explicit signal and
  symmetry conditions;
- it identifies provenance ambiguity `r`, decoder errors, source-collapse,
  and replay budget in the utility/query gap;
- the separation survives stochastic causal transmission with explicit
  probability `theta` even after the single-view policy receives a stronger
  branch-identity oracle;
- a finite-particle corollary connects implementation approximation to replay
  stability; and
- all empirical connections preserve the frozen method and results.

Theorem 7 removes the clearest all-or-none objection to Theorem 6. The package
now supplies a meaningful method-facing theoretical component, but it is not a
broad theory of general causal DAG auditing: the stochastic construction is
still a star with one latent origin. It should support a causal memory-auditing
paper with rigorous foundations rather than be sold as a sweeping new
learning-theory framework.

The theory direction fails if:

- the separation construction gives the joint policy extra information;
- the result reduces to renaming ordinary independent active search;
- only a probability-floor correction is presented as novelty;
- an approximate-posterior bound is misrepresented as Bayes-optimal regret;
  or
- a theorem assumes false-edge robustness not tested by the benchmark while
  the empirical section implies otherwise.

## 17. Ordered proof program

1. Treat Propositions 1--5 as the frozen foundational package and subject them
   to line-by-line proof review.
2. Independently audit the finite-particle concentration and trajectory proof,
   including its rare-history condition.
3. Independently audit Theorems 6--7, particularly the policy-class
   definitions, oracle domination argument, and noisy-view condition.
4. Map theorem parameters to existing frozen experimental factors without
   fitting the theorem to Meta-World outcomes.
5. Complete the adjacent-theory literature audit and freeze theory version
   1.0 without adding another planned theorem family.
6. Obtain an independent mathematical review before paper integration.

No new Meta-World experiment or SC-DCTA modification is part of this proof
program.
