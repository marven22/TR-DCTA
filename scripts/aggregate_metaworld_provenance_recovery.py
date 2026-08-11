"""Aggregate recovery and utility across provenance missingness conditions."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics


SPLITS = ("development", "validation", "test")
MASKS = (0.0, .25, .5)
BUDGETS = (2, 4, 8)
ALIASES = {
    "development": {"sc_dcta": "sc_dcta", "sc_ens": "ens_shared_posterior",
                    "hard_source_dcta": "hard_source_dcta",
                    "sc_source_then_dcta": "source_then_dcta",
                    "floored_prob_dcta": "floored_prob_dcta",
                    "known_source_dcta": "known_source_dcta",
                    "full_information_oracle": "full_information_oracle"},
    "validation": {name: name for name in (
        "sc_dcta", "hard_source_dcta", "source_then_dcta", "floored_prob_dcta",
        "known_source_dcta", "full_information_oracle")} | {"ens": "ens_shared_posterior"},
    "test": {name: name for name in (
        "sc_dcta", "hard_source_dcta", "source_then_dcta", "floored_prob_dcta",
        "known_source_dcta", "full_information_oracle")} | {"ens": "ens_shared_posterior"},
}


def stems(split, mask, budget):
    if mask == .25:
        if split == "development" and budget == 4:
            stem = "metaworld_recovery_development"
            evaluation = "metaworld_forced_exposure_development_evaluation.json"
        else:
            stem = f"metaworld_recovery_{split}_b{budget}"
            evaluation = f"metaworld_forced_exposure_{split}_b{budget}_evaluation.json"
    else:
        tag = "m0" if mask == 0 else "m50"
        stem = f"metaworld_recovery_{split}_{tag}_b{budget}"
        evaluation = f"metaworld_forced_exposure_{split}_{tag}_b{budget}_evaluation.json"
    return (Path(f"results/{stem}_observable.json"),
            Path(f"results/{stem}_private.json"), Path("results") / evaluation)


def mean(values):
    return statistics.fmean(values) if values else None


def task_means(rows, field="post_success"):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["task_key"], []).append(float(row[field]))
    return {task: mean(values) for task, values in grouped.items()}


def interval(values_by_task, draws=10_000, seed=85031):
    tasks = sorted(values_by_task); values = [values_by_task[t] for t in tasks]
    rng = random.Random(seed)
    samples = sorted(mean([values[rng.randrange(len(values))] for _ in values])
                     for _ in range(draws))
    return {"estimate": mean(values), "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[int(.975 * draws)], "task_count": len(tasks)}


def recovery_summary(rows):
    output = {}
    for method in sorted({row["method"] for row in rows}):
        chosen = [row for row in rows if row["method"] == method]
        localized = [row for row in chosen if row["anchor_quarantined"]]
        output[method] = {
            "exposure_count": len(chosen),
            "localized_count": len(localized),
            "recovered_count": sum(row["post_success"] for row in chosen),
            "micro_localization_rate": mean([float(row["anchor_quarantined"]) for row in chosen]),
            "micro_recovery_rate": mean([float(row["post_success"]) for row in chosen]),
            "recovery_given_localization": mean([float(row["post_success"]) for row in localized]),
            "harmful_fallback_count": sum(row["fallback_still_harmful"] for row in chosen),
            "task_macro_recovery": interval(task_means(chosen)),
        }
    return output


def utility_summary(observable, private, aliases):
    truth = {row["archive_id"]: set(row["affected_ids"]) for row in private["archives"]}
    output = {}
    for source_method, method in aliases.items():
        replay_calls = harmful = benign = false = retained = candidates = 0
        for archive in observable["archives"]:
            affected = truth[archive["archive_id"]]
            replayed = set(archive["replayed_ids"][source_method])
            removed = set(archive["quarantined_ids"][source_method])
            all_ids = set(archive["candidate_ids"]); benign_ids = all_ids - affected
            replay_calls += len(replayed); harmful += len(replayed & affected)
            benign += len(replayed - affected); false += len(removed - affected)
            retained += len(benign_ids - removed); candidates += len(benign_ids)
        output[method] = {"replay_calls": replay_calls, "harmful_replays": harmful,
                          "benign_replays": benign, "audit_yield": harmful / replay_calls,
                          "false_quarantines": false,
                          "target_benign_retained": retained,
                          "target_benign_count": candidates}
    return output


def robustness(rows_by_condition, splits, budget):
    methods = sorted({row["method"] for split in splits
                      for row in rows_by_condition[split, 0.0, budget]})
    output = {}
    per_method_delta = {}
    for method in methods:
        zero = sum(([r for r in rows_by_condition[split, 0.0, budget]
                     if r["method"] == method] for split in splits), [])
        half = sum(([r for r in rows_by_condition[split, .5, budget]
                     if r["method"] == method] for split in splits), [])
        z, h = task_means(zero), task_means(half)
        tasks = sorted(set(z) & set(h))
        delta = {task: h[task] - z[task] for task in tasks}
        per_method_delta[method] = delta
        output[method] = {"mask_0_task_macro": mean(z.values()),
                          "mask_50_task_macro": mean(h.values()),
                          "change_50_minus_0": interval(delta)}
    sc = per_method_delta["sc_dcta"]
    output["sc_dcta_difference_in_change"] = {}
    for method, values in per_method_delta.items():
        if method == "sc_dcta":
            continue
        tasks = sorted(set(sc) & set(values))
        contrast = {task: sc[task] - values[task] for task in tasks}
        output["sc_dcta_difference_in_change"][method] = interval(contrast, seed=85032)
    return output


def main() -> None:
    rows_by_condition = {}; cells = {}
    for split in SPLITS:
        aliases = ALIASES[split]
        for mask in MASKS:
            for budget in BUDGETS:
                observable_path, private_path, evaluation_path = stems(split, mask, budget)
                observable = json.loads(observable_path.read_text(encoding="utf-8"))
                private = json.loads(private_path.read_text(encoding="utf-8"))
                evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
                rows = [{**row, "method": aliases[row["method"]], "split": split,
                         "mask": mask, "budget": budget} for row in evaluation["rows"]
                        if row["method"] in aliases]
                rows_by_condition[split, mask, budget] = rows
                cells[f"{split}|{mask:.2f}|{budget}"] = {
                    "recovery": recovery_summary(rows),
                    "utility": utility_summary(observable, private, aliases),
                }
    payload = {
        "protocol": "sc-dcta/metaworld-provenance-recovery-results-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_test_robustness": robustness(rows_by_condition, ("test",), 4),
        "test_budget_sensitivity": {
            str(budget): robustness(rows_by_condition, ("test",), budget)
            for budget in BUDGETS
        },
        "all_49_descriptive_robustness": robustness(rows_by_condition, SPLITS, 4),
        "cells": cells,
    }
    output = Path("results/metaworld_provenance_recovery_all_masks.json")
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"primary_test_robustness": payload["primary_test_robustness"],
                      "all_49_descriptive_robustness": payload["all_49_descriptive_robustness"]},
                     indent=2))


if __name__ == "__main__":
    main()
