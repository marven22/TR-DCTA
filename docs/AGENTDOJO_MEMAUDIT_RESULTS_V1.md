# AgentDojo MemAudit results v1

## Scope and integrity

The evaluation covers all 97 official AgentDojo tasks, all 291 frozen corruption instances, all 552 logged harmful-memory events, and all 3,201 provenance views. The report contains 9,603 method rows (three terminal budgets per view) and passes every independent verification check. Statistical intervals use 10,000 suite-stratified task-cluster bootstrap draws with the 97 tasks as the independent units.

The preceding label-blind natural-retrieval pilot selected no harmful memory in 12 trials. It was therefore a retrieval diagnostic, not evidence about MemAudit attribution. The primary result uses forced exposure to every logged harmful event and asks whether MemAudit can identify and quarantine the responsible memories after harm has occurred.

## Primary outcome

At nominal budget 4, with terminal capacity capped at the archive depth, MemAudit safely recovers 275 of 291 corruption instances: 94.50%, with a task-clustered 95% interval of 91.41% to 96.91%. Budget 8 is identical because AgentDojo archives have depth two or three. At budget 2 it recovers 200 of 291 instances (68.73%).

MemAudit is provenance-blind, so these results are exactly invariant under complete, 33%-missing, and 67%-missing provenance. The repeated mask views preserve the frozen paired populations but are not counted as independent evidence.

## Comparisons at budget 4

On complete provenance, TR-DCTA safely recovers all 291 instances. MemAudit is lower by 5.50 percentage points (task-clustered paired 95% interval: -8.25 to -3.09), corresponding to 16 additional failures. This is especially notable because MemAudit was given forced exposure to every harmful event and made 2,760 leave-one-out counterfactual calls (five per event); these calls are not budget-equivalent to the active-search replay budgets.

Against the information-matched Graph Active Search native terminal, MemAudit is 1.72 points higher on complete provenance, but the paired interval crosses zero (-2.06 to 5.50). Its advantage grows as provenance is removed because MemAudit ignores graph provenance: +4.54 points at 33% missing and +13.95 points at 67% missing.

Against the information-matched MemoRepair adaptation, MemAudit is substantially higher: +19.24 points with complete provenance, +52.30 at 33% missing, and +80.89 at 67% missing. MemoRepair remains a repair baseline with a different, non-budget-matched intervention model, so these comparisons must retain that qualifier.

## Interpretation

MemAudit is a strong but expensive retrospective auditor on AgentDojo. It can recover most corruption instances once harmful events are supplied, and it is naturally insensitive to missing provenance. It does not dominate TR-DCTA: the latter achieves perfect recovery here with a far smaller active replay budget. The result therefore strengthens the paper without overstating it: a causal batch auditor is competitive, while TR-DCTA's sequential, terminal-objective-aware search is both more effective and more resource-efficient on this benchmark.

Artifacts:

- Protocol: `configs/memaudit_agentdojo_all97_freeze_v1.json` and `docs/AGENTDOJO_MEMAUDIT_PROTOCOL_V1.md`
- Natural pilot: `reports/memaudit_agentdojo_pilot_v1.json`
- Full result: `reports/memaudit_agentdojo_all97_v1.json`
- Independent verification: `reports/memaudit_agentdojo_all97_verified_v1.json`
- Runner: `scripts/run_memaudit_agentdojo_all97_v1.py`
- Verifier: `scripts/verify_memaudit_agentdojo_all97_v1.py`
