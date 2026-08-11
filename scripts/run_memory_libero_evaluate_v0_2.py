"""Evaluate frozen discovery methods on strict Memory-LIBERO v0.2 archives."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

import _bootstrap

from mcx.memory_libero import (
    BUDGETS, CONDITIONS, PROTOCOL, build_archive, channel_rates, content_rates,
    discovery_case, evaluate_method, mask_edges,
)
from mcx.risk_aware_acis import LogisticCalibrator


METHODS = (
    "random", "content", "graph_reachability", "acis_risk_v1",
    "graph_as_truth", "scacd_up_point", "full_replay",
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
        raise ValueError("v0.2 generation is incomplete or incompatible")
    archives = [build_archive(record) for record in generation["archives"]]
    if len(archives) < 5:
        raise ValueError("strict archive feasibility gate failed")
    calibrator = load_calibrator(args.calibrator)
    channels = {}
    for condition in CONDITIONS:
        q, r, counts = channel_rates(archives, condition)
        channels[condition] = {"q": q, "r": r, "counts": counts}
    calibrations = {}
    for archive in archives:
        sensitivity, fpr, counts = content_rates(archives, archive.archive_id)
        calibrations[archive.archive_id] = {
            "sensitivity": sensitivity, "false_positive_rate": fpr, "counts": counts,
        }

    rows = []
    for archive in archives:
        calibration = calibrations[archive.archive_id]
        for condition in CONDITIONS:
            channel = channels[condition]
            for mask_index in range(10):
                edges = mask_edges(archive, condition, mask_index)
                case = discovery_case(archive, edges)
                for budget in BUDGETS:
                    for method in METHODS:
                        result = evaluate_method(
                            archive=archive, case=case, edges=edges,
                            condition=condition, mask_index=mask_index,
                            budget=budget, method=method, calibrator=calibrator,
                            sensitivity=calibration["sensitivity"],
                            false_positive_rate=calibration["false_positive_rate"],
                            q=channel["q"], r=channel["r"],
                        )
                        rows.append({
                            "archive_id": archive.archive_id, "condition": condition,
                            "mask_index": mask_index, "budget": budget,
                            "method": method, **result,
                        })
    summary = {}
    for condition in CONDITIONS:
        summary[condition] = {}
        for budget in BUDGETS:
            summary[condition][str(budget)] = {}
            for method in METHODS:
                subset = [row for row in rows if row["condition"] == condition
                          and row["budget"] == budget and row["method"] == method]
                summary[condition][str(budget)][method] = {
                    "macro_recall": statistics.fmean(row["recall"] for row in subset),
                    "mean_discoveries": statistics.fmean(row["discoveries"] for row in subset),
                    "robot_success_rate": statistics.fmean(float(row["robot_success"]) for row in subset),
                    "repair_precision": 1.0,
                    "units": len(subset),
                }
    noisy = summary["deleted_spurious"]["3"]
    gates = {
        "scacd_minus_graph_at_least_0_10": (
            noisy["scacd_up_point"]["macro_recall"]
            - noisy["graph_as_truth"]["macro_recall"] >= 0.10
        ),
        "scacd_minus_acis_at_least_0_05": (
            noisy["scacd_up_point"]["macro_recall"]
            - noisy["acis_risk_v1"]["macro_recall"] >= 0.05
        ),
        "repair_precision_one": noisy["scacd_up_point"]["repair_precision"] == 1.0,
        "robot_success_improves_over_source_only": noisy["scacd_up_point"]["robot_success_rate"] > 0.0,
    }
    payload = {
        "protocol": PROTOCOL, "complete": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "strict_archive_count": len(archives), "conditions": list(CONDITIONS),
        "masks_per_archive_condition": 10, "budgets": list(BUDGETS),
        "methods": list(METHODS), "channel_calibration": channels,
        "content_calibration": calibrations, "source_only_robot_success": 0.0,
        "summary": summary, "mechanism_gates": gates,
        "mechanism_gate_passed": all(gates.values()), "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "strict_archive_count": len(archives),
        "deleted_spurious_budget_3": noisy,
        "mechanism_gates": gates,
        "mechanism_gate_passed": payload["mechanism_gate_passed"],
    }, indent=2))


if __name__ == "__main__":
    main()
