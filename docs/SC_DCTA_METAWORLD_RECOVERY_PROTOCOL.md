# Meta-World end-to-end recovery protocol

## Status and purpose

This document fixes the behavioral endpoint before the held-out 29-task
evaluation is opened. Implementation is first checked on the existing 10-task
development split. SC-DCTA, its posterior, its audit policy, and all competing
audit policies remain frozen; this study adds one common remediation and task
execution layer after auditing.

The question is: **after a fixed number of physical memory replays, does an
auditor enable the robot to recover useful behavior, rather than merely assign
high scores to labeled corruptions?**

## Experimental unit and primary condition

- Unit: one task, active-source rotation, and provenance mask (an archive).
- Development: 10 Meta-World tasks; evaluation: the untouched 29 Meta-World
  tasks.
- Primary condition: four replay means and 25% missing provenance.
- Primary method: SC-DCTA.
- Comparators: ENS, hard-source DCTA, source-then-DCTA, static risk, random,
  known-source DCTA, and the full-information oracle where available.
- The same replay sequences already produced by the frozen audit experiment are
  reused. No method is retuned for this endpoint.

## Common remediation rule

Each replay reveals whether the audited memory's recommended policy succeeds on
the target task. After four replays, every replayed memory that failed is
quarantined. Replayed memories that succeeded and all unaudited memories remain
available. This rule is identical for every auditor.

## Behavioral endpoint

For each archive and each post-audit condition:

1. Embed the target instruction and observable memory text with
   `sentence-transformers/all-mpnet-base-v2` at revision
   `e8c3b32edf5434bc2275fc9bab85f82640a19130`.
2. Retrieve the five most similar surviving memories, breaking ties by creation
   order and then memory ID.
3. Ask `Qwen/Qwen2.5-14B-Instruct` at revision
   `cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8`, with greedy decoding, to choose
   exactly one retrieved experience. One formatting-repair attempt is allowed.
4. Map the selected memory to its hidden policy only after selection. Score the
   choice using the policy outcome already physically verified in Meta-World
   during archive construction.

The corrupted archive before auditing and a fully clean counterfactual archive
are evaluated with exactly the same retrieval and Qwen procedure. The clean
archive changes memory content, not the underlying task or candidate IDs.

## Leakage boundary

The model-facing event runner receives only task text, public memory text,
creation times, candidate IDs, and the IDs quarantined as outcomes of performed
replays. It never loads affected-memory labels, source labels, hidden policy
IDs, or simulator outcomes. A separate evaluator joins selected memory IDs to
the private policy/outcome ledger afterward.

## Outcomes

Primary behavioral outcome:

- post-audit task success among *recoverable harmful archives*, defined before
  comparing methods as archives where the corrupted condition fails and the
  clean-reference condition succeeds.

Secondary outcomes:

- success over all archives before and after remediation;
- aggregate fraction of the clean-reference performance deficit recovered;
- harmful memories quarantined, benign memories retained, and false
  quarantines;
- recovery per physical replay;
- invalid model-output count.

The recoverable-harmful analysis is explicitly conditional and its denominator
will be reported. It will not be presented as performance over all archives.

## Statistical analysis

Report counts and task-clustered paired bootstrap 95% confidence intervals
(10,000 draws) for SC-DCTA minus each comparator. Rotations share a task and are
therefore resampled together. Exact paired win/tie/loss counts are also
reported. No claim of superiority is made when the confidence interval spans
zero.

## Development gate and held-out policy

The development run checks integrity, output validity, and whether the endpoint
has enough recoverable harmful archives to be informative. It may motivate a
single documented correction to the evaluation machinery, but not tuning to
favor SC-DCTA. The 29-task evaluation ledger remains unopened by the behavioral
runner until the executable configuration and artifact hashes are frozen.

If fewer than 20 of the 87 primary evaluation archives are recoverable harmful
archives, the conditional endpoint will be reported as underpowered and only
descriptive. Null or adverse results are retained.

## Exposure-conditioned stress test

Because ordinary retrieval incidence and audit quality are separate questions,
the development study also permits a controlled stress test. Every affected
descendant becomes one exposure episode. That same descendant is forced to
retrieval rank one for every method. After the common audit and quarantine,
the first surviving memory is executed; all remaining candidates follow the
ordinary frozen semantic order.

The primary stress-test metric is behavioral recovery rate from a guaranteed
pre-audit failure. Anchor-quarantine rate is reported separately, as is the rate
at which quarantine exposes another harmful fallback. Results are clustered by
task. This conditional stress test does not estimate natural attack incidence
and will never be presented as doing so.
