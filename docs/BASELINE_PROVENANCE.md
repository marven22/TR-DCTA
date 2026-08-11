# Baseline provenance and comparison contract

This file prevents paper-derived reconstructions, internal ablations, and
privileged references from being mislabeled as equivalent official SOTA
implementations.

| Method | Code provenance | Information/budget contract | Reporting role |
|---|---|---|---|
| SC-DCTA | This project | Same archive, posterior family, and replay budget | Primary predecessor |
| ENS–SharedPosterior | ENS acquisition rule implemented here | Receives the same joint posterior as DCTA | Primary controlled active-search baseline |
| Probabilistic DCTA | This project | Same budget; earlier posterior formulation | Predecessor/ablation |
| Hard-source DCTA | This project | Collapses source uncertainty to top-1 | Ablation |
| Source-then DCTA | This project | Resolves source first, then searches cascade | Sequential ablation |
| Positive-only DCTA | This project | Updates/expands only from positive replays | Ablation |
| Static risk | This project | One frozen risk ranking; no replanning | Ablation |
| Random replay | This project | Same budget and candidate set | Sanity baseline |
| Known-source DCTA | This project | Given the realized corrupt source | Privileged-information reference |
| Full-information hindsight | This project | Given the realized affected set | Privileged-information reference |
| ACIS-Risk | Frozen predecessor implemented here | Prior/risk-aware positive expansion | Discovery-oriented predecessor |
| Graph Active Search | Paper-equation reconstruction | Budget matched on symmetrized observable graph | Secondary external baseline |
| MemoRepair | Paper-based reconstruction; not author code | Repair scope/operator selection differs from active discovery | Compatibility/appendix study |
| MemAudit | Paper-based reconstruction; not author code | Post-hoc removal attribution over retrieved memories | Secondary/appendix study |

## ENS qualification

The main ENS comparison shares DCTA's fitted joint posterior and changes only
the acquisition rule. This is a deliberately strong controlled comparison, but
it is not an official reproduction of a native k-nearest-neighbor ENS system.
Tables and captions must use `ENS–SharedPosterior` or an equivalently explicit
label.

## MemoRepair qualification

The reconstruction follows the public optimization contract, cascade
withdrawal, republication, and validation structure. Author code and
benchmark-specific candidate values/costs were unavailable when the study was
implemented. MemoRepair assumes or derives a repair scope; TR-DCTA actively
spends physical replay budget to discover what should be quarantined. The
comparison supports complementarity and failure-scope analysis, not an
unqualified universal-superiority claim.

## MemAudit qualification

The reconstruction performs counterfactual memory removal and causal
attribution over retrieved context. Its Memory-LIBERO experiment is not the
method's native sparse-MINJA setting. Report it as a scoped reconstruction and
retain CMIS-only, CAS-only, retrieval-frequency, and random-deletion rows as
MemAudit ablations.

## Methods that are related work, not baselines

MINJA, AgentPoison, OEP, MemoryGraft, sleeper-memory poisoning, and similar
systems motivate attack construction and threat models. Unless their executable
attack or defense is actually run under a matched contract, they belong in
Related Work and must not be listed as empirical comparison rows.

