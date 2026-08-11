"""Create the immutable test-gate ledger and concise publication report."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics


def mean(rows, field="recall"):
    return statistics.fmean(float(row[field]) for row in rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--generation-validation", type=Path, required=True)
    parser.add_argument("--inference-freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    generation_validation = json.loads(args.generation_validation.read_text(encoding="utf-8"))
    freeze = json.loads(args.inference_freeze.read_text(encoding="utf-8"))
    if evaluation.get("expected_split") != "test" or not evaluation.get("complete"):
        raise ValueError("completed frozen test evaluation required")
    if not generation_validation.get("passed") or freeze.get("test_labels_seen") is not False:
        raise ValueError("test integrity prerequisites failed")
    rows = evaluation["rows"]
    primary = [row for row in rows if row["budget"] == 4 and row["provenance_missing_rate"] == .25]
    primary_prob = [row for row in primary if row["method"] == "prob_dcta"]
    pooled = evaluation["primary_summary"]["pooled"]
    comparisons = evaluation["comparisons"]
    initial_brier = mean(primary_prob, "initial_source_brier")
    final_brier = mean(primary_prob, "source_brier")
    source_top1 = mean(primary_prob, "source_top1_correct")
    retention = pooled["prob_dcta"]["macro_recall"] / pooled["known_source_dcta"]["macro_recall"]
    ens_gap = pooled["prob_dcta"]["macro_recall"] - pooled["ens"]["macro_recall"]
    checks = {
        "prob_beats_top1_with_cluster_ci": comparisons["pooled"]["prob_minus_top1"]["lower_95"] > 0,
        "prob_beats_acis": pooled["prob_dcta"]["macro_recall"] > pooled["acis_risk"]["macro_recall"],
        "prob_within_003_of_ens": ens_gap >= -.03,
        "retains_85_percent_known_source": retention >= .85,
        "improves_source_brier": final_brier < initial_brier,
        "negative_evidence_advantage_at_25pct_mask": (
            pooled["prob_dcta"]["macro_recall"] > pooled["positive_only_risk"]["macro_recall"]
        ),
        "at_least_15_test_tasks": evaluation["task_count"] >= 15,
        "beats_top1_pointwise_in_each_benchmark": all(
            evaluation["primary_summary"][benchmark]["prob_dcta"]["macro_recall"]
            > evaluation["primary_summary"][benchmark]["top1_dcta"]["macro_recall"]
            for benchmark in ("libero", "metaworld")
        ),
    }
    sensitivity = {}
    for budget in (2, 4, 8):
        sensitivity[str(budget)] = {}
        for mask in (0.0, .25, .5):
            selected = [row for row in rows if row["budget"] == budget
                        and row["provenance_missing_rate"] == mask]
            sensitivity[str(budget)][str(mask)] = {
                method: mean([row for row in selected if row["method"] == method])
                for method in ("top1_dcta", "acis_risk", "ens", "prob_dcta",
                               "source_then_dcta", "known_source_dcta")
            }
    sanitized = []
    for archive in generation["archives"]:
        records = [value for root in archive["roots"] for value in (root["factual"], root["counterfactual"])]
        records += [value for branch in archive["branches"] for memory in branch["memories"]
                    for value in (memory["factual"], memory["counterfactual"])]
        records += [value for memory in archive["shared_memories"] for value in memory["variants"].values()]
        sanitized.extend(value for value in records if value.get("privacy_sanitization"))
    payload = {
        "protocol": "memory-corruption/multi-origin-publication-v2/test-gate-analysis",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "publication_gate_passed": all(checks.values()), "checks": checks,
        "task_count": evaluation["task_count"], "archive_count": evaluation["archive_count"],
        "primary": {"budget": 4, "provenance_missing_rate": .25,
                    "summary": evaluation["primary_summary"],
                    "comparisons": comparisons,
                    "initial_source_brier": initial_brier, "final_source_brier": final_brier,
                    "source_top1_accuracy": source_top1, "known_source_retention": retention,
                    "prob_minus_ens": ens_gap},
        "sensitivity": sensitivity,
        "generation": {"sanitized_record_count": len(sanitized),
                       "sanitization_rate": len(sanitized) / (evaluation["task_count"] * 60),
                       "causal_summary": generation_validation["summary"]},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown = f"""# Prob-DCTA Publication v2 Frozen Test Results

## Outcome

The frozen publication gate **did not fully pass**. Prob-DCTA establishes a
clear advantage over hard source commitment and the prior ACIS-Risk baseline,
but narrowly misses the ENS noninferiority margin and does not retain the
predeclared fraction of known-source performance.

## Primary endpoint (budget 4, 25% missing provenance)

