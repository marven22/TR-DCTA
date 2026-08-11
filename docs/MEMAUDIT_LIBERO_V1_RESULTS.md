# MemAudit Reconstruction on Memory-LIBERO

## Status and scope

This study implements equations (7), (8), and (10) and Algorithm 1 from
MemAudit (arXiv:2605.23723v1). The May 2026 paper explicitly reports that no
public author code or data release accompanies the submission. This is therefore
a paper-faithful reconstruction with declared choices, not official code or a
code-identical reproduction.

The reconstruction was frozen before the complete 67-archive observable run.
Private affected-memory labels were loaded only by the scoring stage after Qwen
events, counterfactuals, and rankings had been written.

## Frozen implementation

- Semantic retrieval and neighborhoods: `all-mpnet-base-v2`, pinned revision.
- Consistency model: `DeBERTa-v3-base-mnli-fever-anli`, pinned revision.
- Five retrieved memories and five semantic neighbors.
- Ordered memory-to-neighbor contradiction probability.
- Per-archive min-max normalization.
- Paper-default fusion: `0.6 * normalized CMIS + 0.4 * normalized CAS`.
- Agent: Qwen2.5-14B-Instruct, pinned revision, greedy decoding.
- Harm: binary failure of the selected policy on the target LIBERO task.
- Physical outcomes: the previously frozen native-success/donor-failure MuJoCo
  screen; each retained outcome had been repeated and verified deterministic.

For each archive, Qwen received the five memories most semantically relevant to
the target task and selected one experience to execute. The selected memory's
policy determined physical task harm. When the original choice was harmful,
MemAudit removed each of the five retrieved memories in turn, reran retrieval
and Qwen, and measured the reduction in harm (CMIS). It then fused CMIS with the
global consistency anomaly score (CAS) and ranked all 18 candidates.

## Applicability population

Qwen selected a failing donor policy in 20 of 67 archives, giving an overall
pre-audit attack/failure rate of 29.85%. MemAudit is a post-hoc method, so its
causal attribution applies to these 20 observed-harm archives. All 20 selected
memories were independently confirmed to be in the private affected set.

Each applicable archive required five counterfactual Qwen calls before any
memories were removed. DCTA and ACIS retained their original physical replay
budgets. The comparison therefore does not give DCTA extra observations.

## Affected-memory recall on the same 20 archives

| Removal/audit budget | MemAudit | CMIS only | CAS only | Retrieval frequency | Random deletion | DCTA-Risk-Local | ACIS-Risk |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 14.18% | 15.69% | 4.29% | 26.48% | 10.82% | 31.51% | **34.80%** |
| 4 | 19.11% | 25.76% | 10.10% | 50.56% | 21.57% | **58.88%** | 57.91% |
| 6 | 27.83% | 39.36% | 18.57% | 57.86% | 32.28% | **77.58%** | 73.86% |
| 9 | 37.02% | 55.36% | 29.30% | 65.35% | 49.37% | 90.32% | **91.44%** |

At the primary four-memory budget, MemAudit trails DCTA by 39.77 percentage
points. The paired 95% bootstrap interval for MemAudit minus DCTA is -47.61 to
-32.17 points, with 0 wins, 0 ties, and 20 losses for MemAudit. It trails ACIS
by 38.80 points (95% interval: -45.77 to -32.32).

Full MemAudit also trails CMIS-only by 6.65 points at budget four. This indicates
that the structural anomaly component harms rather than helps ranking in these
propagated-corruption archives. It also trails the paper-matched 10-run random
deletion average by 2.46 points at this budget, although it remains above random
when only two memories are removed.

## Task-level harm after MemAudit removal

Among the 20 archives that initially produced harm, the post-removal failure
rates were:

| Memories removed | Post-hoc failure rate | Failure rate over all 67 archives |
|---:|---:|---:|
| 2 | 50% | 14.93% |
| 4 | 50% | 14.93% |
| 6 | 50% | 14.93% |
| 9 | 60% | 17.91% |

Thus MemAudit eliminates half of the observed harmful events at the primary
budget but does not reproduce the zero-ASR result reported for the paper's
sparse MINJA QA/RAP settings. Removing nine memories is worse because clean
support can be deleted, allowing a failing policy to become selected again.

## Mechanism diagnosis

The 20 harmful archives contain a mean 5.75 affected memories out of 18, or
31.94% contamination (range: 16.67% to 44.44%). The MemAudit paper reports an
operating boundary near 25% contamination, after which mutually supportive
poisoned memories cease to look anomalous.

That mechanism appears directly here:

- mean CAS for affected memories: 0.171;
- mean CAS for clean memories: 0.320;
- mean causal selected-memory rank under full MemAudit: 7.10;
- mean rank under CMIS only: 5.50;
- mean rank under CAS only: 11.75.

The propagated affected memories form a semantically coherent local cluster.
Clean corrective memories can look more contradictory to that cluster, causing
CAS to prioritize clean memories. DCTA instead models directed propagation from
the invalid source and uses physical replay outcomes to update correlated
descendant beliefs.

This supports a scoped conclusion: MemAudit is effective for causal attribution
of isolated retrieved poison, whereas directed cascade auditing is better suited
to coherent descendant contamination. It does not establish universal
superiority over MemAudit in its native sparse-MINJA setting.

## Reproducibility

- Core: `src/mcx/memaudit.py`
- LIBERO adapter: `src/mcx/memaudit_libero.py`
- Frozen configuration: `configs/memaudit_libero_v1.json`
- Execution freeze: `configs/memaudit_libero_v1_execution_freeze.json`
- Observable runner: `scripts/run_memaudit_libero_events_v1.py`
- Private-label evaluator: `scripts/evaluate_memaudit_libero_v1.py`
- Integrity validator: `scripts/validate_memaudit_libero_v1.py`
- Observable events: `results/memaudit_libero_v1_observable_events.json`
- Evaluation: `results/memaudit_libero_v1_evaluation.json`
- Audit: `results/memaudit_libero_v1_validation.json`

The integrity audit passes every check, and the repository's 125 automated tests
pass.
