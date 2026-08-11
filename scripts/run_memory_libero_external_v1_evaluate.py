"""Frozen evaluator for Memory-LIBERO external validation v1."""
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

from mcx.causal_regime_benchmark import RegimeInstance, expected_outcomes
from mcx.directional_transition import (
    CascadeWorld, DirectionalPosterior, LocalTransitionParameters,
    build_local_directional_posterior, greedy_choice, risk_choice,
)
from mcx.memorepair import Artifact, plan_repair
from mcx.memory_libero_external import join_archive
from mcx.memory_libero_v041 import (
    FrontierParameters, discovery_case, evaluate_method, static_probabilities,
)
from mcx.risk_aware_acis import (
    LogisticCalibrator, ThreeSignalIndex, adaptive_three_signal_replay,
)


PROTOCOL = "memory-libero/external-validation-v1/evaluation"
PUBLIC_PROTOCOL = "memory-libero/external-validation-v1/public"
PRIVATE_PROTOCOL = "memory-libero/external-validation-v1/private-labels"
BUDGETS = (2, 4, 6, 9)
PRIMARY_BUDGET = 4
BASE_METHODS = (
    "random", "raw_content", "graph_reachability", "static_source_probability",
    "acis_probability", "acis_risk", "causal_oracle", "full_replay",
)
DCTA_METHODS = ("dcta_probability", "dcta_risk_local_v1")


