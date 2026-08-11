"""Independent integrity checks for the frozen LIBERO-90 external study."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def sha256(name: str) -> str:
    return hashlib.sha256((RESULTS / name).read_bytes()).hexdigest()


def recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(recursive_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(recursive_keys(v) for v in value)) if value else set()
    return set()


def main() -> None:
    screen = load("memory_libero_external_v1_screen.json")
    generation = load("memory_libero_external_v1_generation.json")
    public = load("memory_libero_external_v1_public.json")
    private = load("memory_libero_external_v1_private_labels.json")
    evaluation = load("memory_libero_external_v1_evaluation.json")

    checks: dict[str, bool] = {}
    checks["screen_complete_90_tasks"] = screen["complete"] and screen["task_count"] == 90
    checks["screen_gate_67_verified"] = screen["feasibility_gate_passed"] and screen["verified_pair_count"] == 67
    checks["generation_complete_67"] = generation["complete"] and len(generation["archives"]) == 67

    pub = {a["archive_id"]: a for a in public["archives"]}
    prv = {a["archive_id"]: a for a in private["archives"]}
    checks["unique_public_ids"] = len(pub) == len(public["archives"]) == 67
    checks["unique_private_ids"] = len(prv) == len(private["archives"]) == 67
    checks["public_private_exact_join"] = pub.keys() == prv.keys()
    checks["evaluator_hash_frozen_before_join"] = (
        public["evaluator_sha256_before_label_join"]
        == private["evaluator_sha256_before_label_join"]
        == "de0b9a2f262f92f2b734d077745a92830574d90a15c9666c64e8bfa82b0c7394"
    )
    checks["evaluation_input_hashes_match"] = (
        evaluation["public_sha256"] == sha256("memory_libero_external_v1_public.json")
        and evaluation["private_sha256"] == sha256("memory_libero_external_v1_private_labels.json")
    )
    forbidden = {"affected_ids", "affected_count", "counterfactual", "counterfactuals", "is_affected"}
    checks["no_private_label_keys_in_public"] = not (recursive_keys(public) & forbidden)

    archive_shape_ok = True
    positive_ok = True
    for archive_id, archive in pub.items():
        candidates = archive["candidate_ids"]
        known = set(candidates) | {archive["source_id"]}
        times = archive["created_at"]
        archive_shape_ok &= (
            len(candidates) == len(set(candidates)) == 18
            and archive["source_id"] not in candidates
            and set(archive["memories"]) == known
            and set(times) == known
            and all(parent in known and child in known and times[parent] < times[child]
                    for parent, child in archive["formation_edges"])
            and set(prv[archive_id]["affected_ids"]).issubset(candidates)
            and prv[archive_id]["affected_count"] == len(prv[archive_id]["affected_ids"])
        )
        positive_ok &= prv[archive_id]["affected_count"] > 0
    checks["archive_graphs_are_18_node_dags"] = archive_shape_ok
    checks["all_archives_have_positive_truth"] = positive_ok

    rows = evaluation["rows"]
    methods = set(evaluation["summary"])
    budgets = set(evaluation["budgets"])
    row_keys = [(r["archive_id"], r["budget"], r["method"]) for r in rows]
    checks["complete_method_budget_grid"] = (
        len(rows) == 67 * len(methods) * len(budgets)
        and len(row_keys) == len(set(row_keys))
        and set(r["archive_id"] for r in rows) == set(pub)
        and set(r["method"] for r in rows) == methods
        and set(r["budget"] for r in rows) == budgets
    )
    checks["metrics_in_valid_ranges"] = all(
        0 <= r["recall"] <= 1
        and 0 <= r["deep_recall"] <= 1
        and 0 <= r["residual_invalid_exposure"] <= 1
        and len(r["replayed_ids"]) == len(set(r["replayed_ids"]))
        for r in rows
    )
    checks["diagnostic_world_enumeration_complete"] = (
        len(evaluation["diagnostics"]) == 67
        and all(d["world_count"] == 6940 and d["truth_support"] for d in evaluation["diagnostics"])
    )
    checks["evaluation_declared_complete"] = evaluation["complete"]

    primary = evaluation["primary_difference"]
    budget_effects = {}
    for budget in sorted(budgets):
        indexed = {
            method: {r["archive_id"]: r["recall"] for r in rows if r["budget"] == budget and r["method"] == method}
            for method in ("dcta_risk_local_v1", "acis_risk")
        }
        differences = [indexed["dcta_risk_local_v1"][a] - indexed["acis_risk"][a] for a in sorted(pub)]
        budget_effects[str(budget)] = {
            "mean_recall_difference": sum(differences) / len(differences),
            "wins": sum(d > 0 for d in differences),
            "ties": sum(d == 0 for d in differences),
            "losses": sum(d < 0 for d in differences),
        }
    checks["primary_difference_recomputed"] = abs(
        budget_effects[str(evaluation["primary_budget"])]["mean_recall_difference"] - primary["estimate"]
    ) < 1e-12

    strata = Counter()
    for diagnostic in evaluation["diagnostics"]:
        for key in ("negative_screening", "deep_cascade", "affected_merge"):
            if diagnostic[key]:
                strata[key] += 1

    limitations = []
    if strata["negative_screening"] == 67:
        limitations.append("All 67 archives satisfy the negative-screening stratum; the predeclared outside-stratum contrast is not identifiable.")
    if budget_effects["2"]["mean_recall_difference"] < 0:
        limitations.append("DCTA-Risk-Local v1 is worse than ACIS-Risk at replay budget 2; competitiveness is budget-dependent.")
    limitations.append("MemoRepair scope recall is not budget-equivalent: it republishes all 18 candidates and therefore remains a separate scope analysis.")

    output = {
        "protocol": "memory-libero/external-validation-v1/integrity-audit",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": all(checks.values()),
        "checks": checks,
        "counts": {
            "screened_tasks": screen["task_count"],
            "verified_archives": len(pub),
            "evaluation_rows": len(rows),
            "methods": len(methods),
            "budgets": len(budgets),
            "strata": dict(strata),
        },
        "budget_effects_dcta_minus_acis": budget_effects,
        "primary_difference": primary,
        "limitations": limitations,
    }
    target = RESULTS / "memory_libero_external_v1_validation.json"
    target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
