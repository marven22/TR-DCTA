# AgentDojo Graph Active Search and MemoRepair results

Status: complete, independently integrity-checked external-baseline extension on all 97 official AgentDojo tasks.

The experiment contains 291 latent corruption instances, 3,201 provenance views, 38,412 Graph Active Search runs, and 6,402 MemoRepair runs. Graph Active Search is replay-budget matched at 2, 4, and 8 replays. The primary table below uses 4. MemoRepair is a repair-scope method and is reported with repair-operation cost rather than pretending that its repairs equal replay queries.

## Primary safe-recovery result

| Provenance | TR-DCTA | GraphAS known root, native | GraphAS known root, shared terminal | GraphAS signaled root, native | GraphAS signaled root, shared terminal | MemoRepair known root | MemoRepair signaled root |
|---|---:|---:|---:|---:|---:|---:|---:|
| Complete | 1.000 | 1.000 | 1.000 | 0.928 | 1.000 | 1.000 | 0.753 |
| 33% missing | 1.000 | 0.969 | 0.969 | 0.900 | 0.962 | 0.551 | 0.422 |
| 67% missing | 1.000 | 0.829 | 0.901 | 0.805 | 0.897 | 0.172 | 0.136 |

The known-root methods are privileged references: they are told the true invalid origin. The signaled-root methods are information-matched adaptations that receive only the same frozen source prior available to TR-DCTA.

At 67% missing provenance, TR-DCTA exceeds the strongest Graph Active Search variant—the privileged known-root acquisition with the generous shared terminal—by 0.099 mean safe recovery (95% task-stratified bootstrap CI 0.078 to 0.121; 52 task wins, 45 ties, no losses). Against the information-matched Graph Active Search variant with the same generous terminal, the difference is 0.103 (95% CI 0.082 to 0.125; 56 wins, 41 ties, no losses).

This isolates the central result: incomplete lineage, rather than merely uncertain source identity or a weak terminal decision, causes graph traversal and repair propagation to miss harmful descendants. TR-DCTA maintains recovery by reasoning jointly over plausible hidden lineage completions and spending replays for final recovery.

## MemoRepair cost and interpretation

All intervals below are 95% suite-stratified task-cluster bootstrap intervals from 10,000 draws. The 97 tasks—not their correlated origins or provenance masks—are the resampling units.

| Provenance | Root information | Safe recovery (95% CI) | Repair recall (95% CI) | Repair operations (95% CI) |
|---|---|---:|---:|---:|
| Complete | Known true root | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 2.804 [2.732, 2.876] |
| Complete | Highest-prior root | 0.753 [0.725, 0.780] | 0.753 [0.725, 0.784] | 2.804 [2.732, 2.876] |
| 33% missing | Known true root | 0.551 [0.538, 0.564] | 0.656 [0.643, 0.670] | 1.544 [1.489, 1.596] |
| 33% missing | Highest-prior root | 0.422 [0.400, 0.444] | 0.499 [0.477, 0.520] | 1.559 [1.495, 1.623] |
| 67% missing | Known true root | 0.172 [0.157, 0.186] | 0.244 [0.235, 0.252] | 0.480 [0.463, 0.498] |
| 67% missing | Highest-prior root | 0.136 [0.120, 0.152] | 0.191 [0.178, 0.204] | 0.496 [0.459, 0.532] |

With complete lineage and the true root, MemoRepair repairs the entire visible source lineage and recovers every instance. At 67% missing provenance, broken visible edges stop its cascade traversal; safe recovery falls to 0.172 even with the true root. The declining operation count is failed reachability, not improved efficiency.

MemoRepair therefore remains a valuable complementary baseline, but it is not a budget-matched auditing method. Its result demonstrates what deterministic repair propagation can and cannot do when provenance is incomplete.

Artifacts:

- Frozen protocol: `configs/agentdojo_external_baselines_all97_freeze_v1.json`
- Full report: `reports/agentdojo_external_baselines_all97_v1.json`
- Verification: `reports/agentdojo_external_baselines_all97_verified_v1.json`
- Runner: `scripts/run_agentdojo_external_baselines_all97_v1.py`
- Verifier: `scripts/verify_agentdojo_external_baselines_all97_v1.py`
