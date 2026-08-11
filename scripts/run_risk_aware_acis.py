"""Run the frozen V7 cross-fitted risk-aware ACIS development study."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
import random

import _bootstrap

from mcx.memoryarena_v6 import (
    adaptive_replay,
    build_task_matched_cases,
    formation_contexts_for_unit,
    mask_edges_with_forced_hidden_direct,
)
from mcx.risk_aware_acis import (
    ThreeSignalIndex,
    adaptive_three_signal_replay,
    fit_monotone_logistic,
    oracle_prefix_training_rows,
)


PROTOCOL_VERSION = "memoryarena-v7.1/cascade-impact-ablation-v1"
BUDGETS = (5, 10, 13, 20, 49)
METHODS = (
    "acis_text_only", "acis", "acis_trajectory",
    "acis_3", "acis_probability", "acis_risk",
    "acis_impact",
)


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _prefix_metrics(score_log, affected_ids):
    affected = set(affected_ids)
    recalls = {}
    confirmed = set()
    full_curve = []
    replay_order = []
    replay_outcomes = []
    for entry in score_log:
        chosen = entry["chosen_id"]
        outcome = bool(entry["replay_affected"])
        replay_order.append(chosen)
        replay_outcomes.append(outcome)
        if outcome:
            confirmed.add(chosen)
        full_curve.append(len(confirmed & affected) / len(affected))
        if len(full_curve) in BUDGETS:
            recalls[str(len(full_curve))] = full_curve[-1]
    return {
        "recall_by_budget": recalls,
        "recall_cost_area": _mean(full_curve),
        "precision": 1.0 if confirmed else 0.0,
        "replay_order": replay_order,
        "replay_outcomes": replay_outcomes,
    }


def _bootstrap_difference(
    rows, left, right, budget="13", group_field="base_case_id", seed=42, draws=10000
):
    by_archive = {}
    for row in rows:
        difference = (
            row["methods"][left]["recall_by_budget"][budget]
            - row["methods"][right]["recall_by_budget"][budget]
        )
        by_archive.setdefault(row[group_field], []).append(difference)
    archive_values = [_mean(by_archive[key]) for key in sorted(by_archive)]
    rng = random.Random(seed)
    samples = sorted(
        _mean(archive_values[rng.randrange(len(archive_values))] for _ in archive_values)
        for _ in range(draws)
    )
    return {
        "estimate": _mean(archive_values),
        "lower": samples[int(0.025 * draws)],
        "upper": samples[int(0.975 * draws) - 1],
        "group_field": group_field,
        "group_count": len(archive_values),
    }


def _calibration(initial_predictions):
    if not initial_predictions:
        raise ValueError("no calibration predictions")
    brier = _mean((probability - label) ** 2 for probability, label in initial_predictions)
    bins = [[] for _ in range(10)]
    for probability, label in initial_predictions:
        bins[min(9, int(probability * 10))].append((probability, label))
    ece = sum(
        len(bucket) / len(initial_predictions)
        * abs(_mean(value[0] for value in bucket) - _mean(value[1] for value in bucket))
        for bucket in bins if bucket
    )
    return {
        "initial_candidate_brier": brier,
        "initial_candidate_ece_10_bin": ece,
        "prediction_count": len(initial_predictions),
        "positive_rate": _mean(label for _, label in initial_predictions),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation-dir", required=True)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    generation_dir = os.path.abspath(args.generation_dir)
    summary = _read(os.path.join(generation_dir, "generation_summary.json"))
    attack_dir = summary["manifest"]["source_attack_dir"]
    units = [
        _read(os.path.join(generation_dir, "units", name))
        for name in sorted(os.listdir(os.path.join(generation_dir, "units")))
        if name.endswith(".json")
    ]
    contexts = {
        unit["unit_id"]: formation_contexts_for_unit(
            unit, _read(os.path.join(attack_dir, "units", f"{unit['unit_id']}.json"))
        )
        for unit in units
    }
    unit_by_id = {unit["unit_id"]: unit for unit in units}
    constructed = build_task_matched_cases(units, contexts)
    masked_cases = []
    for base_case, metadata in constructed:
        unit = unit_by_id[metadata["unit_id"]]
        metadata = {
            **metadata,
            "candidate_family": unit["candidate_id"],
        }
        for mask_seed in range(10):
            masked, mask = mask_edges_with_forced_hidden_direct(
                base_case, 0.75, mask_seed, metadata["direct_child_id"]
            )
            masked_cases.append((masked, metadata, mask_seed, mask))

    families = sorted({metadata["candidate_family"] for _, metadata, _, _ in masked_cases})
    all_training_rows = Counter()
    rows_by_family = {family: Counter() for family in families}
    archives_by_family = {family: set() for family in families}
    for case, metadata, _, _ in masked_cases:
        case_rows = oracle_prefix_training_rows(case)
        all_training_rows.update(case_rows)
        rows_by_family[metadata["candidate_family"]].update(case_rows)
        archives_by_family[metadata["candidate_family"]].add(metadata["case_id"])
    calibrators = {}
    training_counts = {}
    for held_family in families:
        rows = all_training_rows.copy()
        rows.subtract(rows_by_family[held_family])
        rows = Counter({key: count for key, count in rows.items() if count > 0})
        calibrators[held_family] = fit_monotone_logistic(rows, l2=0.01)
        training_counts[held_family] = {
            "training_archive_count": 30 - len(archives_by_family[held_family]),
            "weighted_training_row_count": sum(rows.values()),
            "unique_training_row_count": len(rows),
        }

    results = []
    initial_predictions = []
    for index, (case, metadata, mask_seed, mask) in enumerate(masked_cases, 1):
        calibrator = calibrators[metadata["candidate_family"]]
        source_only = {case.source_id}
        signal_index = ThreeSignalIndex(case)
        for memory in case.memories:
            if memory.memory_id == case.source_id:
                continue
            probability = calibrator.probability(
                signal_index.signals(memory.memory_id, source_only)
            )
            initial_predictions.append((probability, int(memory.memory_id in case.affected_ids)))

        trajectories = {
            "acis_text_only": adaptive_replay(
                case, 49, 42, use_exposure=False, use_trajectory=False
            ),
            "acis": adaptive_replay(
                case, 49, 42, use_exposure=True, use_trajectory=False
            ),
            "acis_trajectory": adaptive_replay(
                case, 49, 42, use_exposure=True, use_trajectory=True
            ),
            "acis_3": adaptive_three_signal_replay(case, 49, "acis_3", seed=42),
            "acis_probability": adaptive_three_signal_replay(
                case, 49, "acis_probability", calibrator, 42
            ),
            "acis_impact": adaptive_three_signal_replay(
                case, 49, "acis_impact", calibrator, 42
            ),
            "acis_risk": adaptive_three_signal_replay(
                case, 49, "acis_risk", calibrator, 42
            ),
        }
        method_metrics = {
            method: _prefix_metrics(trajectory["score_log"], case.affected_ids)
            for method, trajectory in trajectories.items()
        }
        for method in METHODS:
            replayed_at_13 = set(method_metrics[method]["replay_order"][:13])
            method_metrics[method]["descendant_hit_at_13"] = {
                role.split(":")[1]: float(opaque_id in replayed_at_13)
                for role, opaque_id in metadata["role_to_opaque_id"].items()
                if role in {"core:m2", "core:m4", "core:m5", "core:m6"}
            }
        results.append({
            "base_case_id": metadata["case_id"],
            "masked_case_id": case.case_id,
            "unit_id": metadata["unit_id"],
            "candidate_family": metadata["candidate_family"],
            "attack_type": metadata["attack_type"],
            "mask_seed": mask_seed,
            "remaining_missing_fraction_realized": mask[
                "remaining_missing_fraction_realized"
            ],
            "methods": method_metrics,
        })
        if index % 25 == 0:
            print(f"evaluated {index}/{len(masked_cases)} case-mask pairs", flush=True)

    macro = {
        method: {
            "recall_by_budget": {
                str(budget): _mean(
                    row["methods"][method]["recall_by_budget"][str(budget)]
                    for row in results
                )
                for budget in BUDGETS
            },
            "recall_cost_area": _mean(
                row["methods"][method]["recall_cost_area"] for row in results
            ),
            "precision": _mean(
                row["methods"][method]["precision"] for row in results
            ),
        }
        for method in METHODS
    }
    by_attack = {
        attack: {
            method: _mean(
                row["methods"][method]["recall_by_budget"]["13"]
                for row in results if row["attack_type"] == attack
            )
            for method in METHODS
        }
        for attack in ("evidence_substitution", "evidence_swap")
    }
    by_descendant = {
        method: {
            descendant: _mean(
                row["methods"][method]["descendant_hit_at_13"][descendant]
                for row in results
            )
            for descendant in ("m2", "m4", "m5", "m6")
        }
        for method in METHODS
    }
    comparisons = {
        method: _bootstrap_difference(results, method, "acis_trajectory")
        for method in ("acis_3", "acis_probability", "acis_impact", "acis_risk")
    }
    coefficient_mean = {
        key: _mean(model.as_dict()[key] for model in calibrators.values())
        for key in ("intercept", "provenance", "formation_task", "content")
    }
    baseline_reproduced = (
        abs(macro["acis_text_only"]["recall_by_budget"]["13"] - 0.800) < 1e-12
        and abs(macro["acis"]["recall_by_budget"]["13"] - 0.8016666666666666) < 1e-12
        and abs(macro["acis_trajectory"]["recall_by_budget"]["13"] - 0.860) < 1e-12
    )
    v7_new_methods_reproduced = (
        abs(macro["acis_3"]["recall_by_budget"]["13"] - 0.875) < 1e-12
        and abs(macro["acis_probability"]["recall_by_budget"]["13"] - 0.835) < 1e-12
        and abs(macro["acis_risk"]["recall_by_budget"]["13"] - 0.9216666666666666) < 1e-12
        and abs(macro["acis_risk"]["recall_cost_area"] - 0.8709523809523809) < 1e-12
    )
    risk_recall = macro["acis_risk"]["recall_by_budget"]["13"]
    risk_gain = risk_recall - macro["acis_trajectory"]["recall_by_budget"]["13"]
    risk_auc = macro["acis_risk"]["recall_cost_area"]
    impact_recall = macro["acis_impact"]["recall_by_budget"]["13"]
    impact_auc = macro["acis_impact"]["recall_cost_area"]
    main_budgets = (5, 10, 13, 20)
    impact_within_two_each_budget = all(
        macro["acis_impact"]["recall_by_budget"][str(budget)]
        >= macro["acis_risk"]["recall_by_budget"][str(budget)] - 0.02
        for budget in main_budgets
    )
    impact_within_auc_margin = impact_auc >= risk_auc - 0.005
    prefer_impact = (
        impact_within_two_each_budget
        and impact_within_auc_margin
        and macro["acis_impact"]["precision"] == 1.0
    )
    retain_risk = (
        risk_recall - impact_recall > 0.02
        and risk_auc > impact_auc
    )
    surviving_complex_method = (
        "acis_impact" if prefer_impact
        else "acis_risk" if retain_risk
        else "unresolved"
    )
    prefer_acis_3 = False
    if surviving_complex_method != "unresolved":
        prefer_acis_3 = (
            all(
                macro["acis_3"]["recall_by_budget"][str(budget)]
                >= macro[surviving_complex_method]["recall_by_budget"][str(budget)] - 0.02
                for budget in main_budgets
            )
            and macro["acis_3"]["recall_cost_area"]
            >= macro[surviving_complex_method]["recall_cost_area"] - 0.005
        )
    gates = {
        "frozen_baselines_reproduced": baseline_reproduced,
        "v7_new_methods_reproduced": v7_new_methods_reproduced,
        "risk_recall_at_least_086": risk_recall >= 0.860,
        "risk_gain_at_least_003": risk_gain >= 0.03,
        "risk_bootstrap_lower_nonnegative": comparisons["acis_risk"]["lower"] >= 0.0,
        "risk_auc_exceeds_all_frozen_acis": risk_auc > max(
            macro[method]["recall_cost_area"]
            for method in ("acis_text_only", "acis", "acis_trajectory")
        ),
        "risk_swap_not_below_acis_t": (
            by_attack["evidence_swap"]["acis_risk"]
            >= by_attack["evidence_swap"]["acis_trajectory"]
        ),
        "risk_precision_one": macro["acis_risk"]["precision"] == 1.0,
    }
    gates["promote_risk_to_heldout"] = all(gates.values())
    aggregate = {
        "protocol_version": PROTOCOL_VERSION,
        "scientific_result": False,
        "development_cohort": True,
        "archive_count": 30,
        "archive_mask_pairs": len(results),
        "candidate_family_count": len(families),
        "archive_size": 50,
        "replay_candidates": 49,
        "budgets": list(BUDGETS),
        "cross_fitting": "leave-one-source-candidate-family-out",
        "macro": macro,
        "budget_13_by_attack": by_attack,
        "budget_13_by_descendant": by_descendant,
        "paired_budget_13_vs_acis_t_bootstrap_95": comparisons,
        "posthoc_candidate_family_cluster_sensitivity": {
            method: _bootstrap_difference(
                results, method, "acis_trajectory", group_field="candidate_family"
            )
            for method in ("acis_3", "acis_probability", "acis_impact", "acis_risk")
        },
        "calibration": _calibration(initial_predictions),
        "cross_fitted_calibrators": {
            family: {
                "coefficients": calibrators[family].as_dict(),
                **training_counts[family],
            }
            for family in families
        },
        "mean_coefficients": coefficient_mean,
        "gains": {
            "risk_minus_acis_t_at_13": risk_gain,
            "risk_auc_minus_acis_t": (
                risk_auc - macro["acis_trajectory"]["recall_cost_area"]
            ),
            "impact_minus_risk_at_13": impact_recall - risk_recall,
            "impact_auc_minus_risk": impact_auc - risk_auc,
        },
        "impact_ablation_decision": {
            "impact_within_two_points_at_every_main_budget": impact_within_two_each_budget,
            "impact_within_0005_recall_cost_area": impact_within_auc_margin,
            "prefer_impact": prefer_impact,
            "retain_risk": retain_risk,
            "surviving_complex_method": surviving_complex_method,
            "prefer_acis_3_over_survivor": prefer_acis_3,
            "selected_method": (
                "acis_3" if prefer_acis_3 else surviving_complex_method
            ),
        },
        "gates": gates,
        "run": {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_generation_dir": generation_dir,
        },
    }
    output_dir = os.path.abspath(
        args.output_dir
        or os.path.join(_bootstrap.RESULTS_DIR, "memoryarena_v7_risk_aware")
    )
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "cases.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    with open(os.path.join(output_dir, "aggregate.json"), "w", encoding="utf-8") as handle:
        json.dump(aggregate, handle, indent=2)
    print(json.dumps(aggregate, indent=2))
    print(f"results: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
