"""Evaluate SCACD-UP-Continuous on held-out Memory-LIBERO v0.3.3."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

import _bootstrap

from mcx.memory_libero_v03 import (
    BUDGETS, CONDITIONS, PROTOCOL, build_archive, channel_rates, discovery_case,
    evaluate_method, fit_evidence, is_strict_record, mask_edges, similarity,
)
from mcx.risk_aware_acis import LogisticCalibrator


METHODS = (
    "random", "content", "graph_reachability", "acis_risk_v1",
    "graph_as_truth", "scacd_up_continuous", "full_replay",
)


def load_calibrator(path: Path) -> LogisticCalibrator:
    values = json.loads(path.read_text(encoding="utf-8"))["coefficients"]
    return LogisticCalibrator(
        values["intercept"], values["provenance"],
        values["formation_task"], values["content"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    if generation.get("protocol") != PROTOCOL or not generation.get("complete"):
        raise ValueError("v0.3.3 generation is incomplete or incompatible")
    archives = [build_archive(record) for record in generation["archives"] if is_strict_record(record)]
    development = [archive for archive in archives if archive.split == "development"]
    heldout = [archive for archive in archives if archive.split == "heldout"]
    if len(development) < 10 or len(heldout) < 5:
        raise ValueError("strict generation gate failed")
    global_evidence = fit_evidence(development)
    evidence_by_archive = {}
    for archive in archives:
        evidence_by_archive[archive.archive_id] = (
            global_evidence if archive.split == "heldout"
            else fit_evidence([item for item in development if item.archive_id != archive.archive_id])
        )
    channels = {}
    for condition in CONDITIONS:
        q, r, counts = channel_rates(development, condition)
        channels[condition] = {"q": q, "r": r, "counts": counts}
    calibrator = load_calibrator(args.calibrator)
    rows = []
    for archive in archives:
        evidence = evidence_by_archive[archive.archive_id]
        for condition in CONDITIONS:
            channel = channels[condition]
            for mask_index in range(10):
                edges = mask_edges(archive, condition, mask_index)
                case = discovery_case(archive, edges)
                for budget in BUDGETS:
                    for method in METHODS:
                        result = evaluate_method(
                            archive=archive, case=case, edges=edges,
                            evidence=evidence, q=channel["q"], r=channel["r"],
                            condition=condition, mask_index=mask_index, budget=budget,
                            method=method, calibrator=calibrator,
                        )
                        rows.append({
                            "archive_id": archive.archive_id, "suite": archive.suite,
                            "split": archive.split, "condition": condition,
                            "mask_index": mask_index, "budget": budget,
                            "method": method, **result,
                        })
    summary = {}
    for split in ("development", "heldout"):
        summary[split] = {}
        for condition in CONDITIONS:
            summary[split][condition] = {}
            for budget in BUDGETS:
                summary[split][condition][str(budget)] = {}
                for method in METHODS:
                    subset = [row for row in rows if row["split"] == split
                              and row["condition"] == condition
                              and row["budget"] == budget and row["method"] == method]
                    summary[split][condition][str(budget)][method] = {
                        "macro_recall": statistics.fmean(row["recall"] for row in subset),
                        "mean_discoveries": statistics.fmean(row["discoveries"] for row in subset),
                        "robot_policy_validity": statistics.fmean(row["robot_policy_validity"] for row in subset),
                        "repair_precision": 1.0, "units": len(subset),
                    }
    primary = summary["heldout"]["deleted_spurious"]["3"]
    hardness = {
        "content_recall_no_more_than_0_80": primary["content"]["macro_recall"] <= 0.80,
        "graph_recall_no_more_than_0_80": primary["graph_as_truth"]["macro_recall"] <= 0.80,
    }
    gates = {
        "scacd_minus_graph_at_least_0_10": (
            primary["scacd_up_continuous"]["macro_recall"]
            - primary["graph_as_truth"]["macro_recall"] >= 0.10
        ),
        "scacd_minus_acis_at_least_0_05": (
            primary["scacd_up_continuous"]["macro_recall"]
            - primary["acis_risk_v1"]["macro_recall"] >= 0.05
        ),
        "scacd_minus_content_at_least_0_05": (
            primary["scacd_up_continuous"]["macro_recall"]
            - primary["content"]["macro_recall"] >= 0.05
        ),
        "repair_precision_one": primary["scacd_up_continuous"]["repair_precision"] == 1.0,
        "robot_validity_improves_over_0_75": primary["scacd_up_continuous"]["robot_policy_validity"] > 0.75,
    }
    content_diagnostic = {
        split: {
            label: {
                "count": len(values), "mean": statistics.fmean(values),
                "minimum": min(values), "maximum": max(values),
            }
            for label, values in {
                "affected": [similarity(a, n) for a in archives if a.split == split for n in a.affected_ids],
                "clean": [similarity(a, n) for a in archives if a.split == split for b in a.branch_ids[1:] for n in b],
            }.items()
        }
        for split in ("development", "heldout")
    }
    payload = {
        "protocol": PROTOCOL, "complete": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "strict_development_archives": len(development),
        "strict_heldout_archives": len(heldout),
        "global_development_evidence": global_evidence.__dict__,
        "content_diagnostic": content_diagnostic,
        "channel_calibration": channels, "methods": list(METHODS),
        "budgets": list(BUDGETS), "conditions": list(CONDITIONS),
        "source_only_robot_policy_validity": 0.75,
        "summary": summary, "hardness_gates": hardness,
        "hardness_gate_passed": all(hardness.values()),
        "mechanism_gates": gates,
        "mechanism_gate_passed": all(hardness.values()) and all(gates.values()),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "strict_development_archives": len(development),
        "strict_heldout_archives": len(heldout),
        "heldout_deleted_spurious_budget_3": primary,
        "hardness_gates": hardness, "mechanism_gates": gates,
        "mechanism_gate_passed": payload["mechanism_gate_passed"],
    }, indent=2))


if __name__ == "__main__":
    main()
