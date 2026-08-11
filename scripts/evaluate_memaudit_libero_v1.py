"""Join private labels only after frozen MemAudit rankings have been produced."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

import _bootstrap


PROTOCOL = "memaudit-libero-v1/private-label-evaluation"
EVENT_PROTOCOL = "memaudit-libero-v1/observable-events"
PRIVATE_PROTOCOL = "memory-libero/external-validation-v1/private-labels"
FREEZE_PROTOCOL = "memaudit-libero-v1/execution-freeze"
METHODS = (
    "memaudit_full", "memaudit_cmis_only", "memaudit_cas_only",
    "retrieval_frequency", "random_deletion",
    "dcta_risk_local_v1", "acis_risk",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ranking(scores, key):
    return [row["memory_id"] for row in sorted(
        scores, key=lambda row: (-float(row[key]), str(row["memory_id"]))
    )]


def bootstrap(rows, left, right, budget, draws=10000):
    paired = {}
    for row in rows:
        if row["budget"] == budget:
            paired.setdefault(row["archive_id"], {})[row["method"]] = row["recall"]
    ids = sorted(key for key, values in paired.items() if left in values and right in values)
    differences = [paired[key][left] - paired[key][right] for key in ids]
    rng = random.Random(260523 + budget)
    samples = sorted(statistics.fmean(
        differences[rng.randrange(len(differences))] for _ in differences
    ) for _ in range(draws))
    return {
        "estimate": statistics.fmean(differences),
        "lower_95": samples[int(.025 * draws)],
        "upper_95": samples[int(.975 * draws)],
        "wins": sum(value > 0 for value in differences),
        "ties": sum(value == 0 for value in differences),
        "losses": sum(value < 0 for value in differences),
        "archive_count": len(ids),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--prior-evaluation", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    events = json.loads(args.events.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    prior = json.loads(args.prior_evaluation.read_text(encoding="utf-8"))
    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    if events.get("protocol") != EVENT_PROTOCOL or not events.get("complete"):
        raise ValueError("complete observable MemAudit events required")
    if private.get("protocol") != PRIVATE_PROTOCOL:
        raise ValueError("frozen private label ledger required")
    if freeze.get("protocol") != FREEZE_PROTOCOL:
        raise ValueError("MemAudit execution freeze required")
    checks = {
        "core": (args.core, freeze["sha256"]["core"]),
        "libero_adapter": (args.adapter, freeze["sha256"]["libero_adapter"]),
        "runner": (args.runner, freeze["sha256"]["runner"]),
        "configuration": (args.config, freeze["sha256"]["configuration"]),
        "public_ledger": (args.public, freeze["sha256"]["public_ledger"]),
        "physical_screen": (args.screen, freeze["sha256"]["physical_screen"]),
    }
    for name, (path, expected) in checks.items():
        if sha256(path) != expected:
            raise ValueError(f"frozen hash mismatch: {name}")
    if events["runner_sha256"] != freeze["sha256"]["runner"]:
        raise ValueError("event ledger was produced by a non-frozen runner")
    if events["public_sha256"] != freeze["sha256"]["public_ledger"]:
        raise ValueError("event ledger used a non-frozen public ledger")
    labels = {row["archive_id"]: frozenset(row["affected_ids"])
              for row in private["archives"]}
    public_archives = {
        row["archive_id"]: row
        for row in json.loads(args.public.read_text(encoding="utf-8"))["archives"]
    }
    prior_rows = [row for row in prior["rows"]
                  if row["method"] in {"dcta_risk_local_v1", "acis_risk"}]
    prior_index = {(row["archive_id"], row["budget"], row["method"]): row
                   for row in prior_rows}
    originals = {row["archive_id"]: row for row in events["original_events"]}
    post = {(row["archive_id"], row["budget"]): row
            for row in events["post_removal_events"]}
    budgets = tuple(events["config"]["declared_reconstruction_choices"]["removal_budgets"])
    rows = []
    coverage_rows = []
    for archive_id in events["harmful_archive_ids"]:
        affected = labels[archive_id]
        scores = events["rankings"][archive_id]["scores"]
        retrieved = originals[archive_id]["retrieved_ids"]
        orders = {
            "memaudit_full": [row["memory_id"] for row in scores],
            "memaudit_cmis_only": ranking(scores, "cmis"),
            "memaudit_cas_only": ranking(scores, "cas"),
            "retrieval_frequency": sorted(
                public_archives[archive_id]["candidate_ids"],
                key=lambda node: (
                    -int(node in retrieved),
                    public_archives[archive_id]["created_at"][node], node,
                ),
            ),
        }
        coverage_rows.append({
            "archive_id": archive_id,
            "affected_count": len(affected),
            "retrieved_affected_count": len(set(retrieved) & affected),
            "retrieved_affected_recall": len(set(retrieved) & affected) / len(affected),
            "nonzero_cmis_count": sum(float(row["cmis"]) > 0 for row in scores),
        })
        for budget in budgets:
            for method, order in orders.items():
                selected = order[:budget]
                hits = set(selected) & affected
                rows.append({
                    "archive_id": archive_id, "budget": budget, "method": method,
                    "selected_ids": selected, "discoveries": len(hits),
                    "recall": len(hits) / len(affected),
                })
            random_discoveries = []
            random_selections = []
            for run in range(10):
                seed = int.from_bytes(hashlib.sha256(
                    f"{PROTOCOL}|random-deletion|{archive_id}|{run}".encode()
                ).digest()[:8], "big")
                order = list(public_archives[archive_id]["candidate_ids"])
                random.Random(seed).shuffle(order)
                selected = order[:budget]
                random_selections.append(selected)
                random_discoveries.append(len(set(selected) & affected))
            rows.append({
                "archive_id": archive_id, "budget": budget,
                "method": "random_deletion",
                "selected_ids_by_run": random_selections,
                "discoveries": statistics.fmean(random_discoveries),
                "recall": statistics.fmean(
                    value / len(affected) for value in random_discoveries
                ),
                "runs": 10,
            })
            for method in ("dcta_risk_local_v1", "acis_risk"):
                source = prior_index[archive_id, budget, method]
                rows.append({
                    "archive_id": archive_id, "budget": budget, "method": method,
                    "selected_ids": source["replayed_ids"],
                    "discoveries": source["discoveries"], "recall": source["recall"],
                })
    summary = {}
    for budget in budgets:
        summary[str(budget)] = {}
        for method in METHODS:
            selected = [row for row in rows
                        if row["budget"] == budget and row["method"] == method]
            summary[str(budget)][method] = {
                "macro_recall": statistics.fmean(row["recall"] for row in selected),
                "mean_discoveries": statistics.fmean(row["discoveries"] for row in selected),
            }
    comparisons = {}
    for budget in budgets:
        comparisons[str(budget)] = {
            "memaudit_minus_dcta": bootstrap(
                rows, "memaudit_full", "dcta_risk_local_v1", budget
            ),
            "memaudit_minus_acis": bootstrap(
                rows, "memaudit_full", "acis_risk", budget
            ),
            "memaudit_minus_cas": bootstrap(
                rows, "memaudit_full", "memaudit_cas_only", budget
            ),
            "memaudit_minus_cmis": bootstrap(
                rows, "memaudit_full", "memaudit_cmis_only", budget
            ),
        }
    asr = {
        "before_all_archives": len(events["harmful_archive_ids"]) / events["archive_count"],
        "before_posthoc_subset": 1.0,
        "after_all_archives": {}, "after_posthoc_subset": {},
    }
    for budget in budgets:
        harms = [float(post[archive_id, budget]["harm"])
                 for archive_id in events["harmful_archive_ids"]]
        asr["after_posthoc_subset"][str(budget)] = statistics.fmean(harms)
        asr["after_all_archives"][str(budget)] = sum(harms) / events["archive_count"]
    payload = {
        "protocol": PROTOCOL,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True, "posthoc_extension": True,
        "events_sha256": sha256(args.events), "private_sha256": sha256(args.private),
        "prior_evaluation_sha256": sha256(args.prior_evaluation),
        "freeze_sha256": sha256(args.freeze),
        "archive_count": events["archive_count"],
        "harmful_event_archive_count": len(events["harmful_archive_ids"]),
        "mean_counterfactual_calls_per_harmful_archive": statistics.fmean(
            events["rankings"][archive_id]["counterfactual_calls"]
            for archive_id in events["harmful_archive_ids"]
        ),
        "budgets": list(budgets), "summary": summary,
        "comparisons": comparisons, "attack_success_rate": asr,
        "mean_retrieval_coverage": statistics.fmean(
            row["retrieved_affected_recall"] for row in coverage_rows
        ),
        "mean_nonzero_cmis_count": statistics.fmean(
            row["nonzero_cmis_count"] for row in coverage_rows
        ),
        "rows": rows, "coverage_rows": coverage_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in {"rows", "coverage_rows"}}, indent=2))


if __name__ == "__main__":
    main()