| Method | LIBERO recall | Meta-World recall | Pooled recall |
|---|---:|---:|---:|
| DCTA-Top1 | {evaluation['primary_summary']['libero']['top1_dcta']['macro_recall']:.3f} | {evaluation['primary_summary']['metaworld']['top1_dcta']['macro_recall']:.3f} | {pooled['top1_dcta']['macro_recall']:.3f} |
| ACIS-Risk | {evaluation['primary_summary']['libero']['acis_risk']['macro_recall']:.3f} | {evaluation['primary_summary']['metaworld']['acis_risk']['macro_recall']:.3f} | {pooled['acis_risk']['macro_recall']:.3f} |
| ENS | {evaluation['primary_summary']['libero']['ens']['macro_recall']:.3f} | {evaluation['primary_summary']['metaworld']['ens']['macro_recall']:.3f} | {pooled['ens']['macro_recall']:.3f} |
| Prob-DCTA | {evaluation['primary_summary']['libero']['prob_dcta']['macro_recall']:.3f} | {evaluation['primary_summary']['metaworld']['prob_dcta']['macro_recall']:.3f} | {pooled['prob_dcta']['macro_recall']:.3f} |
| Source-then-DCTA | {evaluation['primary_summary']['libero']['source_then_dcta']['macro_recall']:.3f} | {evaluation['primary_summary']['metaworld']['source_then_dcta']['macro_recall']:.3f} | {pooled['source_then_dcta']['macro_recall']:.3f} |
| Known-source reference | {evaluation['primary_summary']['libero']['known_source_dcta']['macro_recall']:.3f} | {evaluation['primary_summary']['metaworld']['known_source_dcta']['macro_recall']:.3f} | {pooled['known_source_dcta']['macro_recall']:.3f} |

Prob-DCTA minus Top1 is {comparisons['pooled']['prob_minus_top1']['estimate']:.3f}
(task-cluster 95% CI [{comparisons['pooled']['prob_minus_top1']['lower_95']:.3f},
{comparisons['pooled']['prob_minus_top1']['upper_95']:.3f}]). Prob-DCTA minus
ACIS-Risk is {comparisons['pooled']['prob_minus_acis']['estimate']:.3f}. The
ENS gap is {ens_gap:.3f}, versus the frozen -0.030 noninferiority margin.

Source Brier improves from {initial_brier:.3f} to {final_brier:.3f}, and final
source top-1 accuracy is {source_top1:.3%}. Prob-DCTA retains {retention:.1%}
of known-source recall.

## Pre-specified budget sensitivity

At budget 8 with the same 25% missing-provenance condition, Prob-DCTA reaches
{sensitivity['8']['0.25']['prob_dcta']:.3f} recall, versus
{sensitivity['8']['0.25']['top1_dcta']:.3f} for Top1,
{sensitivity['8']['0.25']['ens']:.3f} for ENS, and
{sensitivity['8']['0.25']['known_source_dcta']:.3f} for the known-source
reference. Thus, at budget 8 the ENS gap is
{sensitivity['8']['0.25']['prob_dcta'] - sensitivity['8']['0.25']['ens']:.3f}
and known-source retention is
{sensitivity['8']['0.25']['prob_dcta'] / sensitivity['8']['0.25']['known_source_dcta']:.1%}.
This sensitivity was pre-specified, but it does not replace the failed budget-4
primary gate.

## Integrity and scale

- 41 independent test tasks: 12 LIBERO and 29 Meta-World.
- 123 task/origin rotations and 369 rotation/provenance-mask archives.
- Affected-set size {generation_validation['summary']['range_affected_count'][0]}–{generation_validation['summary']['range_affected_count'][1]}; mean {generation_validation['summary']['mean_affected_count']:.2f}.
- {generation_validation['summary']['rotations_with_shared_harm']}/123 rotations contain shared functional harm.
- All contamination and harm have a directed causal path.
- {len(sanitized)} of {evaluation['task_count'] * 60} writer records used the logged deterministic format sanitizer.

## Interpretation

The central scientific result survives: preserving origin uncertainty and
conditioning on negative replay evidence materially beats committing to one
suspected source. The current acquisition rule is not yet the best finite-
budget search policy: ENS is stronger, especially on LIBERO, and the
predeclared known-source retention target is missed. `Source-then-DCTA` also
outperformed the frozen primary method on this test set, but it was secondary
and cannot be promoted post hoc. The next method-development iteration should
target the exploration/exploitation objective on development data and then be
tested on a new untouched benchmark—not retuned on these labels.
"""
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown, encoding="utf-8")
    print(json.dumps({"publication_gate_passed": payload["publication_gate_passed"],
                      "checks": checks, "primary": payload["primary"]}, indent=2))


if __name__ == "__main__":
    main()
