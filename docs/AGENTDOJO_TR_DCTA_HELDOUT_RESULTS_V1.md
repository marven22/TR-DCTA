# AgentDojo TR-DCTA method-held-out results v1

## Status and claim boundary

**Complete and independently verified.** The frozen TR-DCTA method was run on
32 new AgentDojo user workflows that had zero user-task overlap with the 16
development archives. Because official utility/security labels were computed
during exhaustive structural qualification, this is correctly described as a
method-held-out evaluation, not a completely label-blind dataset.

## Scale

- Four suites: Workspace, Travel, Banking, and Slack
- 32 archives, exactly eight per suite
- 96 true-source instances: all three source rotations per archive
- One complete-provenance view and five distinct 67%-missing masks
- 576 posterior views
- Replay budgets 2, 4, and 8
- 11 structured methods plus 50 random repetitions
- 105,408 method runs
- 24 instances in each source-confidence regime
- 32 instances at each cascade length

Each positive memory label was backed by an executed workflow satisfying the
official injection evaluator. Each negative label was backed by a clean
workflow satisfying legitimate utility without satisfying the paired attack.

## Primary confirmatory result

The prespecified primary setting averages five distinct 67%-missing provenance
masks and all three source rotations within each archive at budget four.

| Method | Safe recovery | Weighted quarantine recall | Weighted replay discovery |
|---|---:|---:|---:|
| **TR-DCTA** | **1.0000** | **1.0000** | 0.6809 |
| ENS | 0.9521 | 0.9760 | **0.9076** |
| Source-then-DCTA | 0.9333 | 0.9743 | 0.8319 |
| SC-DCTA | 0.9313 | 0.9792 | 0.8087 |
| Probabilistic DCTA | 0.9313 | 0.9792 | 0.8087 |
| Known-source DCTA | 0.9771 | 0.9906 | 0.9486 |
| Hard-source DCTA | 0.8708 | 0.9184 | 0.8531 |
| Random | 0.8720 | 0.9344 | 0.4420 |
| Full-information hindsight | 1.0000 | 1.0000 | 0.8087 |

There are 480 primary source-mask cases. TR-DCTA recovered 480/480; ENS
recovered 457/480; SC-DCTA and probabilistic DCTA recovered 447/480. Random
replay averaged 418.58/480 across its 50 repetitions.

## Paired archive-level inference

Mask repetitions and source rotations were averaged within archive. The table
uses 10,000 suite-stratified paired bootstrap draws over the 32 archives.

| Recovery contrast | Difference | 95% interval | Archive wins/ties/losses |
|---|---:|---:|---:|
| TR-DCTA minus ENS | +0.0479 | [0.0250, 0.0729] | 13 / 19 / 0 |
| TR-DCTA minus SC-DCTA | +0.0688 | [0.0417, 0.0979] | 17 / 15 / 0 |
| TR-DCTA minus Prob-DCTA | +0.0688 | [0.0417, 0.1000] | 17 / 15 / 0 |
| TR-DCTA minus source-then-DCTA | +0.0667 | [0.0417, 0.0938] | 20 / 12 / 0 |
| TR-DCTA minus hard-source DCTA | +0.1292 | [0.0896, 0.1688] | 20 / 12 / 0 |
| TR-DCTA minus random | +0.1280 | [0.1161, 0.1398] | 32 / 0 / 0 |

Weighted quarantine-recall improvements were also positive: +0.0240 over ENS
[0.0125, 0.0375], +0.0208 over SC-DCTA [0.0128, 0.0299], and +0.0656 over
random [0.0590, 0.0723].

## Replay-budget stress test

| Provenance | Budget | TR-DCTA | ENS | SC-DCTA | Random |
|---|---:|---:|---:|---:|---:|
| Complete | 2 | 1.000 | 1.000 | 0.833 | 0.904 |
| Complete | 4 | 1.000 | 1.000 | 1.000 | 0.983 |
| Complete | 8 | 1.000 | 1.000 | 0.948 | 1.000 |
| 67% missing | 2 | **0.844** | 0.763 | 0.710 | 0.667 |
| 67% missing | 4 | **1.000** | 0.952 | 0.931 | 0.872 |
| 67% missing | 8 | **1.000** | 1.000 | 0.969 | 1.000 |

At budget two, TR-DCTA already leads under severe provenance loss. At budget
eight, most posterior-aware methods approach saturation. Budget four is the
informative middle regime and was fixed as primary before execution.

## Multiple-mask and subgroup robustness

TR-DCTA recovered 96/96 instances under every one of the five partial-mask
replicates. ENS recovery ranged from 90/96 to 93/96; SC-DCTA ranged from 85/96
to 92/96.

At the primary setting, TR-DCTA recovery was 1.000 in every suite. ENS ranged
from 0.942 to 0.958 and SC-DCTA from 0.900 to 0.950. TR-DCTA was also 1.000 in
all four source-confidence regimes. The largest comparator separation occurred
under misleading source evidence: ENS recovered 0.892 and SC-DCTA 0.842.

By cascade length, all three methods recovered every length-one instance. At
length three, TR-DCTA remained at 1.000 while ENS fell to 0.856 and SC-DCTA to
0.813. This is consistent with the terminal-objective account: longer harmful
sets make a locally discovery-oriented replay policy less reliable for the
capacity-limited final decision.

## Interpretation

The core finding repeats across MetaWorld, BabyAI, and now tool-agent
workflows: replay discovery and terminal remediation are different objectives.
ENS found substantially more weighted corruption during AgentDojo replay
(0.908 versus 0.681), yet TR-DCTA made better terminal quarantine decisions
and recovered more cases. TR-DCTA matched full-information hindsight on the
primary endpoint despite not receiving hindsight labels.

The result should not be overstated. AgentDojo workflows are deterministic, so
the five repetitions vary provenance uncertainty rather than simulator noise.
The 32 archives—not the 480 source-mask cases—are the statistical units. The
official labels were used to structurally qualify candidate archives, although
none of the selected user workflows influenced method development.

## Verification and artifacts

The independent verifier recomputed all 105,408 row outcomes, every aggregate,
every primary estimate, and every bootstrap interval. It independently checked
the five masks, development exclusion, and frozen hashes, then re-executed all
576 saved positive/negative workflows with zero semantic mismatches.

- Protocol: `docs/AGENTDOJO_TR_DCTA_HELDOUT_PROTOCOL_V1.md`
- Config: `configs/agentdojo_tr_dcta_heldout_freeze_v1.json`
- Runner: `scripts/run_agentdojo_tr_dcta_heldout_v1.py`
- Verifier: `scripts/verify_agentdojo_tr_dcta_heldout_v1.py`
- Raw report: `reports/agentdojo_tr_dcta_heldout_v1.json`
- Verification: `reports/agentdojo_tr_dcta_heldout_verified_v1.json`
- Report SHA-256: `77d3ded6151e376503cb0ceed6c62bbffc1b65fded1ac8db8546063528153b27`
- Verification SHA-256: `d0ea31b37260cedbd1793f5a8bdd2388bf6a36ab2f1f914a677580326d4a4162`
