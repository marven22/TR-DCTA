"""Post-hoc frozen ACIS-Risk extension for the multi-origin study."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.prob_dcta_libero import PROTOCOL, canonical_hash
from mcx.prob_dcta_libero_baselines import run_prior_weighted_acis_risk
from mcx.risk_aware_acis import LogisticCalibrator


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_acis(path: Path) -> LogisticCalibrator:
    value = json.loads(path.read_text(encoding="utf-8"))["coefficients"]
    return LogisticCalibrator(
        value["intercept"], value["provenance"], value["formation_task"], value["content"]
    )


def metrics(public, private, replayed):
    affected = frozenset(str(node) for node in private["affected_ids"])
    hits = set(replayed) & affected
    return {
        "replayed_ids": list(replayed),
        "discoveries": len(hits),
        "recall": len(hits) / len(affected) if affected else 1.0,
        "audit_yield": len(hits) / len(replayed) if replayed else 0.0,
    }


def bootstrap(primary_rows, acis_rows, draws=10000):
    by_cluster = {}
    for row in primary_rows:
        if row["method"] != "prob_dcta":
            continue
        by_cluster.setdefault(row["base_archive_key"], {}).setdefault("prob", []).append(row["recall"])
    for row in acis_rows:
        by_cluster.setdefault(row["base_archive_key"], {}).setdefault("acis", []).append(row["recall"])
    clusters = sorted(key for key, value in by_cluster.items() if {"prob", "acis"} <= set(value))
    differences = [statistics.fmean(by_cluster[key]["prob"])
                   - statistics.fmean(by_cluster[key]["acis"]) for key in clusters]
    rng = random.Random(260806)
    samples = sorted(statistics.fmean(
        differences[rng.randrange(len(differences))] for _ in differences
    ) for _ in range(draws))
    return {
        "estimate": statistics.fmean(differences),
        "lower_95": samples[int(.025 * draws)],
        "upper_95": samples[int(.975 * draws)],
        "cluster_count": len(clusters),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--primary-evaluation", type=Path, required=True)
    parser.add_argument("--acis-config", type=Path, required=True)
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    primary = json.loads(args.primary_evaluation.read_text(encoding="utf-8"))
    if private.get("public_payload_sha256") != canonical_hash(public):
        raise ValueError("public/private mismatch")
    if primary.get("protocol") != f"{PROTOCOL}/evaluation" or not primary.get("complete"):
        raise ValueError("completed primary multi-origin evaluation required")
    if primary["public_sha256"] != sha256(args.public) or primary["private_sha256"] != sha256(args.private):
        raise ValueError("primary evaluation used different ledgers")
    calibrator = load_acis(args.acis_config)
    labels = {row["archive_id"]: row for row in private["archives"]}
    rows = []
    for public_row in public["archives"]:
        private_row = labels[public_row["archive_id"]]
        affected = frozenset(str(node) for node in private_row["affected_ids"])
        for budget in primary["budgets"]:
            replayed = run_prior_weighted_acis_risk(public_row, affected, budget, calibrator)
            rows.append({
                "archive_id": public_row["archive_id"],
                "base_archive_key": public_row["base_archive_key"],
                "split": public_row["split"],
                "condition": public_row["condition"],
                "budget": budget,
                "affected_count": len(affected),
                **metrics(public_row, private_row, replayed),
            })
    selected = [row for row in rows if row["split"] == "test"
                and row["condition"] in {"high", "medium", "uniform"}
                and row["budget"] == primary["primary_budget"] and row["affected_count"] > 0]
    primary_rows = [row for row in primary["rows"] if row["split"] == "test"
                    and row["condition"] in {"high", "medium", "uniform"}
                    and row["budget"] == primary["primary_budget"] and row["affected_count"] > 0]
    summary = {}
    for condition in ("known", "high", "medium", "uniform", "wrong60"):
        summary[condition] = {}
        for budget in primary["budgets"]:
            subset = [row for row in rows if row["split"] == "test"
                      and row["condition"] == condition and row["budget"] == budget
                      and row["affected_count"] > 0]
            summary[condition][str(budget)] = statistics.fmean(row["recall"] for row in subset)
    payload = {
        "protocol": f"{PROTOCOL}/prior-weighted-acis-risk-extension-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True,
        "posthoc_extension": True,
        "posthoc_note": "Primary labels were already evaluated; the frozen old ACIS calibrator was adapted by prior-weighted source averaging without tuning.",
        "public_sha256": sha256(args.public),
        "private_sha256": sha256(args.private),
        "primary_evaluation_sha256": sha256(args.primary_evaluation),
        "acis_config_sha256": sha256(args.acis_config),
        "implementation_sha256": sha256(args.implementation),
        "primary_macro_recall": statistics.fmean(row["recall"] for row in selected),
        "prob_dcta_macro_recall": primary["primary_summary"]["prob_dcta"]["macro_recall"],
        "prob_minus_acis": bootstrap(primary_rows, selected),
        "test_positive_recall_by_condition_budget": summary,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
