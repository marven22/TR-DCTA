from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_OUT = ROOT / "docs" / "METAWORLD_DCTA_EXPERIMENT_LEDGER.md"
JSON_OUT = ROOT / "results" / "metaworld_dcta_experiment_ledger.json"
REPORT_DIR = ROOT / "reports" / "metaworld_dcta_experiment_ledger"
ARTIFACT_OUT = REPORT_DIR / "artifact.json"
NOTES_OUT = REPORT_DIR / "source_notes.md"
SNAPSHOT_OUT = REPORT_DIR / "report_snapshot.sqlite"


STUDIES = [
    {
        "id": "MW-00",
        "title": "Meta-World feasibility and archive screen",
        "phase": "exploratory",
        "paper_role": "historical-only",
        "scope": "Early archive-population screening before the publication-v2 pipeline was frozen.",
        "primary_condition": "Screening, not a performance claim.",
        "methods": ["Prob-DCTA candidate pipeline"],
        "headline": "Retain only as provenance for benchmark construction; do not report as final performance.",
        "files": [
            "configs/prob_dcta_metaworld_v2_screen.json",
            "results/prob_dcta_metaworld_v2_screen.json",
            "scripts/run_prob_dcta_metaworld_v2_screen.py",
        ],
    },
    {
        "id": "MW-01",
        "title": "Frozen publication-v2 Prob-DCTA test",
        "phase": "held-out-confirmatory",
        "paper_role": "superseded-method-history",
        "scope": "29 Meta-World test tasks within a 41-task mixed LIBERO/Meta-World frozen test.",
        "primary_condition": "Four replays; 25% missing provenance.",
        "methods": ["Prob-DCTA", "DCTA-Top1", "ACIS-Risk", "ENS", "Source-then-DCTA", "Known-source"],
        "headline": "Meta-World recall: Prob-DCTA 0.457, ENS 0.486, Top1 0.254, ACIS-Risk 0.270, known-source 0.618. This motivated later Meta-World calibration and is not the final SC-DCTA result.",
        "files": [
            "docs/PROB_DCTA_PUBLICATION_V2_TEST_RESULTS.md",
            "results/prob_dcta_publication_v2_test_evaluation.json",
            "results/prob_dcta_publication_v2_test_gate_analysis.json",
            "configs/prob_dcta_publication_v2_inference_final.json",
            "scripts/analyze_prob_dcta_publication_v2_test.py",
        ],
    },
    {
        "id": "MW-02",
        "title": "Development oracle and planning diagnostic",
        "phase": "development-diagnostic",
        "paper_role": "appendix-mechanism",
        "scope": "10 development tasks; 90 archive conditions; no validation/test labels.",
        "primary_condition": "Four replays; 25% missing provenance.",
        "methods": ["Prob-DCTA", "ENS", "Random", "Source-then-DCTA", "exact posterior planner", "information oracles"],
        "headline": "Prob-DCTA 0.469 versus exact same-posterior planning 0.476 and hindsight ceiling 0.748; posterior localization, not planning depth, explained most of the gap.",
        "files": [
            "docs/METAWORLD_DEVELOPMENT_ORACLE_DIAGNOSTIC_RESULTS.md",
            "results/prob_dcta_metaworld_development_oracle_diagnostic.json",
            "scripts/run_prob_dcta_metaworld_development_diagnostic.py",
            "src/mcx/publication_v2_oracle.py",
            "tests/test_publication_v2_oracle.py",
        ],
    },
    {
        "id": "MW-03",
        "title": "Task-cross-fitted posterior calibration",
        "phase": "development",
        "paper_role": "appendix-method-development",
        "scope": "10 development tasks in leave-one-task-out folds; 30 primary task/rotation archives.",
        "primary_condition": "Four replays; 25% missing provenance.",
        "methods": ["adapted Prob-DCTA", "external Prob-DCTA", "ENS", "Source-then-DCTA", "known-source"],
        "headline": "Adapted Prob-DCTA improved from 0.542 to 0.637 and reached 99.4% of the cross-fitted known-source score.",
        "files": [
            "docs/METAWORLD_CROSSFIT_POSTERIOR_PROTOCOL.md",
            "docs/METAWORLD_CROSSFIT_POSTERIOR_RESULTS.md",
            "results/prob_dcta_metaworld_development_crossfit.json",
            "results/prob_dcta_metaworld_development_public_mask_consistent.json",
            "results/prob_dcta_metaworld_development_private_mask_consistent.json",
            "scripts/run_prob_dcta_metaworld_crossfit.py",
        ],
    },
    {
        "id": "MW-04",
        "title": "Frozen adapted validation",
        "phase": "validation",
        "paper_role": "appendix-method-selection",
        "scope": "10 validation tasks; 90 archive conditions; citation-consistent public ledger.",
        "primary_condition": "Four replays; 25% missing provenance.",
        "methods": ["adapted Prob-DCTA", "adapted ENS", "hard-source DCTA", "known-source DCTA", "external Prob-DCTA"],
        "headline": "Adapted Prob-DCTA reached 0.646 versus ENS 0.670 and hard-source 0.685; the result motivated confidence-aware/hard-source investigation.",
        "files": [
            "docs/METAWORLD_ADAPTED_VALIDATION_RESULTS.md",
            "configs/prob_dcta_metaworld_adapted_validation_freeze.json",
            "configs/prob_dcta_metaworld_adapted_source_validation.json",
            "configs/prob_dcta_metaworld_adapted_cascade_validation.json",
            "results/prob_dcta_metaworld_adapted_validation_evaluation.json",
            "results/prob_dcta_metaworld_external_source_validation_evaluation.json",
            "results/prob_dcta_metaworld_adapted_validation_analysis.json",
            "results/prob_dcta_metaworld_validation_public_mask_consistent.json",
            "results/prob_dcta_metaworld_validation_private_mask_consistent.json",
            "scripts/analyze_prob_dcta_metaworld_adapted_validation.py",
        ],
    },
    {
        "id": "MW-05",
        "title": "Confidence-aware selector development test",
        "phase": "development-negative",
        "paper_role": "excluded-negative-development",
        "scope": "Leave-one-task-out fitting on 10 Meta-World development tasks.",
        "primary_condition": "Four replays; 25% missing provenance.",
        "methods": ["confidence-aware DCTA", "Prob-DCTA", "hard-source DCTA", "ENS"],
        "headline": "The preregistered continuation gate failed; this selector was not promoted to the final method.",
        "files": [
            "docs/CONFIDENCE_AWARE_DCTA_DEVELOPMENT_PROTOCOL.md",
            "docs/CONFIDENCE_AWARE_DCTA_DEVELOPMENT_RESULTS.md",
            "results/confidence_aware_dcta_metaworld_development.json",
            "scripts/run_confidence_aware_dcta_metaworld_development.py",
            "src/mcx/confidence_aware_dcta.py",
            "tests/test_confidence_aware_dcta.py",
        ],
    },
    {
        "id": "MW-06",
        "title": "Support-corrected DCTA development",
        "phase": "development",
        "paper_role": "appendix-method-development",
        "scope": "10 Meta-World development tasks; support correction and particle-quality checks.",
        "primary_condition": "Four replays; 25% missing provenance.",
        "methods": ["SC-DCTA", "hard-source DCTA", "known-source DCTA", "SC-ENS", "floored Prob-DCTA", "Source-then-DCTA"],
        "headline": "SC-DCTA reached 0.6497, improving over floored Prob-DCTA 0.6384 while matching hard- and known-source DCTA on development.",
        "files": [
            "docs/SC_DCTA_DEVELOPMENT_PROTOCOL.md",
            "docs/SC_DCTA_DEVELOPMENT_RESULTS.md",
            "results/sc_dcta_metaworld_development.json",
            "scripts/run_sc_dcta_metaworld_development.py",
        ],
    },
    {
        "id": "MW-07",
        "title": "SC-DCTA particle validation",
        "phase": "validation-diagnostic",
        "paper_role": "appendix-implementation-validation",
        "scope": "Numerical validation of support-corrected particle approximation.",
        "primary_condition": "Frozen SC-DCTA particle settings.",
        "methods": ["SC-DCTA particle posterior", "target posterior"],
        "headline": "Implementation-quality validation; use to support fidelity of the approximation, not benchmark superiority.",
        "files": [
            "docs/SC_DCTA_PARTICLE_VALIDATION_PROTOCOL.md",
            "results/sc_dcta_particle_validation.json",
            "scripts/validate_sc_dcta_particles.py",
        ],
    },
    {
        "id": "MW-08",
        "title": "Frozen SC-DCTA held-out evaluation",
        "phase": "held-out-confirmatory",
        "paper_role": "main-paper",
        "scope": "29 untouched Meta-World tasks; 87 primary archives.",
        "primary_condition": "Four replays; 25% missing provenance.",
        "methods": ["SC-DCTA"],
        "headline": "Weighted harmful-memory recall 0.6297 with task-clustered 95% CI [0.5828, 0.6717]; source Brier 0.0208.",
        "files": [
            "docs/SC_DCTA_METAWORLD_EVALUATION_PROTOCOL.md",
            "docs/SC_DCTA_METAWORLD_EVALUATION_RESULTS.md",
            "configs/sc_dcta_metaworld_evaluation_freeze.json",
            "results/sc_dcta_metaworld_evaluation.json",
            "results/prob_dcta_metaworld_test_public_mask_consistent.json",
            "results/prob_dcta_metaworld_test_private_mask_consistent.json",
            "scripts/run_sc_dcta_metaworld_evaluation.py",
        ],
    },
    {
        "id": "MW-09",
        "title": "Corrected-ledger held-out baseline comparison",
        "phase": "held-out-confirmatory",
        "paper_role": "main-paper",
        "scope": "29 untouched tasks; 261 archives; 12 methods; three budgets; three provenance masks.",
        "primary_condition": "Four replays; 25% missing provenance.",
        "methods": ["SC-DCTA", "ENS", "ACIS-Risk", "Random", "Source information gain", "Source-then-DCTA", "hard-source DCTA", "floored Prob-DCTA", "static-risk DCTA", "positive-only DCTA", "known-source DCTA", "full-information hindsight"],
        "headline": "SC-DCTA 0.6297; ENS 0.6198; ACIS-Risk 0.5488; hard-source 0.6335. SC-DCTA significantly beat ACIS-Risk and floored Prob-DCTA, and was statistically tied with ENS and hard-source DCTA.",
        "files": [
            "docs/SC_DCTA_METAWORLD_BASELINE_PROTOCOL.md",
            "docs/SC_DCTA_METAWORLD_BASELINE_RESULTS.md",
            "configs/sc_dcta_metaworld_baseline_freeze.json",
            "results/sc_dcta_metaworld_baselines.json",
            "scripts/run_sc_dcta_metaworld_baselines.py",
        ],
    },
    {
        "id": "MW-10",
        "title": "Recovery mechanism development study",
        "phase": "development-diagnostic",
        "paper_role": "appendix-behavioral-design",
        "scope": "10 development tasks; transition from detection to quarantine-and-fallback recovery.",
        "primary_condition": "Forced harmful-descendant retrieval followed by budgeted audit.",
        "methods": ["SC-DCTA", "ENS", "hard-source DCTA", "floored Prob-DCTA", "Source-then-DCTA", "oracle"],
        "headline": "Established that recovery is mostly limited by localization and that quarantine succeeds in roughly 92-95% of localized development episodes.",
        "files": [
            "docs/SC_DCTA_METAWORLD_RECOVERY_PROTOCOL.md",
            "docs/SC_DCTA_METAWORLD_RECOVERY_DEVELOPMENT_RESULTS.md",
            "docs/SC_DCTA_METAWORLD_FORCED_EXPOSURE_DEVELOPMENT_RESULTS.md",
            "results/metaworld_recovery_development_evaluation.json",
            "results/metaworld_recovery_development_events.json",
            "results/metaworld_recovery_development_smoke_events.json",
            "scripts/run_metaworld_recovery_events.py",
            "scripts/evaluate_metaworld_recovery.py",
        ],
        "globs": ["results/metaworld_recovery_development*_observable.json", "results/metaworld_recovery_development*_private.json", "results/metaworld_forced_exposure_development*_evaluation.json"],
    },
    {
        "id": "MW-11",
        "title": "Frozen 49-task forced-exposure recovery study",
        "phase": "held-out-confirmatory-plus-descriptive",
        "paper_role": "main-paper",
        "scope": "919 harmful-descendant episodes: 182 development, 172 validation, 565 untouched test.",
        "primary_condition": "Budgets 2, 4, and 8; exposed harmful descendant forced to retrieval rank one.",
        "methods": ["SC-DCTA", "ENS-SharedPosterior", "hard-source DCTA", "known-source DCTA", "full-information oracle"],
        "headline": "Untouched-test SC-DCTA task-macro recovery was 26.90%, 51.03%, and 82.11% at budgets 2, 4, and 8; recovery conditional on localization stayed near 95%. SC-DCTA and ENS-SharedPosterior were tied.",
        "files": [
            "docs/SC_DCTA_METAWORLD_FORCED_EXPOSURE_ALL49_RESULTS.md",
            "configs/metaworld_forced_exposure_freeze_v1.json",
            "results/metaworld_forced_exposure_all49_aggregate.json",
            "results/sc_dcta_metaworld_validation_crossfit.json",
            "scripts/aggregate_metaworld_forced_exposure.py",
            "scripts/evaluate_metaworld_forced_exposure.py",
        ],
        "globs": ["results/metaworld_forced_exposure_validation*_evaluation.json", "results/metaworld_forced_exposure_test*_evaluation.json", "results/metaworld_recovery_validation*_observable.json", "results/metaworld_recovery_validation*_private.json", "results/metaworld_recovery_test*_observable.json", "results/metaworld_recovery_test*_private.json"],
    },
    {
        "id": "MW-12",
        "title": "Task-scoped quarantine utility and audit-cost study",
        "phase": "confirmatory-reanalysis",
        "paper_role": "main-paper-or-appendix",
        "scope": "49 tasks; 147 primary archives; 3,087 candidate-memory instances.",
        "primary_condition": "25% missing provenance; budgets 2, 4, and 8.",
        "methods": ["SC-DCTA", "ENS-SharedPosterior", "hard-source DCTA", "Source-then-DCTA", "floored Prob-DCTA", "known-source DCTA", "oracle"],
        "headline": "At budget four SC-DCTA made 504 harmful and 84 benign replay calls (85.7% audit yield), retained all 2,168 target-benign memories, and avoided cross-context deletion by task-scoped quarantine.",
        "files": [
            "docs/SC_DCTA_METAWORLD_QUARANTINE_UTILITY_PROTOCOL.md",
            "docs/SC_DCTA_METAWORLD_QUARANTINE_UTILITY_RESULTS.md",
            "results/metaworld_quarantine_utility_all49.json",
            "scripts/analyze_metaworld_quarantine_utility.py",
        ],
    },
    {
        "id": "MW-13",
        "title": "Missing-provenance recovery robustness",
        "phase": "held-out-confirmatory",
        "paper_role": "main-paper-limitation",
        "scope": "All 49 tasks across 27 split/mask/budget cells; primary inference on 565 untouched-test episodes.",
        "primary_condition": "Four replays; compare 0% with 50% missing provenance.",
        "methods": ["SC-DCTA", "ENS-SharedPosterior", "hard-source DCTA"],
        "headline": "On held-out test, SC-DCTA recovery declined 3.15 points [1.12, 5.57] from complete to 50%-missing provenance; ENS was more robust by 3.09 points at budget four.",
        "files": [
            "docs/SC_DCTA_METAWORLD_PROVENANCE_RECOVERY_PROTOCOL.md",
            "docs/SC_DCTA_METAWORLD_PROVENANCE_RECOVERY_RESULTS.md",
            "configs/metaworld_provenance_recovery_freeze_v1.json",
            "results/metaworld_provenance_recovery_all_masks.json",
            "scripts/aggregate_metaworld_provenance_recovery.py",
        ],
    },
    {
        "id": "MW-14",
        "title": "Missing-provenance failure-strata diagnostic",
        "phase": "post-hoc-held-out-diagnostic",
        "paper_role": "appendix-limitation-mechanism",
        "scope": "565 paired held-out harmful-descendant episodes at complete and 50%-missing provenance.",
        "primary_condition": "Four replays; no method modification or rerun.",
        "methods": ["SC-DCTA", "ENS-SharedPosterior"],
        "headline": "Loss concentrated in single-source ancestry (-9.02 points) and small cascades (-9.95 points), not deep descendants; the limitation is best described as insufficient lineage-evidence redundancy.",
        "files": [
            "docs/SC_DCTA_METAWORLD_FAILURE_STRATA_PROTOCOL.md",
            "docs/SC_DCTA_METAWORLD_FAILURE_STRATA_RESULTS.md",
            "results/metaworld_failure_strata.json",
            "scripts/analyze_metaworld_failure_strata.py",
        ],
    },
    {
        "id": "MW-15",
        "title": "Frozen task-matched archive-scalability stress test",
        "phase": "frozen-post-hoc-stress-test",
        "paper_role": "main-paper-scalability-and-limitation",
        "scope": "49 Meta-World tasks; nested 21/50/100/200-memory archives; 31,752 audit rows and 66,168 behavioral-recovery rows.",
        "primary_condition": "Four replays; 25% missing provenance; 29-task evaluation panel is disjoint from fit but previously inspected.",
        "methods": ["SC-DCTA", "ENS", "hard-source DCTA", "ACIS-Risk", "floored Prob-DCTA", "deterministic random"],
        "headline": "At 200 memories SC-DCTA retained 0.5487 recall and 0.4515 recovery, but trailed ENS by 0.0449 recall and 0.0468 recovery; acquisition time scaled 275.9x from 21 to 200 memories under shared load.",
        "files": [
            "docs/SC_DCTA_METAWORLD_SCALABILITY_PROTOCOL.md",
            "docs/SC_DCTA_METAWORLD_SCALABILITY_RESULTS.md",
            "configs/metaworld_scalability_freeze_v1.json",
            "scripts/run_metaworld_scalability.py",
            "scripts/aggregate_metaworld_scalability.py",
            "scripts/evaluate_metaworld_scalability_recovery.py",
            "scripts/analyze_metaworld_scalability.py",
            "scripts/verify_metaworld_scalability.py",
            "src/mcx/metaworld_scalability.py",
            "tests/test_metaworld_scalability.py",
            "tests/test_metaworld_scalability_verification.py",
        ],
        "globs": ["results/metaworld_scalability*.json"],
    },
]