def canonical_hash(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def load_acis(path: Path) -> LogisticCalibrator:
    value = json.loads(path.read_text(encoding="utf-8"))["coefficients"]
    return LogisticCalibrator(
        value["intercept"], value["provenance"],
        value["formation_task"], value["content"],
    )


def load_dcta(path: Path) -> LocalTransitionParameters:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("protocol") != "dcta-risk-local-v1/final-transition-freeze":
        raise ValueError("frozen DCTA-Risk-Local v1 parameters required")
    return LocalTransitionParameters(**artifact["parameters"])


def metrics(archive, replayed):
    hits = set(replayed) & archive.affected_ids
    deep = archive.affected_ids - archive.direct_gateways
    return {
        "replayed_ids": list(replayed), "discoveries": len(hits),
        "recall": len(hits) / len(archive.affected_ids) if archive.affected_ids else 1.0,
        "deep_recall": len(hits & deep) / len(deep) if deep else 1.0,
        "audit_yield": len(hits) / len(replayed) if replayed else 0.0,
        "residual_invalid_exposure": (
            len(archive.affected_ids) - len(hits)
        ) / len(archive.candidate_ids),
    }


def dcta_trace(posterior, affected, budget, acquisition):
    current = posterior
    remaining = list(posterior.candidates)
    replayed, trace = [], []
    for step in range(min(budget, len(remaining))):
        chosen = (greedy_choice(current, remaining) if acquisition == "probability"
                  else risk_choice(current, remaining))
        probability = current.marginal(chosen)
        label = int(chosen in affected)
        trace.append({
            "step": step + 1, "chosen_id": chosen,
            "probability_before_replay": probability, "label": label,
            "selected_brier": (probability - label) ** 2,
        })
        replayed.append(chosen)
        remaining.remove(chosen)
        current = current.condition(chosen, label)
        if current is None:
            raise ValueError("external label has zero DCTA posterior support")
    return tuple(replayed), trace


def descendants(archive):
    children = {}
    for parent, child in archive.true_edges:
        children.setdefault(parent, set()).add(child)
    output = {}
    for start in archive.memories:
        found, queue = set(), list(children.get(start, ()))
        while queue:
            node = queue.pop(0)
            if node in found:
                continue
            found.add(node)
            queue.extend(children.get(node, ()))
        output[start] = found
    return output


def strata(archive):
    desc = descendants(archive)
    clean = set(archive.candidate_ids) - archive.affected_ids
    negative_screening = any(
        desc[node] and bool(archive.affected_ids - desc[node]) for node in clean
    )
    parent_count = {node: 0 for node in archive.memories}
    for _, child in archive.true_edges:
        parent_count[child] += 1
    return {
        "negative_screening": negative_screening,
        "deep_cascade": bool(archive.affected_ids - archive.direct_gateways),
        "affected_merge": any(parent_count[node] >= 2 for node in archive.affected_ids),
    }


def project_posterior(posterior, size=12):
    candidates = posterior.candidates[:size]
    allowed = set(candidates)
    masses = {}
    for world in posterior.worlds:
        labels = frozenset(world.affected_ids & allowed)
        masses[labels] = masses.get(labels, 0.0) + world.weight
    return DirectionalPosterior(
        candidates,
        tuple(CascadeWorld(labels, weight) for labels, weight in sorted(
            masses.items(), key=lambda item: tuple(sorted(item[0]))
        )),
    ).normalize()


def memo_repair_scope(archive):
    artifacts = {node: Artifact(node, value=1.0, cost=1.0)
                 for node in archive.memories}
    plan = plan_repair(artifacts, archive.true_edges, {archive.source_id}, .3)
    scope = set(plan.descendants)
    affected = set(archive.affected_ids)
    return {
        "scope_recall": len(scope & affected) / len(affected) if affected else 1.0,
        "collateral_scope_count": len(scope - affected),
        "selected_operator_count": len(plan.selected),
        "republished_count": len(plan.republished),
    }


def bootstrap_difference(rows, left, right, draws=10000):
    values = []
    by_archive = {}
    for row in rows:
        by_archive.setdefault(row["archive_id"], {})[row["method"]] = row["recall"]
    archives = sorted(key for key, value in by_archive.items()
                      if left in value and right in value)
    differences = [by_archive[key][left] - by_archive[key][right] for key in archives]
    rng = random.Random(9041)
    for _ in range(draws):
        values.append(statistics.fmean(
            differences[rng.randrange(len(differences))] for _ in differences
        ))
    values.sort()
    return {
        "estimate": statistics.fmean(differences),
        "lower_95": values[int(.025 * draws)],
        "upper_95": values[int(.975 * draws)],
        "archive_count": len(archives),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--dcta-config", type=Path, required=True)
    parser.add_argument("--acis-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    if public.get("protocol") != PUBLIC_PROTOCOL or private.get("protocol") != PRIVATE_PROTOCOL:
        raise ValueError("external-v1 public/private ledgers required")
    if private.get("public_payload_sha256") != canonical_hash(public):
        raise ValueError("public ledger does not match private labels")
    expected_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if private.get("evaluator_sha256_before_label_join") != expected_hash:
        raise ValueError("evaluator changed after private-label split")
    labels = {row["archive_id"]: row for row in private["archives"]}
    archives = [join_archive(row, labels[row["archive_id"]]) for row in public["archives"]]
    dcta_parameters = load_dcta(args.dcta_config)
    acis_calibrator = load_acis(args.acis_config)
    dummy = FrontierParameters(0.0, 1.0, 0.0, 1.0)
    rows, diagnostics, memo_rows, oracle_rows = [], [], [], []
    for index, archive in enumerate(archives, start=1):
        started = time.perf_counter()
        posterior = build_local_directional_posterior(archive, dcta_parameters)
        truth_support = any(world.affected_ids == archive.affected_ids
                            for world in posterior.worlds)
        if not truth_support:
            raise ValueError(f"truth outside frozen DCTA support: {archive.archive_id}")
        archive_strata = strata(archive)
        case = discovery_case(archive)
        signal_index = ThreeSignalIndex(case)
        static = static_probabilities(archive, acis_calibrator)
        dcta_initial_brier = statistics.fmean(
            (posterior.marginal(node) - int(node in archive.affected_ids)) ** 2
            for node in archive.candidate_ids
        )
        acis_initial_brier = statistics.fmean(
            (static[node] - int(node in archive.affected_ids)) ** 2
            for node in archive.candidate_ids
        )
        traces = {}
        for budget in BUDGETS:
            for method in BASE_METHODS:
                result = evaluate_method(
                    archive, acis_calibrator, method, budget, dummy, dummy
                )
                rows.append({
                    "archive_id": archive.archive_id, "budget": budget,
                    "method": method, "affected_count": len(archive.affected_ids),
                    **archive_strata, **result,
                })
            for method, acquisition in (("dcta_probability", "probability"),
                                        ("dcta_risk_local_v1", "risk")):
                replayed, trace = dcta_trace(
                    posterior, archive.affected_ids, budget, acquisition
                )
                traces[method, budget] = trace
                rows.append({
                    "archive_id": archive.archive_id, "budget": budget,
                    "method": method, "affected_count": len(archive.affected_ids),
                    **archive_strata, **metrics(archive, replayed),
                    "selected_brier": statistics.fmean(item["selected_brier"] for item in trace),
                })
        acis_trace = adaptive_three_signal_replay(
            case, PRIMARY_BUDGET, "acis_risk", acis_calibrator, seed=42
        )["score_log"]
        diagnostics.append({
            "archive_id": archive.archive_id, "world_count": len(posterior.worlds),
            "truth_support": truth_support, **archive_strata,
            "dcta_initial_brier": dcta_initial_brier,
            "acis_initial_brier": acis_initial_brier,
            "dcta_selected_brier": statistics.fmean(
                item["selected_brier"] for item in traces["dcta_risk_local_v1", PRIMARY_BUDGET]
            ),
            "acis_selected_brier": statistics.fmean(
                (float(item["probability_before_replay"]) - int(item["replay_affected"])) ** 2
                for item in acis_trace
            ),
            "elapsed_seconds": time.perf_counter() - started,
        })
        memo_rows.append({"archive_id": archive.archive_id, **archive_strata,
                          **memo_repair_scope(archive)})
        # Six nodes keeps exact enumeration practical for 67 external archives;
        # the protocol permits induced graphs of at most 12. The primary
        # empirical evaluation still uses all 18 candidates.
        projected = project_posterior(posterior, 6)
        model_outcomes = expected_outcomes(RegimeInstance(
            archive.archive_id, "libero_90", 0, projected,
            {node: 1.0 for node in projected.candidates}, PRIMARY_BUDGET,
        ))
        oracle = model_outcomes["exact_bayes_oracle"]["expected_weighted_utility"]
        oracle_rows.append({
            "archive_id": archive.archive_id,
            "oracle_value": oracle,
            "dcta_risk_value": model_outcomes["dcta_risk"]["expected_weighted_utility"],
            "positive_only_risk_value": model_outcomes["positive_only_risk"]["expected_weighted_utility"],
            "dcta_regret": oracle - model_outcomes["dcta_risk"]["expected_weighted_utility"],
            "positive_only_regret": oracle - model_outcomes["positive_only_risk"]["expected_weighted_utility"],
        })
        print(f"evaluated {index}/{len(archives)} {archive.archive_id}", flush=True)
    positive_primary = [row for row in rows if row["budget"] == PRIMARY_BUDGET
                        and row["affected_count"] > 0]
    methods = (*BASE_METHODS, *DCTA_METHODS)
    summary = {method: {
        "macro_recall": statistics.fmean(
            row["recall"] for row in positive_primary if row["method"] == method
        ),
        "mean_discoveries": statistics.fmean(
            row["discoveries"] for row in rows
            if row["budget"] == PRIMARY_BUDGET and row["method"] == method
        ),
    } for method in methods}
    primary_difference = bootstrap_difference(
        positive_primary, "dcta_risk_local_v1", "acis_risk"
    )
    negative_rows = [row for row in positive_primary if row["negative_screening"]]
    outside_rows = [row for row in positive_primary if not row["negative_screening"]]
    negative_difference = bootstrap_difference(
        negative_rows, "dcta_risk_local_v1", "acis_risk"
    ) if negative_rows else None
    outside_difference = bootstrap_difference(
        outside_rows, "dcta_risk_local_v1", "acis_risk"
    ) if outside_rows else None
    oracle_dcta = statistics.fmean(row["dcta_regret"] for row in oracle_rows)
    oracle_positive = statistics.fmean(row["positive_only_regret"] for row in oracle_rows)
    checks = {
        "overall_within_003_of_acis": primary_difference["estimate"] >= -.03,
        "higher_in_negative_screening": (
            negative_difference is not None and negative_difference["estimate"] > 0
        ),
        "lower_exact_oracle_regret": oracle_dcta < oracle_positive,
        "outside_negative_screening_within_003": (
            outside_difference is None or outside_difference["estimate"] >= -.03
        ),
        "sample_size_gate": len(archives) >= 60 and len({
            row["archive_id"] for row in positive_primary
        }) >= 20,
    }
    payload = {
        "protocol": PROTOCOL, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": True, "public_sha256": hashlib.sha256(args.public.read_bytes()).hexdigest(),
        "private_sha256": hashlib.sha256(args.private.read_bytes()).hexdigest(),
        "dcta_config_sha256": hashlib.sha256(args.dcta_config.read_bytes()).hexdigest(),
        "acis_config_sha256": hashlib.sha256(args.acis_config.read_bytes()).hexdigest(),
        "strict_archive_count": len(archives),
        "positive_archive_count": len({row["archive_id"] for row in positive_primary}),
        "primary_budget": PRIMARY_BUDGET, "budgets": list(BUDGETS),
        "summary": summary, "primary_difference": primary_difference,
        "negative_screening_difference": negative_difference,
        "outside_negative_screening_difference": outside_difference,
        "oracle_regret": {"dcta_risk": oracle_dcta,
                          "positive_only_risk": oracle_positive},
        "success_gate": {"passed": all(checks.values()), "checks": checks},
        "rows": rows, "diagnostics": diagnostics,
        "memorepair_scope": memo_rows, "induced_oracle": oracle_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items()
                      if key not in {"rows", "diagnostics", "memorepair_scope", "induced_oracle"}},
                     indent=2))


if __name__ == "__main__":
    main()
