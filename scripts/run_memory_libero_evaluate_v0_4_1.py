"""Frozen evaluation for Memory-LIBERO v0.4.1."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.memory_libero_v041 import (
    BUDGETS, PROTOCOL, FrontierParameters, build_archive, evaluate_method,
    is_strict_record,
)
from mcx.risk_aware_acis import LogisticCalibrator


METHODS = (
    "random", "raw_content", "graph_reachability", "static_source_probability",
    "acis_probability", "acis_risk", "positive_frontier", "delta_frontier",
    "causal_oracle", "full_replay",
)


def load_calibrator(path: Path):
    c = json.loads(path.read_text(encoding="utf-8"))["coefficients"]
    return LogisticCalibrator(c["intercept"], c["provenance"], c["formation_task"], c["content"])


def bootstrap(rows, left, right, draws=5000):
    archives = sorted({r["archive_id"] for r in rows})
    values = {(r["archive_id"], r["method"]): r["recall"] for r in rows}
    rng = random.Random(40411); samples = []
    for _ in range(draws):
        selected = [rng.choice(archives) for _ in archives]
        samples.append(statistics.fmean(values[a, left] - values[a, right] for a in selected))
    samples.sort()
    return {"mean": statistics.fmean(samples), "lower_95": samples[int(.025*draws)],
            "upper_95": samples[int(.975*draws)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--frontier-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ledger = json.loads(args.generation.read_text(encoding="utf-8"))
    if ledger.get("protocol") != PROTOCOL or not ledger.get("complete"):
        raise ValueError("complete v0.4.1 ledger required")
    archives = [build_archive(r) for r in ledger["archives"] if is_strict_record(r)]
    development = [a for a in archives if a.split == "development"]
    heldout = [a for a in archives if a.split == "heldout"]
    if len(development) < 8 or len(heldout) < 4:
        raise ValueError("v0.4.1 strict split gate failed")
    calibrator = load_calibrator(args.calibrator)
    frozen = json.loads(args.frontier_config.read_text(encoding="utf-8"))
    if frozen.get("protocol") != PROTOCOL + "/frontiers-frozen-v1":
        raise ValueError("frozen v0.4.1 frontier config required")
    expected_ids = sorted(a.archive_id for a in development)
    if sorted(frozen["development_archive_ids"]) != expected_ids:
        raise ValueError("frontier config was fitted on a different development split")
    positive_params = FrontierParameters(**frozen["positive_frontier"])
    delta_params = FrontierParameters(**frozen["delta_frontier"])
    rows = []
    for archive in archives:
        for budget in BUDGETS:
            for method in METHODS:
                rows.append({
                    "archive_id": archive.archive_id, "suite": archive.suite,
                    "split": archive.split, "budget": budget, "method": method,
                    "affected_count": len(archive.affected_ids),
                    "deep_affected_count": len(archive.affected_ids - archive.direct_gateways),
                    **evaluate_method(archive, calibrator, method, budget,
                                      positive_params, delta_params),
                })
    summary = {}
    for split in ("development", "heldout"):
        summary[split] = {}
        for budget in BUDGETS:
            summary[split][str(budget)] = {}
            for method in METHODS:
                subset = [r for r in rows if r["split"] == split and r["budget"] == budget and r["method"] == method]
                positive = [r for r in subset if r["affected_count"] > 0]
                deep = [r for r in subset if r["deep_affected_count"] > 0]
                summary[split][str(budget)][method] = {
                    "macro_recall_positive_archives": statistics.fmean(r["recall"] for r in positive),
                    "macro_deep_recall": statistics.fmean(r["deep_recall"] for r in deep),
                    "mean_discoveries": statistics.fmean(r["discoveries"] for r in subset),
                    "audit_yield": statistics.fmean(r["audit_yield"] for r in subset),
                    "residual_invalid_exposure": statistics.fmean(r["residual_invalid_exposure"] for r in subset),
                    "zero_positive_archives": len(subset)-len(positive), "units": len(subset),
                }
    primary = summary["heldout"]["4"]
    frozen = ("raw_content", "graph_reachability", "static_source_probability",
              "acis_probability", "acis_risk")
    strongest = max(frozen, key=lambda m: primary[m]["macro_recall_positive_archives"])
    primary_rows = [r for r in rows if r["split"] == "heldout" and r["budget"] == 4 and r["affected_count"] > 0]
    delta_ci = bootstrap(primary_rows, "delta_frontier", strongest)
    affected = sum(len(a.affected_ids) for a in heldout)
    deep_affected = sum(len(a.affected_ids-a.direct_gateways) for a in heldout)
    graph_precision = affected / (18*len(heldout))
    gates = {
        "all_six_heldout_strict": len(heldout) == 6,
        "deep_effect_fraction_at_least_0_25": deep_affected/max(1, affected) >= .25,
        "graph_blind_precision_below_0_80": graph_precision < .80,
        "static_recall_below_0_80": primary["static_source_probability"]["macro_recall_positive_archives"] < .80,
        "delta_gain_at_least_0_05": (
            primary["delta_frontier"]["macro_recall_positive_archives"]
            - primary[strongest]["macro_recall_positive_archives"] >= .05
        ),
        "delta_bootstrap_lower_above_zero": delta_ci["lower_95"] > 0,
    }
    payload = {
        "protocol": PROTOCOL, "complete": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "strict_development_archives": len(development), "strict_heldout_archives": len(heldout),
        "positive_frontier_parameters": positive_params.__dict__,
        "delta_frontier_parameters": delta_params.__dict__,
        "heldout_affected": affected, "heldout_deep_affected": deep_affected,
        "heldout_graph_blind_withdrawal_precision": graph_precision,
        "strongest_frozen_baseline": strongest, "delta_minus_strongest_bootstrap": delta_ci,
        "gates": gates, "method_gate_passed": gates["delta_gain_at_least_0_05"] and gates["delta_bootstrap_lower_above_zero"],
        "summary": summary, "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in payload.items() if k not in ("summary","rows")}
                     | {"primary": primary}, indent=2))


if __name__ == "__main__":
    main()
