# LANTERN explained from first principles

This chapter explains the complete idea behind LANTERN without assuming prior
knowledge of agent memory,
Bayesian inference, provenance graphs, or active search. It begins with an
ordinary example, develops the mathematical version, and then connects every
piece to the implementation and experiments.

## 1. The idea in one sentence

An agent has more stored memories than we can afford to check. Some may have
been corrupted and may have caused later memories to become harmful. TR-DCTA
chooses which memories to physically replay by asking:

> **After all of my limited checks are used, which check sequence is most
> likely to leave the agent able to act safely?**

That last phrase is the defining difference. TR-DCTA does not merely try to
find the largest number of harmful memories. It plans backward from the final
recovery decision.

## 2. What “memory” means here

A memory is a persistent record that an agent may retrieve when handling a
future task. It can contain a lesson, strategy, workflow, expected outcome,
policy reference, or summary of a past trajectory.

Imagine a household robot that previously tried to open a locked cabinet. It
might store:

> “When the cabinet is locked, first pick up the key, unlock the door, and then
> retrieve the object.”

Later, the robot retrieves that record instead of solving the task from
scratch. This is useful because past experience becomes reusable knowledge.

Now suppose a bad feedback event tells the robot that an incorrect trajectory
was successful. The robot might instead store:

> “The lock can be bypassed; reach directly for the object.”

That record is the **corrupt source memory**. Future reflections, summaries, or
workflows may be derived from it:

> “For enclosed-object tasks, skip access-preparation steps.”

Those later records are **descendant memories**. They can remain harmful even
if the original bad record is deleted. This persistence is the problem we
study.

Memories in our experiments come from executed or constructed agent
trajectories, feedback, and subsequent memory-writing or archive-update steps.
The archive also contains unrelated valid memories, so the auditor cannot
simply delete everything.

## 3. The archive

An **archive** is one complete memory-auditing instance. It contains:

- candidate memories that could be replayed;
- one or more possible corrupt origins;
- timestamps or formation order;
- observed provenance links, such as “memory B used memory A when it was
  formed”;
- possible but unobserved links when provenance is incomplete;
- memory text and task context;
- a physical replay budget; and
- a downstream task whose success depends on which memories remain usable.

One archive is analogous to one patient case or one robot situation, not one
image in a vision dataset. It includes a connected system of memories and a
decision problem.

We use three related labels:

- **Contaminated:** information from the corrupt source reached this memory.
- **Affected or harmful:** the contamination changed behavior in a way that can
  cause task failure.
- **Clean:** the memory is not behaviorally harmful in the evaluated task.

A memory can be contaminated without being behaviorally harmful. TR-DCTA's
terminal goal concerns the harmful set.

## 4. Provenance and missing provenance

Provenance is the recorded formation history of memories. A link

```text
A -> B
```

means that memory A influenced the formation of memory B. A chain

```text
bad source -> B -> C
```

provides evidence that B and C may carry forward the original error.

Real systems do not always record every dependency. A missing link does **not**
mean that influence was absent; it means the auditor cannot observe that link.
Our experiments deliberately hide a prescribed fraction of provenance links.
The method must reason over several possible completed causal graphs rather
than treating the visible graph as perfect truth.

## 5. What a replay is

A replay is an expensive physical or executable check of one memory. The system
runs the policy, workflow, or action associated with that memory in the relevant
environment and observes a binary label:

```text
1 = this memory is harmful for the evaluated behavior
0 = this memory is not harmful for the evaluated behavior
```

In MetaWorld, for example, the replay can execute the corresponding robot
policy in simulation. In BabyAI, it executes the memory-conditioned action
logic in the grid environment.

Replaying is different from reading text. A harmful memory can sound plausible,
and a strange-looking memory can still execute correctly. Replay provides the
behavioral evidence used to update the belief.

The final experiments assume **ideal binary replay feedback**: the observed
label is correct. Handling noisy or delayed replay labels is outside the current
guarantee.

