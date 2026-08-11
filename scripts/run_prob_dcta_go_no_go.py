"""Run the frozen exact Prob-DCTA go/no-go benchmark."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

import _bootstrap

from mcx.prob_dcta_benchmark import evaluate_instance, frozen_prob_dcta_instances


METHODS = ("static_risk", "positive_only_risk", "top1_dcta", "source_ig",
           "source_then_dcta", "ens", "prob_dcta")
METRICS = ("expected_weighted_utility", "expected_discoveries", "expected_harm_recall",
           "source_top1_accuracy", "source_brier", "source_entropy")
AMBIGUOUS = {"high", "medium", "uniform"}


def _mean(rows, method, metric):
    return statistics.fmean(row["outcomes"][method][metric] for row in rows)


def _summary(rows):
    output = {}
    for confidence in ("known", "high", "medium", "uniform", "wrong60"):
        selected = [row for row in rows if row["confidence"] == confidence]
        output[confidence] = {
            method: {metric: _mean(selected, method, metric) for metric in METRICS}
            for method in METHODS
        }
        output[confidence]["exact_bayes_oracle"] = {
            "expected_weighted_utility": statistics.fmean(
                row["outcomes"]["exact_bayes_oracle"]["expected_weighted_utility"]
                for row in selected
            )
        }
    selected = [row for row in rows if row["confidence"] in AMBIGUOUS]
    pooled = {
        method: {metric: _mean(selected, method, metric) for metric in METRICS}
        for method in METHODS
    }
    pooled["exact_bayes_oracle"] = {
        "expected_weighted_utility": statistics.fmean(
            row["outcomes"]["exact_bayes_oracle"]["expected_weighted_utility"]
            for row in selected
        )
    }
    return output, pooled


def _initial_brier(instance):
    probabilities = instance.belief.source_probabilities()
    return sum(
        world.weight * sum(
            (probabilities[source] - float(source == world.source_id)) ** 2
            for source in instance.belief.source_ids
        )
        for world in instance.truth.worlds
    )


def _gate(rows, pooled):
    known = [row for row in rows if row["confidence"] == "known"]
    exact_reduction = all(
        abs(row["outcomes"]["prob_dcta"][metric]
            - row["outcomes"]["top1_dcta"][metric]) <= 1e-12
        for row in known
        for metric in ("expected_weighted_utility", "expected_discoveries",
                       "expected_harm_recall")
    )
    prob = pooled["prob_dcta"]["expected_weighted_utility"]
    top1 = pooled["top1_dcta"]["expected_weighted_utility"]
    positive = pooled["positive_only_risk"]["expected_weighted_utility"]
    ens = pooled["ens"]["expected_weighted_utility"]
    oracle = pooled["exact_bayes_oracle"]["expected_weighted_utility"]
    closure = (prob - top1) / (oracle - top1) if oracle > top1 + 1e-12 else None
    ambiguous_rows = [row for row in rows if row["confidence"] in AMBIGUOUS]
    initial_brier = statistics.fmean(row["initial_source_brier"] for row in ambiguous_rows)
    final_brier = pooled["prob_dcta"]["source_brier"]
    checks = {
        "known_origin_exact_reduction": exact_reduction,
        "ambiguous_beats_top1_and_positive_only": prob > top1 + 1e-12 and prob > positive + 1e-12,
        "closes_at_least_20_percent_top1_oracle_gap": closure is not None and closure >= .20,
        "within_002_of_ens": prob + .02 >= ens,
        "source_brier_improves": final_brier < initial_brier - 1e-12,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "ambiguous_prob_minus_top1": prob - top1,
        "ambiguous_prob_minus_positive_only": prob - positive,
        "ambiguous_prob_minus_ens": prob - ens,
        "top1_oracle_gap_closure": closure,
        "initial_source_brier": initial_brier,
        "final_prob_dcta_source_brier": final_brier,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    instances = frozen_prob_dcta_instances()
    rows = []
    for instance in instances:
        rows.append({
            "instance_id": instance.instance_id,
            "confidence": instance.confidence,
            "signaled_source": instance.signaled_source,
            "level": int(instance.instance_id.split("_l", 1)[1].split("_", 1)[0]),
            "misspecified": instance.misspecified,
            "candidate_count": len(instance.truth.candidates),
            "truth_world_count": len(instance.truth.worlds),
            "belief_world_count": len(instance.belief.worlds),
            "budget": instance.budget,
            "initial_source_brier": _initial_brier(instance),
            "outcomes": evaluate_instance(instance),
        })
    by_confidence, pooled = _summary(rows)
    gate = _gate(rows, pooled)
    payload = {
        "protocol": "prob-dcta-go-no-go-v0.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True,
        "exact_enumeration": True,
        "instance_count": len(rows),
        "by_confidence": by_confidence,
        "pooled_ambiguous": pooled,
        "go_no_go_gate": gate,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
