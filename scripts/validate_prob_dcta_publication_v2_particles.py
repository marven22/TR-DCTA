"""Label-blind particle-convergence validation on the v2 validation public data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

import _bootstrap

from mcx.publication_v2 import PROTOCOL
from mcx.publication_v2_posterior import cascade_from_json, sample_posterior, stable_seed
from mcx.publication_v2_source import SourceEstimator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--cascade-config", type=Path, required=True)
    parser.add_argument("--candidate", type=int, default=2048)
    parser.add_argument("--reference", type=int, default=8192)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8"))
    if public.get("protocol") != f"{PROTOCOL}/public" or any(
        row["split"] != "validation" for row in public["archives"]
    ):
        raise ValueError("validation public ledger required")
    source_value = json.loads(args.source_config.read_text(encoding="utf-8"))
    source = SourceEstimator(tuple(map(float, source_value["means"])),
                             tuple(map(float, source_value["scales"])),
                             tuple(map(float, source_value["coefficients"])))
    cascade = cascade_from_json(json.loads(args.cascade_config.read_text(encoding="utf-8")))
    # Primary-mask archives only; labels are never loaded.
    archives = [row for row in public["archives"] if row["provenance_missing_rate"] == .25]
    rows = []
    for index, archive in enumerate(archives, start=1):
        prior = source.prior(archive, float(source_value["minimum_source_probability"]))
        low = sample_posterior(archive, prior, cascade, args.candidate,
                               stable_seed(archive["archive_id"], args.candidate))
        high = sample_posterior(archive, prior, cascade, args.reference,
                                stable_seed(archive["archive_id"], args.reference))
        differences = [abs(low.marginal(node) - high.marginal(node))
                       for node in low.candidates]
        source_low, source_high = low.source_probabilities(), high.source_probabilities()
        rows.append({"archive_id": archive["archive_id"],
                     "mean_marginal_absolute_difference": statistics.fmean(differences),
                     "max_marginal_absolute_difference": max(differences),
                     "max_source_probability_difference": max(
                         abs(source_low[key] - source_high[key]) for key in source_low),
                     "candidate_worlds": len(low.worlds), "reference_worlds": len(high.worlds)})
        if index % 20 == 0 or index == len(archives):
            print(f"validated particles {index}/{len(archives)}", flush=True)
    summary = {
        "archive_count": len(rows),
        "mean_marginal_absolute_difference": statistics.fmean(
            row["mean_marginal_absolute_difference"] for row in rows),
        "worst_marginal_absolute_difference": max(
            row["max_marginal_absolute_difference"] for row in rows),
        "worst_source_probability_difference": max(
            row["max_source_probability_difference"] for row in rows),
    }
    checks = {"mean_marginal_difference_below_002": summary["mean_marginal_absolute_difference"] < .02,
              "worst_marginal_difference_below_010": summary["worst_marginal_absolute_difference"] < .10,
              "worst_source_difference_below_005": summary["worst_source_probability_difference"] < .05}
    payload = {"protocol": f"{PROTOCOL}/particle-validation",
               "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "label_blind": True, "candidate_particles": args.candidate,
               "reference_particles": args.reference, "summary": summary,
               "checks": checks, "passed": all(checks.values()), "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