## 6. Why the budget matters

If an archive has 50 memories and we can replay all 50, the search problem is
mostly gone. In deployment, replay can require simulator time, robot time,
human review, or costly model execution. We therefore impose a budget such as
four replays.

The method must decide:

1. which memory to replay first;
2. how the result changes its belief;
3. which memory to replay next; and
4. what to quarantine after the budget is exhausted.

This is an **adaptive** problem: the best second replay can depend on whether
the first replay was positive or negative.

## 7. Uncertainty is represented as possible worlds

The auditor does not know the corrupt source, the missing provenance links, or
the complete harmful set. It represents uncertainty using a finite posterior
over possible worlds.

A world is a pair

```text
(possible corrupt source, possible set of harmful memories)
```

with a probability weight. For example:

| Possible world | Harmful memories | Probability |
|---|---|---:|
| W1 | A, B | 0.45 |
| W2 | A, C | 0.45 |
| W3 | D, E | 0.10 |

The marginal probability that A is harmful is therefore 0.90. The marginal for
B is 0.45, and so on.

### Where the initial probabilities come from

The posterior builder uses only information available to the auditor:

- semantic relationship between memory text and the target task;
- semantic relationship between possible sources and descendants;
- observed formation links;
- possible missing links;
- formation order and relative depth;
- branch/reach information;
- number and identity of active parents; and
- cited-memory information when available.

The source estimator uses six observable features: source-to-target similarity,
direct-child-to-target similarity, reachable-descendant-to-target similarity,
source-to-descendant similarity, local graph coherence, and normalized
reachable-set size.

Separate fitted models estimate whether corruption transmits through an active
parent and whether transmitted contamination becomes behaviorally harmful.
These models are fit on permitted development data—not on the hidden labels of
the archive being audited.

### Finite particles

Large archives have too many possible worlds to enumerate exactly. We sample
2,048 worlds, or **particles**, in the final MetaWorld study. Each particle
samples a possible source, missing edges, transmission events, and harmful
emissions.

Rare source hypotheses still need sampling support. We therefore sample from a
support-safe proposal distribution and correct each particle by

```text
target source probability / proposal source probability.
```

This is importance sampling. It prevents a sampling floor from silently
changing the source belief we intend to represent.

## 8. How a replay updates the posterior

Within each possible world, a candidate is either harmful or not. If memory B
is replayed and the result is positive, every world in which B is clean is
discarded. The remaining worlds are renormalized. If the replay is negative,
worlds in which B is harmful are discarded instead.

Formally, if `P` is the current belief and `Y_i` is the binary label for memory
`i`, then the new belief is

```text
P(world | Y_i = y) proportional to
    P(world) × 1{world predicts Y_i = y}.
```

Crucially, the algorithm never reads the label of an unreplayed memory. Private
labels are used only by the evaluator after a method has made its decisions.

## 9. What earlier DCTA does

Probabilistic DCTA is the base policy. At each step it chooses the remaining
memory with the largest current posterior expected harm:

```text
risk(i) = P(i is harmful | current evidence) × harm_weight(i).
```

It observes the replay label, updates the posterior, and repeats.

In the MetaWorld implementation, the harm weight is

```text
w_i = 1
      + 0.25 × normalized_recency(i)
      + 0.25 × normalized_observed_reach(i).
```

Thus every candidate begins with weight 1, while newer memories and memories
with more observable descendants receive modestly larger importance.

This policy is sensible when the objective is to discover weighted harmful
memories. But discovery is an intermediate objective. A replay can find a
harmful memory without resolving which final quarantine permits recovery, and a
negative replay can be extremely valuable even though it discovers no harm.

## 10. Why greedy discovery can choose the wrong replay

Return to the three-world example:

| World | Harmful set | Probability |
|---|---|---:|
| W1 | A, B | 0.45 |
| W2 | A, C | 0.45 |
| W3 | D, E | 0.10 |

Assume one replay remains and the final quarantine can hold two memories.

