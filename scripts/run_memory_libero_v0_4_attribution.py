"""Post-hoc, explicitly diagnostic attribution of the v0.4 ACIS result."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.memory_libero_v04 import PROTOCOL, build_archive, discovery_case, is_strict_record
from mcx.risk_aware_acis import (
    LogisticCalibrator, ThreeSignalIndex, adaptive_three_signal_replay,
)


METHODS = ("static_probability", "adaptive_probability", "adaptive_impact", "acis_risk")


def load_calibrator(path: Path) -> LogisticCalibrator:
    values = json.loads(path.read_text(encoding="utf-8"))["coefficients"]
    return LogisticCalibrator(values["intercept"], values["provenance"],
                              values["formation_task"], values["content"])


def static_probability(case, calibrator, budget):
    index = ThreeSignalIndex(case)
    source = next(m for m in case.memories if m.memory_id == case.source_id)
    candidates = [m for m in case.memories if m.created_at > source.created_at]
    return [
        node for _, node in sorted(
            ((-calibrator.probability(index.signals(m.memory_id, {case.source_id})),
              m.memory_id) for m in candidates)
        )[:budget]
    ]


def bootstrap(rows, left, right, draws=5000):
    archives = sorted({r["archive_id"] for r in rows})
    values = {(r["archive_id"], r["method"]): r["recall"] for r in rows}
    rng = random.Random(4041)
    samples = []
    for _ in range(draws):
        chosen = [rng.choice(archives) for _ in archives]
        samples.append(statistics.fmean(values[(a, left)] - values[(a, right)] for a in chosen))
    samples.sort()
    return {"mean": statistics.fmean(samples), "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[int(.975 * draws)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ledger = json.loads(args.generation.read_text(encoding="utf-8"))
    if ledger.get("protocol") != PROTOCOL or not ledger.get("complete"):
        raise ValueError("complete v0.4 ledger required")
    archives = [build_archive(r) for r in ledger["archives"] if is_strict_record(r)]
    calibrator = load_calibrator(args.calibrator)
    rows = []
    for archive in archives:
        case = discovery_case(archive)
        for budget in (1, 2, 3, 6, 12):
            for method in METHODS:
                if method == "static_probability":
                    replayed = static_probability(case, calibrator, budget)
                else:
                    internal = {
                        "adaptive_probability": "acis_probability",
                        "adaptive_impact": "acis_impact",
                        "acis_risk": "acis_risk",
                    }[method]
                    replayed = adaptive_three_signal_replay(
                        case, budget, internal, calibrator, seed=42
                    )["replayed_ids"]
                hits = set(replayed) & archive.affected_ids
                rows.append({
                    "archive_id": archive.archive_id, "split": archive.split,
                    "budget": budget, "method": method,
                    "affected_count": len(archive.affected_ids),
                    "replayed_ids": replayed, "discoveries": len(hits),
                    "recall": len(hits) / len(archive.affected_ids)
                              if archive.affected_ids else 1.0,
                })
    primary = [r for r in rows if r["split"] == "heldout" and r["budget"] == 3
               and r["affected_count"] > 0]
    summary = {
        method: {
            "macro_recall_positive_archives": statistics.fmean(
                r["recall"] for r in primary if r["method"] == method
            ),
            "mean_discoveries": statistics.fmean(
                r["discoveries"] for r in primary if r["method"] == method
            ),
        }
        for method in METHODS
    }
    payload = {
        "protocol": PROTOCOL + "/posthoc-attribution-v0.1",
        "diagnostic_not_preregistered": True, "complete": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "calibrator": calibrator.as_dict(), "primary": summary,
        "risk_minus_static_probability": bootstrap(primary, "acis_risk", "static_probability"),
        "risk_minus_adaptive_probability": bootstrap(primary, "acis_risk", "adaptive_probability"),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
