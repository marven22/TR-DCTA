"""Fit and freeze v0.4.1 frontier parameters from development only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import _bootstrap

from mcx.memory_libero_v041 import PROTOCOL, build_archive, fit_frontier_parameters, is_strict_record
from mcx.risk_aware_acis import LogisticCalibrator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ledger = json.loads(args.generation.read_text(encoding="utf-8"))
    if ledger.get("protocol") != PROTOCOL:
        raise ValueError("v0.4.1 development ledger required")
    development = [build_archive(r) for r in ledger["archives"]
                   if r["split"] == "development" and is_strict_record(r)]
    if len(development) != 12:
        raise ValueError("exactly twelve strict development archives required")
    c = json.loads(args.calibrator.read_text(encoding="utf-8"))["coefficients"]
    calibrator = LogisticCalibrator(c["intercept"], c["provenance"],
                                    c["formation_task"], c["content"])
    positive = fit_frontier_parameters(development, calibrator, neutral=False)
    delta = fit_frontier_parameters(development, calibrator, neutral=True)
    payload = {
        "protocol": PROTOCOL + "/frontiers-frozen-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "development_archive_ids": [a.archive_id for a in development],
        "source_calibrator": str(args.calibrator),
        "positive_frontier": positive.__dict__, "delta_frontier": delta.__dict__,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

