"""Integrity audit for the post-hoc active-search LIBERO extension."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--prior-evaluation", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, required=True)
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--active-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = json.loads(args.result.read_text(encoding="utf-8"))
    prior = json.loads(args.prior_evaluation.read_text(encoding="utf-8"))
    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    rows = result["rows"]
    methods = set(result["methods"])
    budgets = set(result["budgets"])
    archives = set(row["archive_id"] for row in rows)
    keys = [(row["archive_id"], row["budget"], row["method"]) for row in rows]
    checks = {
        "declared_complete_posthoc": result["complete"] and result["posthoc_extension"],
        "frozen_evaluator_hash": (
            result["evaluator_sha256"] == sha256(args.evaluator)
            == freeze["evaluator_sha256"]
        ),
        "frozen_implementation_hash": (
            result["implementation_sha256"] == sha256(args.implementation)
            == freeze["active_search_implementation_sha256"]
        ),
        "frozen_config_hash": (
            result["active_config_sha256"] == sha256(args.active_config)
            == freeze["active_search_config_sha256"]
        ),
        "prior_evaluation_hash": result["prior_evaluation_sha256"] == sha256(args.prior_evaluation),
        "complete_unique_grid": (
            len(archives) == result["archive_count"] == 67
            and len(rows) == 67 * len(methods) * len(budgets)
            and len(keys) == len(set(keys))
        ),
        "valid_metrics": all(
            0.0 <= row["recall"] <= 1.0
            and 0.0 <= row["deep_recall"] <= 1.0
            and 0.0 <= row["audit_yield"] <= 1.0
            and 0.0 <= row["residual_invalid_exposure"] <= 1.0
            and len(row["replayed_ids"]) == row["budget"]
            and len(row["replayed_ids"]) == len(set(row["replayed_ids"]))
            for row in rows
        ),
    }
    old = {(row["archive_id"], row["budget"], row["method"]): row
           for row in prior["rows"] if row["method"] in {"dcta_risk_local_v1", "acis_risk"}}
    current = {(row["archive_id"], row["budget"], row["method"]): row
               for row in rows if row["method"] in {"dcta_risk_local_v1", "acis_risk"}}
    checks["prior_dcta_acis_rows_unchanged"] = current == old
    for budget in budgets:
        for method in methods:
            selected = [row["recall"] for row in rows
                        if row["budget"] == budget and row["method"] == method]
            reported = result["summary"][str(budget)][method]["macro_recall"]
            checks[f"summary_{budget}_{method}"] = abs(sum(selected) / len(selected) - reported) < 1e-12

    payload = {
        "protocol": "memory-libero/external-validation-v1/active-search-extension-audit",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": all(checks.values()),
        "checks": checks,
        "counts": {
            "archives": len(archives),
            "rows": len(rows),
            "methods": len(methods),
            "budgets": len(budgets),
        },
        "primary": {
            method: result["summary"]["4"][method]["macro_recall"]
            for method in result["methods"]
        },
        "posthoc_limitation": result["posthoc_note"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
