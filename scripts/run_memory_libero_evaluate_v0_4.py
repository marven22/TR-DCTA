"""Evaluate the falsification-first Memory-LIBERO v0.4 pilot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.memory_libero_v04 import (
    BUDGETS, PROTOCOL, build_archive, evaluate_method, fit_branch_model,
    initial_probabilities, is_strict_record,
)
from mcx.risk_aware_acis import LogisticCalibrator


METHODS = (
    "random", "raw_content", "graph_reachability", "acis_risk_v1",
    "calibrated_individual", "static_branch_posterior",
    "adaptive_branch_posterior", "causal_oracle", "full_replay",
)


def load_calibrator(path: Path) -> LogisticCalibrator:
    values = json.loads(path.read_text(encoding="utf-8"))["coefficients"]
    return LogisticCalibrator(values["intercept"], values["provenance"],
                              values["formation_task"], values["content"])


def _bootstrap_delta(rows, left: str, right: str, draws: int = 5000):
    archives = sorted({row["archive_id"] for row in rows})
    by_key = {(r["archive_id"], r["method"]): r["recall"] for r in rows}
    rng = random.Random(404)
    values = []
    for _ in range(draws):
        sample = [rng.choice(archives) for _ in archives]
        values.append(statistics.fmean(by_key[(a, left)] - by_key[(a, right)] for a in sample))
    values.sort()
    return {"mean": statistics.fmean(values), "lower_95": values[int(.025 * draws)],
            "upper_95": values[int(.975 * draws)]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ledger = json.loads(args.generation.read_text(encoding="utf-8"))
    if ledger.get("protocol") != PROTOCOL or not ledger.get("complete"):
        raise ValueError("complete v0.4 generation required")
    strict = [build_archive(r) for r in ledger["archives"] if is_strict_record(r)]
    development = [a for a in strict if a.split == "development"]
    heldout = [a for a in strict if a.split == "heldout"]
    if len(development) < 8 or len(heldout) < 4:
        raise ValueError("v0.4 strict archive gate failed")
    model = fit_branch_model(development)
    calibrator = load_calibrator(args.calibrator)
    rows = []
    for archive in strict:
        for budget in BUDGETS:
            for method in METHODS:
                rows.append({
                    "archive_id": archive.archive_id, "suite": archive.suite,
                    "split": archive.split, "affected_count": len(archive.affected_ids),
                    "partial_branch": any(
                        0 < sum(n in archive.affected_ids for n in b) < len(b)
                        for b in archive.branch_ids
                    ),
                    "budget": budget, "method": method,
                    **evaluate_method(archive, model, calibrator, method, budget),
                })
    summary = {}
    for split in ("development", "heldout"):
        summary[split] = {}
        for budget in BUDGETS:
            summary[split][str(budget)] = {}
            for method in METHODS:
                subset = [r for r in rows if r["split"] == split and r["budget"] == budget and r["method"] == method]
                positive = [r for r in subset if r["affected_count"] > 0]
                summary[split][str(budget)][method] = {
                    "macro_recall_positive_archives": (
                        statistics.fmean(r["recall"] for r in positive) if positive else None
                    ),
                    "zero_positive_archives": len(subset) - len(positive),
                    "mean_discoveries": statistics.fmean(r["discoveries"] for r in subset),
                    "audit_yield": statistics.fmean(r["audit_yield"] for r in subset),
                    "residual_invalid_exposure": statistics.fmean(r["residual_invalid_exposure"] for r in subset),
                    "initial_brier": statistics.fmean(r["initial_brier"] for r in subset),
                    "units": len(subset),
                }
    primary_rows = [r for r in rows if r["split"] == "heldout" and r["budget"] == 3
                    and r["affected_count"] > 0]
    primary = summary["heldout"]["3"]
    heldout_mixed = [a for a in heldout if 0 < len(a.affected_ids) < 12]
    heldout_partial = [a for a in heldout if any(0 < sum(n in a.affected_ids for n in b) < 3 for b in a.branch_ids)]
    stronger = max(("static_branch_posterior", "calibrated_individual"),
                   key=lambda m: primary[m]["macro_recall_positive_archives"])
    delta = _bootstrap_delta(primary_rows, "adaptive_branch_posterior", stronger)
    graph_precision = statistics.fmean(len(a.affected_ids) / 12 for a in heldout)
    gates = {
        "graph_blind_withdrawal_precision_below_0_80": graph_precision < .80,
        "raw_content_recall_below_0_80": primary["raw_content"]["macro_recall_positive_archives"] < .80,
        "at_least_half_heldout_archives_mixed": len(heldout_mixed) >= len(heldout) / 2,
        "at_least_one_partial_branch": bool(heldout_partial),
        "adaptive_gain_at_least_0_05": (
            primary["adaptive_branch_posterior"]["macro_recall_positive_archives"]
            - primary[stronger]["macro_recall_positive_archives"] >= .05
        ),
        "adaptive_bootstrap_lower_above_zero": delta["lower_95"] > 0,
    }
    payload = {
        "protocol": PROTOCOL, "complete": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "strict_development_archives": len(development),
        "strict_heldout_archives": len(heldout),
        "branch_model": {"alpha": model.alpha, "beta": model.beta,
                         "evidence": model.evidence.__dict__},
        "heldout_graph_blind_withdrawal_precision": graph_precision,
        "heldout_mixed_archives": len(heldout_mixed),
        "heldout_partial_archives": len(heldout_partial),
        "stronger_static_baseline": stronger, "paired_bootstrap_delta": delta,
        "gates": gates, "all_gates_passed": all(gates.values()),
        "summary": summary, "rows": rows,
        "initial_probabilities": {
            a.archive_id: initial_probabilities(a, model) for a in heldout
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"primary": primary, "stronger_static_baseline": stronger,
                      "paired_bootstrap_delta": delta, "gates": gates}, indent=2))


if __name__ == "__main__":
    main()
