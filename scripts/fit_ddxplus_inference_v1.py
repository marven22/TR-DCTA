"""Fit and diagnose the DDXPlus source and cascade models.

This is the go/no-go diagnostic for the domain.  The audit posterior is built
from a fitted origin prior and a fitted contamination/emission cascade.  If the
origin estimator cannot beat the one-in-three chance rate, the posterior
carries no information, every acquisition policy sees the same belief, and the
domain cannot discriminate between methods regardless of their quality.

Fitting follows the existing held-task-out contract: a task's own archives never
appear in the model that scores them, and only complete-provenance rows are used
for fitting.
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.ddxplus import PROTOCOL
from mcx.publication_v2_posterior import (
    fit_cascade_parameters, sample_importance_posterior, stable_seed, support_proposal,
)
from mcx.publication_v2_source import fit_source_estimator, source_features


ROOT = Path(__file__).resolve().parents[1]


LEDGER_DIR = ROOT / "results"


def load(split: str, kind: str) -> list[dict[str, Any]]:
    path = LEDGER_DIR / f"ddxplus_{split}_{kind}_mask_consistent.json"
    return json.loads(path.read_text(encoding="utf-8"))["archives"]


def ranking_auc(marginals: dict[str, float], affected: set[str]) -> float | None:
    """Probability a harmful memory outranks a clean one under the posterior."""
    harmful = [value for node, value in marginals.items() if node in affected]
    clean = [value for node, value in marginals.items() if node not in affected]
    if not harmful or not clean:
        return None
    wins = sum((1.0 if h > c else 0.5 if h == c else 0.0)
               for h in harmful for c in clean)
    return wins / (len(harmful) * len(clean))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--primary-rate", type=float, default=0.25)
    parser.add_argument("--particles", type=int, default=512)
    parser.add_argument("--auc-archives", type=int, default=9)
    parser.add_argument("--ledger-dir", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    global LEDGER_DIR
    LEDGER_DIR = args.ledger_dir

    public = {split: load(split, "public") for split in ("development", "validation")}
    private = {split: load(split, "private") for split in ("development", "validation")}
    labels = {row["archive_id"]: row
              for split in private for row in private[split]}

    results: dict[str, Any] = {}
    auc_values: list[float] = []
    for split in ("development", "validation"):
        pool = public["development"] if split == "development" else (
            public["development"] + public["validation"])
        scored: list[dict[str, Any]] = []
        cascade_counts: dict[str, int] = {}
        for held_task in sorted({row["task_key"] for row in public[split]}):
            training = [row for row in pool
                        if row["task_key"] != held_task
                        and float(row["provenance_missing_rate"]) == 0.0]
            cascade, counts = fit_cascade_parameters(training, labels, l2=1.0)
            cascade_counts = counts
            estimator = fit_source_estimator(
                [(source_features(row, str(source)),
                  int(str(source) == str(labels[row["archive_id"]]["active_source_id"])))
                 for row in training for source in row["source_ids"]], l2=1.0)
            held = [row for row in public[split]
                    if row["task_key"] == held_task
                    and float(row["provenance_missing_rate"]) == args.primary_rate]
            for archive in held:
                truth = labels[archive["archive_id"]]
                prior = estimator.prior(archive, 0.0)
                predicted = min(prior, key=lambda source: (-prior[source], source))
                actual = str(truth["active_source_id"])
                scored.append({"archive_id": archive["archive_id"],
                               "correct": predicted == actual,
                               "true_source_probability": prior[actual]})
                if split == "development" and len(auc_values) < args.auc_archives:
                    posterior, _ = sample_importance_posterior(
                        archive, prior, support_proposal(prior, 0.05), cascade,
                        args.particles,
                        stable_seed(str(archive["archive_id"]), args.particles))
                    marginals = {node: posterior.marginal(node)
                                 for node in posterior.candidates}
                    value = ranking_auc(marginals, set(map(str, truth["affected_ids"])))
                    if value is not None:
                        auc_values.append(value)
        results[split] = {
            "archives_scored": len(scored),
            "source_top1_accuracy": statistics.fmean(
                float(row["correct"]) for row in scored),
            "mean_true_source_probability": statistics.fmean(
                row["true_source_probability"] for row in scored),
            "chance_accuracy": 1.0 / 3.0,
            "cascade_rows": cascade_counts,
        }

    payload = {
        "protocol": f"{PROTOCOL}/ddxplus-inference-diagnostic",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_provenance_missing_rate": args.primary_rate,
        "particles": args.particles,
        "source_estimator": results,
        "posterior_harm_ranking_auc": {
            "archives": len(auc_values),
            "mean": statistics.fmean(auc_values) if auc_values else None,
            "min": min(auc_values) if auc_values else None,
            "max": max(auc_values) if auc_values else None,
            "chance": 0.5,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in
                      ("source_estimator", "posterior_harm_ranking_auc")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
