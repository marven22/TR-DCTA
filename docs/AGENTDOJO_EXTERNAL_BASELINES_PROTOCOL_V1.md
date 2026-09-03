# AgentDojo external-baseline extension (frozen protocol)

This is a locked, post-hoc extension of the completed all-97 AgentDojo study. TR-DCTA and its earlier results are not changed or tuned in response to these baselines.

## Graph Active Search

We reconstruct Wang et al.'s graph active-search equations using the visible provenance graph. It receives the same replay budgets (2, 4, and 8) as TR-DCTA. Because graph active search requires a known positive seed, we report both (a) its native, privileged initialization with the true invalid origin and (b) an information-matched adaptation initialized with the origin having the largest already-available source prior (lexical tie break). This is a reconstruction, not author-provided AgentDojo code.

Missing provenance can produce degree-zero vertices, for which the published neighbor-average term is undefined. We assign such vertices the frozen class prior; all non-isolated vertices use the paper equation exactly.

For each initialization assumption, we report two terminal variants:

1. **Native graph score:** confirmed harmful replays are quarantined first, then remaining slots use graph-active-search scores.
2. **Shared Bayesian terminal:** only the acquisition policy comes from graph active search; its observed replay labels update the same posterior and the same terminal quarantine optimizer used by every DCTA method. This generous control isolates acquisition quality from terminal-decision quality.

## MemoRepair

We use the repository's transparent reconstruction of the public MemoRepair algorithm. Every descendant is a replayable record with unit repair value and cost, the paper's fixed lambda is 0.3, and validation passes after recomputation. This is not the authors' code because their benchmark-specific operators, values, costs, and validation suites are unavailable.

We report:

1. **Known-root MemoRepair:** the invalid origin is supplied. This is MemoRepair's native, privileged information assumption and is not an information-matched head-to-head comparison.
2. **Signaled-root MemoRepair:** the supplied origin is the source with the largest prior probability. This is our explicitly labeled information-matched adaptation.

MemoRepair is not replay-budget matched. We report repair success, corrupt-descendant recall, collateral repairs, and number of repair operations. A repaired artifact is treated as safely republished; it is not counted as quarantined.

MemoRepair uncertainty uses 10,000 suite-stratified task-cluster bootstrap draws. All origins and provenance masks belonging to one AgentDojo task are averaged first; whole tasks are then resampled within their original suites. We report 95% percentile intervals for recovery, repair recall, collateral repair, and repair-operation cost. This prevents correlated masks from being counted as independent samples.

The source report, its independent verification, algorithm parameters, and implementation hashes are frozen in `configs/agentdojo_external_baselines_all97_freeze_v1.json`.
