"""Post-hoc frozen ENS/Graph Active Search extension on LIBERO-90."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

import _bootstrap

from mcx.active_search_baselines import (
    GraphActiveSearch,
    GraphActiveSearchParameters,
    run_ens_policy,
)
from mcx.directional_transition import (
    LocalTransitionParameters,
    build_local_directional_posterior,
)
from mcx.memory_libero_external import join_archive


PROTOCOL = "memory-libero/external-validation-v1/active-search-extension"
ACTIVE_CONFIG_PROTOCOL = "active-search-baselines-v1/development-freeze"
BUDGETS = (2, 4, 6, 9)
PRIMARY_BUDGET = 4
METHODS = (
    "dcta_risk_local_v1",
    "acis_risk",
    "ens_shared_dcta_posterior",
    "graph_active_search",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def load_dcta(path: Path) -> LocalTransitionParameters:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("protocol") != "dcta-risk-local-v1/final-transition-freeze":
        raise ValueError("frozen DCTA configuration required")
    return LocalTransitionParameters(**value["parameters"])


def metrics(archive, replayed):
    hits = set(replayed) & archive.affected_ids
    deep = archive.affected_ids - archive.direct_gateways
    return {
        "replayed_ids": list(replayed),
        "discoveries": len(hits),
        "recall": len(hits) / len(archive.affected_ids) if archive.affected_ids else 1.0,
        "deep_recall": len(hits & deep) / len(deep) if deep else 1.0,
        "audit_yield": len(hits) / len(replayed) if replayed else 0.0,
        "residual_invalid_exposure": (
            len(archive.affected_ids) - len(hits)
        ) / len(archive.candidate_ids),
    }


def bootstrap(rows, left, right, budget, draws=10000):
    selected = [row for row in rows if row["budget"] == budget]
    by_archive = {}
    for row in selected:
        by_archive.setdefault(row["archive_id"], {})[row["method"]] = row["recall"]
    archives = sorted(a for a, values in by_archive.items() if left in values and right in values)
    differences = [by_archive[a][left] - by_archive[a][right] for a in archives]
    rng = random.Random(19041 + budget)
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
        "archive_count": len(archives),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--prior-evaluation", type=Path, required=True)
    parser.add_argument("--active-config", type=Path, required=True)
    parser.add_argument("--dcta-config", type=Path, required=True)
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    prior = json.loads(args.prior_evaluation.read_text(encoding="utf-8"))
    active = json.loads(args.active_config.read_text(encoding="utf-8"))
    if active.get("protocol") != ACTIVE_CONFIG_PROTOCOL:
        raise ValueError("frozen active-search configuration required")
    if active["implementation"]["sha256"] != sha256(args.implementation):
        raise ValueError("active-search implementation differs from frozen hash")
    if private.get("public_payload_sha256") != canonical_hash(public):
        raise ValueError("public and private LIBERO ledgers do not match")
    if not prior.get("complete") or prior.get("strict_archive_count") != 67:
        raise ValueError("completed 67-archive prior evaluation required")
    if prior.get("public_sha256") != sha256(args.public):
        raise ValueError("prior evaluation used a different public ledger")
    if prior.get("private_sha256") != sha256(args.private):
        raise ValueError("prior evaluation used a different private ledger")

    labels = {row["archive_id"]: row for row in private["archives"]}
    archives = [join_archive(row, labels[row["archive_id"]]) for row in public["archives"]]
    dcta = load_dcta(args.dcta_config)
    graph_config = active["graph_active_search"]
    baseline_rows = [row for row in prior["rows"]
                     if row["method"] in {"dcta_risk_local_v1", "acis_risk"}]
    rows = list(baseline_rows)
    timing = []
    first_actions = []
    for index, archive in enumerate(archives, start=1):
        started = time.perf_counter()
        posterior = build_local_directional_posterior(archive, dcta)
        graph = GraphActiveSearch(
            tuple(sorted(archive.memories, key=archive.created_at.get)),
            archive.true_edges,
            {archive.source_id: 1},
            GraphActiveSearchParameters(
                eta=graph_config["eta"],
                prior_strength=None,
                prior_probability=graph_config["prior_probability"],
                alpha=graph_config["selected_alpha"],
            ),
        )
        graph_path = graph.run(archive.candidate_ids, archive.affected_ids, max(BUDGETS))
        for budget in BUDGETS:
            ens_path = run_ens_policy(posterior, archive.affected_ids, budget)
            for method, replayed in (
                ("ens_shared_dcta_posterior", ens_path),
                ("graph_active_search", graph_path[:budget]),
            ):
                rows.append({
                    "archive_id": archive.archive_id,
                    "budget": budget,
                    "method": method,
                    "affected_count": len(archive.affected_ids),
                    **metrics(archive, replayed),
                })
        first = {row["method"]: row["replayed_ids"][0]
                 for row in rows if row["archive_id"] == archive.archive_id
                 and row["budget"] == PRIMARY_BUDGET}
        first_actions.append({
            "archive_id": archive.archive_id,
            "ens_equals_dcta": first["ens_shared_dcta_posterior"] == first["dcta_risk_local_v1"],
            "ens_equals_acis": first["ens_shared_dcta_posterior"] == first["acis_risk"],
            "graph_equals_dcta": first["graph_active_search"] == first["dcta_risk_local_v1"],
        })
        timing.append({"archive_id": archive.archive_id,
                       "elapsed_seconds": time.perf_counter() - started})
        print(f"evaluated {index}/{len(archives)} {archive.archive_id}", flush=True)

    expected = len(archives) * len(BUDGETS) * len(METHODS)
    if len(rows) != expected:
        raise ValueError(f"incomplete method grid: {len(rows)} != {expected}")
    summary = {}
    for budget in BUDGETS:
        summary[str(budget)] = {}
        for method in METHODS:
            selected = [r for r in rows if r["budget"] == budget and r["method"] == method]
            summary[str(budget)][method] = {
                "macro_recall": statistics.fmean(r["recall"] for r in selected),
                "mean_discoveries": statistics.fmean(r["discoveries"] for r in selected),
                "mean_audit_yield": statistics.fmean(r["audit_yield"] for r in selected),
            }
    comparisons = {}
    for budget in BUDGETS:
        comparisons[str(budget)] = {
            "ens_minus_dcta": bootstrap(
                rows, "ens_shared_dcta_posterior", "dcta_risk_local_v1", budget
            ),
            "ens_minus_acis": bootstrap(
                rows, "ens_shared_dcta_posterior", "acis_risk", budget
            ),
            "graph_minus_dcta": bootstrap(
                rows, "graph_active_search", "dcta_risk_local_v1", budget
            ),
            "graph_minus_acis": bootstrap(
                rows, "graph_active_search", "acis_risk", budget
            ),
        }
    payload = {
        "protocol": PROTOCOL,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True,
        "posthoc_extension": True,
        "posthoc_note": (
            "External labels were already evaluated in the parent study; baseline code and "
            "parameters were frozen from papers and the old development set before this run."
        ),
        "evaluator_sha256": sha256(Path(__file__)),
        "public_sha256": sha256(args.public),
        "private_sha256": sha256(args.private),
        "prior_evaluation_sha256": sha256(args.prior_evaluation),
        "active_config_sha256": sha256(args.active_config),
        "dcta_config_sha256": sha256(args.dcta_config),
        "implementation_sha256": sha256(args.implementation),
        "archive_count": len(archives),
        "budgets": list(BUDGETS),
        "primary_budget": PRIMARY_BUDGET,
        "methods": list(METHODS),
        "summary": summary,
        "comparisons": comparisons,
        "first_action_agreement": {
            key: sum(row[key] for row in first_actions) / len(first_actions)
            for key in ("ens_equals_dcta", "ens_equals_acis", "graph_equals_dcta")
        },
        "mean_new_baseline_seconds_per_archive": statistics.fmean(
            row["elapsed_seconds"] for row in timing
        ),
        "rows": rows,
        "timing": timing,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": True,
        "summary": summary,
        "comparisons": comparisons,
        "first_action_agreement": payload["first_action_agreement"],
        "mean_seconds_per_archive": payload["mean_new_baseline_seconds_per_archive"],
    }, indent=2))


if __name__ == "__main__":
    main()
