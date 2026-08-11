"""Integrity checks for the completed multi-origin LIBERO study."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import _bootstrap

from mcx.prob_dcta_libero import PROTOCOL, canonical_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    labels = {row["archive_id"]: row for row in private["archives"]}
    public_ids = [row["archive_id"] for row in public["archives"]]
    split_clusters = {}
    condition_counts = Counter()
    leakage_free = True
    valid_priors = True
    known_correct = True
    labels_valid = True
    for row in public["archives"]:
        label = labels[row["archive_id"]]
        split_clusters.setdefault(row["split"], set()).add(row["base_archive_key"])
        condition_counts[row["condition"]] += 1
        rendered = json.dumps(row["memories"])
        leakage_free &= (
            "recommended_policy_id" not in rendered
            and "affected_ids" not in row and "active_source_id" not in row
        )
        valid_priors &= abs(sum(row["source_prior"].values()) - 1.0) <= 1e-12
        labels_valid &= (
            label["active_source_id"] in row["source_ids"]
            and set(label["affected_ids"]).issubset(row["candidate_ids"])
        )
        if row["condition"] == "known":
            known_correct &= row["source_prior"][label["active_source_id"]] == 1.0
    row_index = {
        (row["archive_id"], row["budget"], row["method"]): row
        for row in evaluation["rows"]
    }
    known_reduction = all(
        row_index[(archive_id, budget, "prob_dcta")]["replayed_ids"]
        == row_index[(archive_id, budget, "known_source_dcta")]["replayed_ids"]
        for archive_id in public_ids
        if next(row for row in public["archives"] if row["archive_id"] == archive_id)["condition"] == "known"
        for budget in evaluation["budgets"]
    )
    checks = {
        "public_private_hash_match": private["public_payload_sha256"] == canonical_hash(public),
        "unique_complete_ids": len(public_ids) == len(set(public_ids)) == 1005
                               and set(public_ids) == set(labels),
        "split_cluster_counts": {key: len(value) for key, value in split_clusters.items()}
                                == {"development": 10, "validation": 10, "test": 47},
        "condition_counts": dict(condition_counts)
                            == {condition: 201 for condition in ("known", "high", "medium", "uniform", "wrong60")},
        "public_leakage_check": leakage_free,
        "valid_source_priors": valid_priors,
        "known_prior_points_to_truth": known_correct,
        "private_labels_valid": labels_valid,
        "truth_supported_everywhere": all(row["truth_support"] for row in evaluation["diagnostics"]),
        "complete_method_budget_grid": len(evaluation["rows"]) == 1005 * 3 * 9
                                       and len(row_index) == len(evaluation["rows"]),
        "known_source_exact_reduction": known_reduction,
        "frozen_success_gate_passed": evaluation["success_gate"]["passed"],
    }
    payload = {
        "protocol": f"{PROTOCOL}/validation-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": all(checks.values()),
        "checks": checks,
        "realized_signal_accuracy": evaluation["realized_signal_accuracy"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

