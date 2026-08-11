"""Exploratory budget robustness following the frozen Prob-DCTA gate."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

import _bootstrap

from mcx.prob_dcta_benchmark import evaluate_instance, frozen_prob_dcta_instances


METHODS = ("positive_only_risk", "top1_dcta", "source_ig", "source_then_dcta",
           "ens", "prob_dcta")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for budget in (2, 3, 4, 5):
        for base in frozen_prob_dcta_instances():
            if base.confidence == "known":
                continue
            instance = replace(base, budget=budget)
            rows.append({
                "budget": budget,
                "confidence": instance.confidence,
                "misspecified": instance.misspecified,
                "outcomes": evaluate_instance(instance),
            })
    summary = []
    for budget in (2, 3, 4, 5):
        for group, confidences in (
            ("calibrated_ambiguous", {"high", "medium", "uniform"}),
            ("wrong60", {"wrong60"}),
        ):
            selected = [row for row in rows
                        if row["budget"] == budget and row["confidence"] in confidences]
            utilities = {
                method: statistics.fmean(
                    row["outcomes"][method]["expected_weighted_utility"]
                    for row in selected
                )
                for method in METHODS
            }
            oracle = statistics.fmean(
                row["outcomes"]["exact_bayes_oracle"]["expected_weighted_utility"]
                for row in selected
            )
            summary.append({
                "budget": budget,
                "group": group,
                "expected_weighted_utility": utilities,
                "oracle": oracle,
                "prob_minus_top1": utilities["prob_dcta"] - utilities["top1_dcta"],
                "prob_minus_ens": utilities["prob_dcta"] - utilities["ens"],
                "hybrid_minus_prob": utilities["source_then_dcta"] - utilities["prob_dcta"],
            })
    payload = {
        "protocol": "prob-dcta-budget-robustness-v0.1-exploratory",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True,
        "exact_enumeration": True,
        "budgets": [2, 3, 4, 5],
        "summary": summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