Greedy DCTA chooses A because A has the highest harmful probability, 0.90.

- If A is positive, we still cannot distinguish W1 from W2. We can quarantine
  A with B or A with C, but not both. One of the two equally likely worlds is
  recovered.
- If A is negative, we identify W3 and quarantine D and E.
- Total expected recovery is `0.45 + 0.10 = 0.55`.

TR-DCTA instead evaluates B even though B's harmful probability is only 0.45.

- If B is positive, W1 is identified and quarantine `{A,B}` recovers it.
- If B is negative, W1 is eliminated. Between W2 and W3, quarantine `{A,C}`
  recovers the much more likely W2.
- Total expected recovery is `0.45 + 0.45 = 0.90`.

B is less likely to be harmful, but it is much more useful for the final
decision. This is the heart of TR-DCTA.

## 11. The terminal recovery objective

Let:

- `V` be the candidate memories;
- `A` be the unknown harmful set;
- `P_t` be the posterior after replay history `t`;
- `C` be quarantine capacity; and
- `Q` be a candidate quarantine set of size `C`.

For the capacity-limited BabyAI setting, define full recovery as

```text
u_rec(Q,A) = 1 if A is a subset of Q, otherwise 0.
```

The secondary utility is captured harmful weight:

```text
u_harm(Q,A) = sum over i in Q of w_i × 1{i in A}.
```

The final quarantine is chosen **lexicographically**:

1. maximize posterior probability of complete recovery;
2. among recovery ties, maximize expected captured harmful weight; and
3. use a deterministic identifier ordering for any remaining tie.

Lexicographic ordering avoids inventing an arbitrary coefficient that trades
one unit of recovery against some quantity of captured harm.

## 12. How TR-DCTA chooses the next replay

Suppose candidate `i` is considered next. It can produce a positive or negative
label. TR-DCTA considers both:

```text
Value(i) = P(Y_i=1) × future_value(after i is positive)
         + P(Y_i=0) × future_value(after i is negative).
```

It does not stop after one hypothetical step. It evaluates the complete
remaining replay budget. To make this tractable, hypothetical future actions
follow base probabilistic DCTA. This is a standard rollout construction.

At the real next step, TR-DCTA chooses the candidate with the best expected
terminal value. It then observes the actual label, updates the posterior, and
**replans**. Thus its real future actions are not permanently committed to the
base-policy simulation.

Simplified pseudocode is:

```text
belief = initial posterior
remaining = all replay candidates

repeat until replay budget is exhausted:
    for each candidate i in remaining:
        evaluate positive and negative outcomes for i
        simulate base DCTA through the rest of the budget
        evaluate the resulting terminal recovery decision
        average the two branches by their posterior probabilities
    replay the candidate with the best expected terminal value
    observe its real binary label
    condition the posterior on that label
    remove the candidate from the remaining set

make the final quarantine/recovery decision
```

Caching reuses identical posterior states reached in the hypothetical tree.

## 13. BabyAI and MetaWorld use different terminal actions

TR-DCTA is a decision principle, not a single hard-coded quarantine rule.

### BabyAI

BabyAI uses a quarantine capacity of three. After the replay budget, every
method receives the same capacity-limited terminal optimizer described above.
Recovery means that the final quarantine contains the realized harmful set.

TR-DCTA differs from comparison methods only in replay acquisition. It does not
receive extra quarantine capacity or hidden labels.

### MetaWorld

The pre-existing MetaWorld recovery contract is different. Only memories that
were physically replayed and confirmed harmful may be quarantined. After those
memories are removed, the robot executes the first surviving memory in the
frozen semantic retrieval order.

MetaWorld TR-DCTA therefore evaluates two lexicographic quantities:

1. expected robot recovery after confirmed-positive quarantine; and
2. expected fraction of harmful retrieval anchors quarantined, as a tie-break.

For evaluation, each harmful memory is forced to rank first once. This creates
a **forced-exposure episode**: if that harmful memory is retrieved, does the
audit remove it and leave a safe fallback policy?

