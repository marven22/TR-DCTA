# V6 MemoRepair Compatibility Protocol

Status: frozen before execution.

## Question

How does a faithful reimplementation of MemoRepair's public cascade-repair
contract compare with frozen ACIS-T when influence provenance is complete,
missing at increasing rates, or both missing and spurious?

This is a compatibility study, not an exact reproduction of MemoRepair's
published MemoryArena table. The authors' implementation, trace adapter,
per-candidate values and costs, repair prompts/operators, and validation suite
are not publicly specified.

## Paper-exact components

- Influence-only reachability from the corrected root defines the cascade.
- The whole computed cascade is withdrawn before repair.
- Artifact-aware modes are `recompute`, `regen`, `param`, or `remove`.
- Repair dependencies require predecessor closure.
- Unavailable, non-repairable, and cyclic candidates are non-executable.
- The fixed-lambda objective uses `lambda = 0.3`.
- Selection is the exact maximum-weight predecessor closure found by one
  source-sink minimum cut.
- Execution is topological; only validated successors are republished, and a
  validation failure blocks its selected dependents.

## Frozen benchmark adapter

- Dataset: the 30 V6 task-matched, 50-memory archives generated from the pinned
  Qwen2.5-14B run.
- Event: correction of the known bad source.
- Parent and exposure records are both treated as influence provenance and
  duplicate logical edges are collapsed.
- `m4` and `m6` artifacts are summaries (`regen`); other stored artifacts are
  replayable records (`recompute`). No parametric artifacts are present.
- The paired clean archive is the replay/validation oracle. All scoped
  candidates are executable and validate; an unnecessarily scoped clean
  artifact regenerates to an equivalent clean successor but counts as
  collateral work.
- Because the paper does not publish the benchmark-specific `w_i,c_i` schedule,
  all candidates receive `w_i=c_i=1`. This is a neutral, declared adaptation;
  at `lambda=0.3` it selects all executable candidates. Selector-efficiency
  claims from the paper cannot be reproduced from public information.

## Conditions

For every archive use one complete-provenance graph and ten deterministic masks
for each noisy condition:

- complete provenance;
- independent 25%, 50%, 75%, and 100% removal of recorded parent/exposure
  edges;
- the direct source-to-first-descendant exposure forced absent, plus 75%
  removal of all remaining edge records;
- the preceding forced-missing condition plus spurious logical edges equal to
  25% of the complete logical-edge count.

Spurious edges are deterministic, chronological, and sampled from nonedges.

## Methods and cost accounting

- MemoRepair reimplementation.
- Frozen ACIS-T with its unchanged 13-of-49 replay budget.
- ACIS-T + MemoRepair: replay-confirmed artifacts are added as discovered
  source influence links before the MemoRepair contract runs.
- Full replay oracle (49 operations, recall 1.0).

MemoRepair operator cost is the number of selected repair candidates. ACIS-T
cost is 13 replay operations. Hybrid end-to-end cost conservatively counts both
13 discovery replays and every selected MemoRepair operator; it is therefore an
upper bound because a production system could reuse successful replay output.

## Outcomes

Report affected-cascade recall, validated repair recall, stale leak, collateral
scope, native normalized MemoRepair cost, and end-to-end operations normalized
to full replay. Use archive-level paired bootstrap intervals for method recall
differences. The comparison is diagnostic and remains a development result.

