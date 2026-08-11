"""Fit the v2 observable source prior exclusively on the old 67-task study."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

import _bootstrap

from mcx.publication_v2_source import fit_source_estimator, source_features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    labels = {row["archive_id"]: row for row in private["archives"]}
    selected = [row for row in public["archives"] if row["condition"] == "uniform"]
    training_archives = [row for row in selected if row["split"] in {"development", "validation"}]
    evaluation_archives = [row for row in selected if row["split"] == "test"]
    training_rows = [
        (source_features(archive, source), int(source == labels[archive["archive_id"]]["active_source_id"]))
        for archive in training_archives for source in archive["source_ids"]
    ]
    estimator = fit_source_estimator(training_rows, l2=1.0)

    def metrics(archives):
        top1, brier, true_probability = [], [], []
        for archive in archives:
            truth = labels[archive["archive_id"]]["active_source_id"]
            prior = estimator.prior(archive, .05)
            predicted = min(prior, key=lambda source: (-prior[source], source))
            top1.append(float(predicted == truth)); true_probability.append(prior[truth])
            brier.append(sum((value - float(source == truth)) ** 2
                             for source, value in prior.items()))
        return {"archive_count": len(archives), "top1_accuracy": statistics.fmean(top1),
                "mean_true_probability": statistics.fmean(true_probability),
                "mean_brier": statistics.fmean(brier)}

    payload = {
        "protocol": "memory-corruption/multi-origin-publication-v2/source-estimator-freeze",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "model": "binary-logit-normalized",
        "features": ["source_target", "direct_target", "reachable_target",
                     "source_reachable", "edge_coherence", "reachable_size"],
        "l2": 1.0, "means": list(estimator.means), "scales": list(estimator.scales),
        "coefficients": list(estimator.coefficients),
        "minimum_source_probability": .05,
        "training": metrics(training_archives), "old_heldout_evaluation": metrics(evaluation_archives),
        "source_hashes": {"public": hashlib.sha256(args.public.read_bytes()).hexdigest(),
                          "private": hashlib.sha256(args.private.read_bytes()).hexdigest()},
        "v2_labels_used": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