This adapter preserves the terminal-recovery idea while respecting the domain's
actual remediation mechanism. Importing BabyAI's capacity-three rule into
MetaWorld would be an invalid change of experimental contract.

## 14. What TR-DCTA outputs

For each archive, the method returns:

- the ordered list of replayed memory IDs;
- the posterior after all observed labels;
- the final quarantine decision or confirmed-positive set; and
- predicted terminal recovery quantities used during planning.

The evaluator separately computes:

- harmful memories discovered by replay;
- weighted discovery recall;
- harmful anchors quarantined;
- robot recovery success;
- whether the fallback remains harmful; and
- paired task-level comparisons with baselines.

## 15. What information the method is allowed to know

TR-DCTA knows:

- public memory contents and task descriptions;
- observed provenance;
- candidate missing-edge structure when specified by the archive model;
- timestamps and public metadata;
- fitted source/cascade parameters from permitted development data;
- the replay budget and terminal action rules; and
- labels of memories it has actually replayed.

TR-DCTA does **not** know:

- the realized corrupt source;
- hidden provenance links;
- the realized harmful set;
- labels of unreplayed memories; or
- the full-information hindsight solution.

Known-source and full-information methods receive some of this privileged
information and are reported only as reference points.

## 16. Relationship to the main baselines

- **SC-DCTA:** the strongest immediate predecessor; corrects source-posterior
  support but still selects replays primarily for expected harm discovery.
- **ENS–SharedPosterior:** a nonmyopic active-search acquisition rule using the
  same posterior as DCTA. It is a controlled acquisition comparison, not an
  official native k-nearest-neighbor ENS reproduction.
- **Hard-source DCTA:** assumes the most likely source is certainly correct.
- **Source-then DCTA:** first spends effort resolving the source, then searches
  for affected descendants.
- **Positive-only DCTA:** does not fully exploit negative replay evidence.
- **Static risk:** computes a ranking once and does not adapt.
- **Random:** spends the identical budget without informed acquisition.
- **Known-source DCTA:** is given the true source and is nondeployable.
- **Full-information hindsight:** is given the affected set and is a reference,
  not a deployable competitor.
- **MemoRepair:** focuses on withdrawal, republication, and validation after a
  repair scope is available. It is complementary to active discovery.
- **MemAudit:** performs post-hoc causal attribution by removing retrieved
  memories and observing behavior changes. It operates at a different layer.

## 17. The theoretical guarantee

Let `mu` be base probabilistic DCTA. TR-DCTA evaluates every possible current
action using `mu` as the hypothetical continuation, and it includes the action
that `mu` itself would choose. Therefore, under the supplied finite posterior,
ideal binary feedback, and the same bounded terminal utility:

```text
Expected terminal value of TR-DCTA
    is lexicographically no smaller than
Expected terminal value of base probabilistic DCTA.
```

The proof uses induction on remaining budget:

1. With zero replays left, both methods use the same terminal decision.
2. With `b` replays left, TR-DCTA chooses the best action among all candidates,
   including the base policy's action.
3. After observing the result, replanning cannot be worse than following the
   simulated base continuation at every reachable child state.
4. Averaging over positive and negative outcomes preserves the ordering.

This is **model-relative rollout dominance**, not a claim of universal safety.
If the posterior is badly misspecified, both methods can make bad decisions.
TR-DCTA is also not claimed to be exactly Bayes-optimal because its hypothetical
future uses the base DCTA continuation instead of recursively optimizing every
future action.

## 18. Computational cost

For every possible current replay, planning branches over positive and negative
outcomes through the remaining budget. Worst-case work grows exponentially with
budget. The BabyAI terminal optimizer also examines quarantine sets, whose count
grows like

```text
number of candidate quarantines = binomial(number of memories, capacity).
```