FINAL_BASELINES = [
    {"method": "Hard-source DCTA", "role": "Ablation", "recall": 0.6335, "audit_yield": 0.8736},
    {"method": "SC-DCTA", "role": "Proposed", "recall": 0.6297, "audit_yield": 0.8764},
    {"method": "Positive-only DCTA", "role": "Ablation", "recall": 0.6270, "audit_yield": 0.8649},
    {"method": "ENS", "role": "Active-search baseline", "recall": 0.6198, "audit_yield": 0.8678},
    {"method": "Floored Prob-DCTA", "role": "Ablation", "recall": 0.6149, "audit_yield": 0.8621},
    {"method": "Static-risk DCTA", "role": "Ablation", "recall": 0.6080, "audit_yield": 0.8534},
    {"method": "Source-then-DCTA", "role": "Sequential baseline", "recall": 0.5948, "audit_yield": 0.8132},
    {"method": "ACIS-Risk", "role": "External baseline", "recall": 0.5488, "audit_yield": 0.7816},
    {"method": "Source information gain", "role": "Sequential baseline", "recall": 0.2037, "audit_yield": 0.3017},
    {"method": "Random", "role": "Baseline", "recall": 0.1834, "audit_yield": 0.2989},
    {"method": "Known-source DCTA", "role": "Information oracle", "recall": 0.6560, "audit_yield": 0.8994},
    {"method": "Full-information hindsight", "role": "Ceiling", "recall": 0.7117, "audit_yield": 0.9454},
]