Caching and posterior-state collapse make the evaluated budgets practical. The
full 49-task MetaWorld run, after frozen ledgers were available, required about
83 seconds on the reference machine. Much larger archives or budgets would need
limited-horizon rollout, pruning, approximate search, or additional sampling.

## 19. What the experiments found

### MetaWorld

The primary test split contained 29 tasks and 565 forced-exposure episodes:

| Method | Robot recoveries |
|---|---:|
| TR-DCTA | **322/565** |
| SC-DCTA | 289/565 |
| ENS–SharedPosterior | 287/565 |
| Known-source DCTA | 297/565 |
| Full-information reference | 325/565 |

TR-DCTA produced 33 more recoveries than SC-DCTA and 35 more than ENS. It also
reduced harmful fallbacks to four, compared with 16 for SC-DCTA and 15 for ENS.
Its task-clustered recovery improvements over both primary deployable baselines
had 95% intervals excluding zero.

Across all 49 MetaWorld tasks, TR-DCTA recovered 534 of 919 forced exposures,
versus 480 for SC-DCTA, 479 for ENS, and 539 for the full-information reference.
The all-49 aggregation is descriptive because development and validation tasks
were observed during the broader research process.

### BabyAI UnlockPickup

On 240 held-out contexts, averaging the 33%- and 67%-missing provenance views at
budget four:

| Method | Recovery rate |
|---|---:|
| TR-DCTA | **0.8875** |
| ENS | 0.8646 |
| SC-DCTA | 0.8333 |
| Full-information hindsight | 1.0000 |

ENS often replay-confirmed more weighted corruption, yet TR-DCTA recovered more
agents. This is the empirical signature of objective alignment: finding more
harm during audit is not identical to making a better final recovery decision.

## 20. What the results do and do not establish

The results support:

- terminal-recovery-aware acquisition can outperform discovery-oriented
  acquisition under incomplete provenance;
- negative and diagnostic replays can be valuable even when they find no
  harmful memory;
- planning the audit and final remediation together improves downstream robot
  recovery; and
- the benefit transfers between grid-world and continuous-control robot tasks.

The results do not establish:

- perfect recovery;
- robustness to arbitrary posterior misspecification;
- robustness to noisy replay labels;
- universal superiority at every budget or provenance condition;
- scalability to unbounded archives; or
- automatic repair or rewriting of every corrupted memory.

TR-DCTA primarily selects replays and determines quarantine. MemoRepair-like
republication or memory rewriting is a separate downstream layer.

## 21. A compact mental model

Think of an airport security team with four inspections available and several
possibly linked suitcases.

- Greedy discovery inspects the suitcase most likely to contain a prohibited
  item.
- Source-first search tries to identify the suspicious traveler first.
- Static risk creates one ranking and follows it regardless of discoveries.
- TR-DCTA asks which inspection result will most improve the final decision
  about which suitcases to remove so that the flight can depart safely.

The most suspicious suitcase is not always the most useful one to inspect.

## 22. Reading the implementation

A useful order for studying the code is:

1. `src/mcx/prob_dcta_benchmark.py` — possible worlds, conditioning, and base
   policies.
2. `src/mcx/terminal_recovery_dcta.py` — capacity-limited terminal decision and
   rollout acquisition.
3. `src/mcx/metaworld_terminal_recovery_dcta.py` — confirmed-positive-only
   behavioral recovery adapter.
4. `src/mcx/publication_v2_source.py` — source features and estimator.
5. `src/mcx/publication_v2_posterior.py` — cascade model, particles, and
   importance correction.
6. `docs/THEORY_SPECIFICATION_V0_4_TERMINAL_RECOVERY.md` — formal statement and
   proof.
7. `docs/METAWORLD_TR_DCTA_FULL49_PROTOCOL_V1.md` and the corresponding results
   document — exact experimental contract and observations.

The single best question to ask while reading any component is:

> Is this quantity only measuring what the audit found, or is it measuring
> whether the agent can safely recover after the audit?

TR-DCTA is built around the second quantity.