SCALABILITY_HEADLINE = [
    {"archive_size": 21, "sc_recall": 0.6297, "ens_recall": 0.6198, "sc_recovery": 0.5103, "ens_recovery": 0.5069},
    {"archive_size": 50, "sc_recall": 0.6090, "ens_recall": 0.6149, "sc_recovery": 0.5020, "ens_recovery": 0.5110},
    {"archive_size": 100, "sc_recall": 0.5948, "ens_recall": 0.6041, "sc_recovery": 0.4939, "ens_recovery": 0.5065},
    {"archive_size": 200, "sc_recall": 0.5487, "ens_recall": 0.5935, "sc_recovery": 0.4515, "ens_recovery": 0.4983},
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve_files(study: dict) -> list[str]:
    paths = set(study.get("files", []))
    for pattern in study.get("globs", []):
        paths.update(p.relative_to(ROOT).as_posix() for p in ROOT.glob(pattern))
    return sorted(paths)


def build_ledger() -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tracked: set[str] = set()
    rows = []
    missing = []
    for source in STUDIES:
        study = {k: v for k, v in source.items() if k not in {"files", "globs"}}
        evidence = []
        for rel in resolve_files(source):
            tracked.add(rel)
            path = ROOT / rel
            item = {"path": rel, "present": path.is_file()}
            if path.is_file():
                item.update({"bytes": path.stat().st_size, "sha256": digest(path)})
            else:
                missing.append(rel)
            evidence.append(item)
        study["evidence"] = evidence
        rows.append(study)

    discoverable = set()
    for path in (ROOT / "results").glob("*.json"):
        name = path.name.lower()
        if path.resolve() == JSON_OUT.resolve():
            continue
        if "metaworld" in name or name.startswith("sc_dcta_") or name.startswith("confidence_aware_dcta_metaworld"):
            discoverable.add(path.relative_to(ROOT).as_posix())
    unassigned = sorted(discoverable - tracked)
    return {
        "schema_version": 1,
        "generated_at": now,
        "scope": "Meta-World DCTA-family experiments and baselines",
        "status_definitions": {
            "main-paper": "Frozen evidence eligible for the principal Meta-World results.",
            "main-paper-limitation": "Frozen negative or robustness evidence that must qualify the principal claim.",
            "appendix": "Useful mechanism, method-development, or implementation evidence; not a primary held-out claim.",
            "historical-only": "Exploratory or superseded evidence retained for audit but not presented as final performance.",
            "main-paper-scalability-and-limitation": "Frozen post-hoc robustness evidence on a previously inspected evaluation panel; report with that qualification.",
        },
        "primary_reporting_boundary": {
            "method": "SC-DCTA",
            "test_tasks": 29,
            "primary_archives": 87,
            "primary_replay_budget": 4,
            "primary_missing_provenance": 0.25,
            "primary_metric": "weighted harmful-memory recall",
            "behavioral_test_episodes": 565,
            "descriptive_all_tasks": 49,
            "warning": "The 49-task aggregate is descriptive because development and validation tasks informed method construction; the 29-task test result is confirmatory.",
        },
        "studies": rows,
        "final_baseline_table": FINAL_BASELINES,
        "scalability_headline": SCALABILITY_HEADLINE,
        "integrity": {
            "study_count": len(rows),
            "tracked_file_count": len(tracked),
            "missing_files": sorted(set(missing)),
            "discoverable_result_files_not_assigned": unassigned,
        },
    }


def markdown(ledger: dict) -> str:
    lines = [
        "# Meta-World DCTA experiment ledger",
        "",
        f"Generated: `{ledger['generated_at']}`",
        "",
        "## Reporting boundary",
        "",
        "The definitive Meta-World method is **SC-DCTA**. Its confirmatory benchmark claim uses **29 untouched test tasks**, **87 primary archives**, **four replays**, **25% missing provenance**, and **weighted harmful-memory recall**. Results pooled across all 49 tasks are descriptive because development and validation tasks informed method construction.",
        "",
        "Early Prob-DCTA, confidence-aware, oracle, and calibration studies remain preserved below, but they must not be substituted for the final corrected-ledger SC-DCTA evaluation.",
        "",
        "## Publication-ready headline results",
        "",
        "| Evidence | Frozen result | Intended use |",
        "|---|---|---|",
        "| Held-out method performance | SC-DCTA recall 0.6297; task-clustered 95% CI [0.5828, 0.6717] | Main paper |",
        "| Held-out external comparison | SC-DCTA 0.6297 vs ACIS-Risk 0.5488; difference +0.0809 [0.0389, 0.1226] | Main paper |",
        "| Held-out active-search comparison | SC-DCTA 0.6297 vs ENS 0.6198; difference +0.0099 [-0.0257, 0.0445] | Main paper; parity, not superiority |",
        "| Held-out hard-source ablation | SC-DCTA 0.6297 vs hard-source 0.6335; difference -0.0038 [-0.0264, 0.0150] | Main paper; statistically tied |",
        "| Behavioral recovery | Test task-macro recovery 26.90%, 51.03%, 82.11% at budgets 2, 4, 8 | Main paper |",
        "| Post-localization remediation | Recovery conditional on localization was approximately 95% on held-out test | Main paper |",
        "| Missing-provenance limitation | At budget four, SC-DCTA changed -3.15 pp [ -5.57, -1.12 ] from 0% to 50% missing provenance | Main limitation |",
        "| Limitation mechanism | Loss concentrated in single-source ancestry (-9.02 pp) and small cascades (-9.95 pp) | Post-hoc diagnostic; appendix |",
        "| Quarantine utility | Budget-four audit yield 85.7%; all 2,168 target-benign memories retained in deterministic benchmark | Main paper or appendix with stochasticity caveat |",
        "| Archive scalability | At 200 memories SC-DCTA recall 0.5487 and recovery 0.4515; ENS 0.5935 and 0.4983 | Frozen post-hoc stress test; main scalability limitation |",
        "",
        "## Final corrected-ledger baseline table",
        "",
        "Four replays, 25% missing provenance, 29 untouched tasks, 87 archives. Privileged-information rows are references, not competitors.",
        "",
        "| Method | Role | Weighted recall | Audit yield |",
        "|---|---|---:|---:|",
    ]
    for row in FINAL_BASELINES:
        lines.append(f"| {row['method']} | {row['role']} | {row['recall']:.4f} | {row['audit_yield']:.4f} |")
    lines.extend(["", "## Complete study registry", ""])
    for study in ledger["studies"]:
        lines.extend([
            f"### {study['id']} — {study['title']}",
            "",
            f"- Phase: `{study['phase']}`",
            f"- Paper role: `{study['paper_role']}`",
            f"- Scope: {study['scope']}",
            f"- Primary condition: {study['primary_condition']}",
            f"- Methods/references: {', '.join(study['methods'])}",
            f"- Headline: {study['headline']}",
            "- Evidence:",
            "",
        ])
        for item in study["evidence"]:
            if item["present"]:
                lines.append(f"  - `{item['path']}` — SHA-256 `{item['sha256']}`")
            else:
                lines.append(f"  - **MISSING:** `{item['path']}`")
        lines.append("")
    integrity = ledger["integrity"]
    lines.extend([
        "## Integrity audit",
        "",
        f"- Registered studies: {integrity['study_count']}",
        f"- Tracked evidence files: {integrity['tracked_file_count']}",
        f"- Missing registered files: {len(integrity['missing_files'])}",
        f"- Discoverable Meta-World/DCTA result files not yet assigned: {len(integrity['discoverable_result_files_not_assigned'])}",
        "",
    ])
    if integrity["missing_files"]:
        lines.append("Missing files: " + ", ".join(f"`{p}`" for p in integrity["missing_files"]))
        lines.append("")
    if integrity["discoverable_result_files_not_assigned"]:
        lines.append("Unassigned result artifacts (retain; classify before paper submission):")
        lines.append("")
        lines.extend(f"- `{p}`" for p in integrity["discoverable_result_files_not_assigned"])
        lines.append("")
    lines.extend([
        "## Maintenance rule",
        "",
        "Every new Meta-World experiment must receive a study ID, phase, paper role, frozen condition, method list, one-sentence result, and links to its protocol/configuration/raw output/analysis code. Re-run `python scripts/build_metaworld_dcta_experiment_ledger.py` after adding it; changed file hashes make later mutations visible.",
        "",
    ])
    return "\n".join(lines)


def report_artifact(ledger: dict) -> dict:
    studies = [
        {
            "study_id": s["id"],
            "study": s["title"],
            "phase": s["phase"],
            "paper_role": s["paper_role"],
            "scope": s["scope"],
            "primary_condition": s["primary_condition"],
            "headline": s["headline"],
            "evidence_files": len(s["evidence"]),
        }
        for s in ledger["studies"]
    ]
    headline = [{
        "registered_studies": ledger["integrity"]["study_count"],
        "tracked_files": ledger["integrity"]["tracked_file_count"],
        "missing_files": len(ledger["integrity"]["missing_files"]),
        "unassigned_files": len(ledger["integrity"]["discoverable_result_files_not_assigned"]),
    }]
    competitive_baselines = [row for row in FINAL_BASELINES if row["role"] not in {"Information oracle", "Ceiling"}]
    snapshot_path = "reports/metaworld_dcta_experiment_ledger/report_snapshot.sqlite"
    sources = [
        {"id": "ledger", "label": "Reviewed Meta-World DCTA study registry", "path": snapshot_path, "query": {"engine": "sqlite", "sql": "SELECT study_id, study, phase, paper_role, scope, primary_condition, headline, evidence_files FROM study_registry ORDER BY study_id", "description": "Returns every registered Meta-World DCTA study and its publication role.", "tables_used": ["study_registry"], "executed_at": ledger["generated_at"], "metric_definitions": ["Evidence files count the registered protocol, configuration, result, analysis, implementation, and test artifacts linked to each study."]}},
        {"id": "baseline", "label": "Reviewed frozen corrected-ledger baseline table", "path": snapshot_path, "query": {"engine": "sqlite", "sql": "SELECT method, role, recall, audit_yield FROM final_baselines ORDER BY recall DESC", "description": "Returns the frozen four-replay, 25%-missing-provenance comparison on 29 untouched Meta-World tasks.", "tables_used": ["final_baselines"], "executed_at": ledger["generated_at"], "filters": ["29 untouched tasks", "87 archives", "four replays", "25% missing provenance"], "metric_definitions": ["Weighted recall is realized harmful-memory mass found within the replay budget divided by total realized harmful-memory mass.", "Audit yield is harmful replay calls divided by all replay calls."]}},
        {"id": "recovery", "label": "Reviewed frozen forced-exposure recovery summary", "path": snapshot_path, "query": {"engine": "sqlite", "sql": "SELECT budget, task_macro_recovery, conditional_recovery FROM recovery_headline ORDER BY budget", "description": "Returns the untouched-test SC-DCTA recovery curve.", "tables_used": ["recovery_headline"], "executed_at": ledger["generated_at"], "filters": ["29 untouched tasks", "565 harmful-descendant episodes"], "metric_definitions": ["Task-macro recovery averages episode recovery within task and then averages tasks equally.", "Conditional recovery is recovery among episodes where the harmful descendant was localized."]}},
        {"id": "provenance", "label": "Reviewed missing-provenance limitation summary", "path": snapshot_path, "query": {"engine": "sqlite", "sql": "SELECT budget, sc_change_pp, ci_low_pp, ci_high_pp, sc_minus_ens_pp FROM provenance_headline ORDER BY budget", "description": "Returns held-out recovery change from complete to 50%-missing provenance.", "tables_used": ["provenance_headline"], "executed_at": ledger["generated_at"], "filters": ["29 untouched tasks", "paired 0% versus 50% provenance missingness"], "metric_definitions": ["Change is the task-macro recovery difference in percentage points between 50% and 0% missing provenance."]}},
        {"id": "scalability", "label": "Reviewed frozen archive-scalability summary", "path": snapshot_path, "query": {"engine": "sqlite", "sql": "SELECT archive_size, sc_recall, ens_recall, sc_recovery, ens_recovery FROM scalability_headline ORDER BY archive_size", "description": "Returns the primary four-replay, 25%-missing-provenance scalability curve on the 29-task evaluation panel.", "tables_used": ["scalability_headline"], "executed_at": ledger["generated_at"], "filters": ["29 tasks disjoint from fit but previously inspected", "four replays", "25% missing provenance"], "metric_definitions": ["Recall is weighted harmful-memory recall.", "Recovery is task-macro behavioral recovery under forced harmful-descendant exposure."]}},
    ]
    manifest = {
        "version": 1,
        "surface": "report",
        "title": "Meta-World DCTA Experiment Ledger",
        "description": "Publication-oriented inventory of DCTA-family experiments, baselines, claims, limitations, and reproducibility artifacts.",
        "generatedAt": ledger["generated_at"],
        "cards": [],
        "charts": [
            {"id": "baseline_recall", "title": "Weighted harmful-memory recall by method", "subtitle": "Four replays, 25% missing provenance, 29 untouched Meta-World tasks and 87 archives.", "type": "bar", "dataset": "competitive_baselines", "sourceId": "baseline", "encodings": {"x": {"field": "method", "type": "ordinal", "label": "Method"}, "y": {"field": "recall", "type": "quantitative", "label": "Weighted harmful-memory recall", "format": "percent"}}, "yAxisTitle": "Weighted harmful-memory recall", "valueFormat": "percent", "layout": "full"},
        ],
        "tables": [
            {"id": "final_baselines", "title": "Frozen held-out Meta-World baseline comparison", "subtitle": "Four replays, 25% missing provenance, 29 untouched tasks and 87 archives.", "dataset": "final_baselines", "sourceId": "baseline", "density": "spacious", "layout": "full", "defaultSort": {"field": "recall", "direction": "desc"}, "columns": [{"field": "method", "label": "Method", "type": "text"}, {"field": "role", "label": "Role", "type": "text"}, {"field": "recall", "label": "Weighted recall", "format": "percent"}, {"field": "audit_yield", "label": "Audit yield", "format": "percent"}]},
            {"id": "study_registry", "title": "Complete Meta-World study registry", "subtitle": "Exact lookup table distinguishing final claims from development, diagnostics, and superseded method history.", "dataset": "studies", "sourceId": "ledger", "density": "dense", "layout": "full", "defaultSort": {"field": "study_id", "direction": "asc"}, "columns": [{"field": "study_id", "label": "ID", "type": "text"}, {"field": "study", "label": "Study", "type": "text"}, {"field": "phase", "label": "Phase", "type": "text"}, {"field": "paper_role", "label": "Paper role", "type": "text"}, {"field": "evidence_files", "label": "Evidence files", "format": "number"}, {"field": "headline", "label": "Stored result", "type": "text"}]},
            {"id": "scalability", "title": "Frozen Meta-World archive-scalability stress test", "subtitle": "Four replays and 25% missing provenance; evaluation panel disjoint from fit but previously inspected.", "dataset": "scalability_headline", "sourceId": "scalability", "density": "spacious", "layout": "full", "defaultSort": {"field": "archive_size", "direction": "asc"}, "columns": [{"field": "archive_size", "label": "Memories", "format": "number"}, {"field": "sc_recall", "label": "SC-DCTA recall", "format": "percent"}, {"field": "ens_recall", "label": "ENS recall", "format": "percent"}, {"field": "sc_recovery", "label": "SC-DCTA recovery", "format": "percent"}, {"field": "ens_recovery", "label": "ENS recovery", "format": "percent"}]},
        ],
        "sources": sources,
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# Meta-World DCTA Experiment Ledger"},
            {"id": "summary", "type": "markdown", "sourceId": "ledger", "body": "## The Meta-World evidence is preserved and now has a single reporting boundary\n\nThe final method is **SC-DCTA**, evaluated confirmatorily on **29 untouched Meta-World tasks**. The principal condition is **four replays with 25% missing provenance**. Earlier Prob-DCTA and confidence-aware experiments remain available for audit but are explicitly marked as development, negative, or superseded evidence. This prevents exploratory results from being mistaken for final paper claims."},
            {"id": "inventory_status", "type": "markdown", "sourceId": "ledger", "body": f"The inventory contains **{ledger['integrity']['study_count']} registered study groups** and **{ledger['integrity']['tracked_file_count']} hashed evidence files**, with **{len(ledger['integrity']['missing_files'])} missing registered files** and **{len(ledger['integrity']['discoverable_result_files_not_assigned'])} unassigned discoverable Meta-World/DCTA result artifacts**."},
            {"id": "final_heading", "type": "markdown", "sourceId": "baseline", "body": "## The corrected-ledger comparison is the definitive performance table\n\nSC-DCTA reached **62.97% weighted recall**, significantly exceeding ACIS-Risk and the old floored Prob-DCTA implementation. It was statistically tied with ENS and hard-source DCTA. Known-source and hindsight rows use privileged information and must be described as references rather than competitors."},
            {"id": "baseline_chart", "type": "chart", "chartId": "baseline_recall", "layout": "full"},
            {"id": "baseline_table", "type": "table", "tableId": "final_baselines", "layout": "full"},
            {"id": "scope", "type": "markdown", "sourceId": "ledger", "body": "## Reporting units and claim boundaries\n\nThe confirmatory performance unit is the task cluster over 29 untouched tasks and 87 primary archives. The behavioral recovery study contains 565 held-out harmful-descendant episodes. Aggregates over all 49 tasks are descriptive because the 10 development and 10 validation tasks informed method construction. Weighted harmful-memory recall measures how much realized downstream harm is found within the physical replay budget; behavioral recovery measures whether quarantine and fallback restore task success after a harmful memory is forced into retrieval."},
            {"id": "registry_heading", "type": "markdown", "sourceId": "ledger", "body": "## Every experiment has a declared publication role\n\nThe registry preserves positive, negative, and superseded results. Main-paper rows provide the final benchmark, behavioral recovery, utility, and robustness evidence. Appendix rows explain method development or mechanisms. Historical rows document how the method evolved but should not be cited as current SC-DCTA performance."},
            {"id": "registry_table", "type": "table", "tableId": "study_registry", "layout": "full"},
            {"id": "limitations", "type": "markdown", "sourceId": "provenance", "body": "## Missing provenance is a documented limitation, not an omitted result\n\nAt four replays, held-out SC-DCTA recovery declined by **3.15 percentage points** when provenance missingness rose from 0% to 50%. A post-hoc diagnostic localized the loss to single-source ancestry and small cascades, suggesting insufficient lineage-evidence redundancy rather than cascade depth. ENS-SharedPosterior was more robust in the primary four-replay contrast. These results qualify the method's claim and must remain visible."},
            {"id": "scalability_heading", "type": "markdown", "sourceId": "scalability", "body": "## Archive growth exposes a real accuracy-cost boundary\n\nWith the replay budget fixed at four, SC-DCTA retained **54.87% recall** and **45.15% recovery** at 200 task-matched memories. It remained far above ACIS-Risk and floored Prob-DCTA but trailed ENS at the largest scale. Conditional recovery remained near 97%, identifying localization and acquisition cost—not remediation after localization—as the principal scaling limitation. This is a frozen post-hoc stress test because the evaluation panel had been inspected previously."},
            {"id": "scalability_table", "type": "table", "tableId": "scalability", "layout": "full"},
            {"id": "methodology", "type": "markdown", "sourceId": "ledger", "body": "## Reproducibility is file-level and mutation-visible\n\nEach study links its protocol, frozen configuration, raw or aggregate output, analysis code, and tests when available. Every registered file receives a SHA-256 digest in the machine-readable and Markdown ledgers. Regenerating the ledger after a file changes exposes the mutation. The HTML report intentionally uses exact tables instead of decorative charts because its primary purpose is result lookup and auditability."},
            {"id": "next", "type": "markdown", "body": "## The Meta-World empirical package is frozen\n\nThe principal benchmark, baselines, forced-exposure recovery, quarantine utility, missing-provenance robustness, failure strata, and archive-scalability stress test are now registered. No method change should follow from the already inspected Meta-World evaluation panel. The next paper component is the rigorous theory specification; any theory-motivated new algorithm must be evaluated on a new domain or archive population."},
            {"id": "questions", "type": "markdown", "body": "## Open items before paper submission\n\n- Freeze the final theory statement so empirical claims use the same objects and assumptions.\n- Decide whether a faithful end-to-end ENS-kNN implementation is necessary after the theory fixes the precise competitor class; the current ENS shared-posterior result is a strong mechanism control.\n- Estimate false quarantine under stochastic or fresh-seed replay in a future independent domain; the current zero-false-quarantine result uses deterministic stored outcomes.\n- Obtain an independent second-domain evaluation without tuning SC-DCTA on that domain's test panel."},
        ],
    }
    return {"surface": "report", "manifest": manifest, "snapshot": {"version": 1, "generatedAt": ledger["generated_at"], "status": "ready", "datasets": {"headline": headline, "final_baselines": FINAL_BASELINES, "competitive_baselines": competitive_baselines, "studies": studies, "scalability_headline": SCALABILITY_HEADLINE}}, "sources": sources}


def write_report_snapshot(ledger: dict) -> None:
    studies = [
        (
            s["id"], s["title"], s["phase"], s["paper_role"], s["scope"],
            s["primary_condition"], s["headline"], len(s["evidence"]),
        )
        for s in ledger["studies"]
    ]
    if SNAPSHOT_OUT.exists():
        SNAPSHOT_OUT.unlink()
    with sqlite3.connect(SNAPSHOT_OUT) as connection:
        connection.execute("CREATE TABLE study_registry (study_id TEXT PRIMARY KEY, study TEXT, phase TEXT, paper_role TEXT, scope TEXT, primary_condition TEXT, headline TEXT, evidence_files INTEGER)")
        connection.executemany("INSERT INTO study_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?)", studies)
        connection.execute("CREATE TABLE final_baselines (method TEXT PRIMARY KEY, role TEXT, recall REAL, audit_yield REAL)")
        connection.executemany("INSERT INTO final_baselines VALUES (:method, :role, :recall, :audit_yield)", FINAL_BASELINES)
        connection.execute("CREATE TABLE recovery_headline (budget INTEGER PRIMARY KEY, task_macro_recovery REAL, conditional_recovery REAL)")
        connection.executemany("INSERT INTO recovery_headline VALUES (?, ?, ?)", [(2, 0.2690, 0.9500), (4, 0.5103, 0.9475), (8, 0.8211, 0.9570)])
        connection.execute("CREATE TABLE provenance_headline (budget INTEGER PRIMARY KEY, sc_change_pp REAL, ci_low_pp REAL, ci_high_pp REAL, sc_minus_ens_pp REAL)")
        connection.executemany("INSERT INTO provenance_headline VALUES (?, ?, ?, ?, ?)", [(2, -2.47, -4.41, -0.72, -0.42), (4, -3.15, -5.57, -1.12, -3.09), (8, -2.59, -5.03, -0.53, -0.45)])
        connection.execute("CREATE TABLE scalability_headline (archive_size INTEGER PRIMARY KEY, sc_recall REAL, ens_recall REAL, sc_recovery REAL, ens_recovery REAL)")
        connection.executemany("INSERT INTO scalability_headline VALUES (:archive_size, :sc_recall, :ens_recall, :sc_recovery, :ens_recovery)", SCALABILITY_HEADLINE)


def main() -> None:
    ledger = build_ledger()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    DOC_OUT.write_text(markdown(ledger), encoding="utf-8")
    write_report_snapshot(ledger)
    ARTIFACT_OUT.write_text(json.dumps(report_artifact(ledger), indent=2) + "\n", encoding="utf-8")
    NOTES_OUT.write_text(
        "# Source and QA notes\n\n"
        "Audience: technical. Delivery: portable HTML.\n\n"
        "Chart map: the final-performance section asks how budget-matched methods compare under the one frozen held-out condition; it uses a single-root categorical bar chart with method on the horizontal axis and weighted recall on the quantitative axis. "
        "Exact tables remain primary for audit. The remaining studies mix non-comparable phases, splits, metrics, and purposes, so charting them together would imply a false common scale.\n\n"
        "Required technical-report roles map to: summary, final baseline evidence, scope/definitions, study registry/method history, limitations, reproducibility methodology, next steps, and open items.\n",
        encoding="utf-8",
    )
    print(json.dumps(ledger["integrity"], indent=2))


if __name__ == "__main__":
    main()
