"""Aggregate publication-facing Meta-World scalability findings."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics


RESULTS = Path("results")
OUTPUT = RESULTS / "metaworld_scalability_analysis.json"


def mean(values):
    return statistics.fmean(values)


def bootstrap_task_difference(values_by_task, draws=10_000, seed=260806):
    tasks = sorted(values_by_task)
    differences = [values_by_task[task] for task in tasks]
    rng = random.Random(seed)
    samples = sorted(mean(differences[rng.randrange(len(differences))]
                          for _ in differences) for _ in range(draws))
    return {"estimate": mean(differences),
            "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[int(.975 * draws)],
            "task_count": len(tasks)}


def audit_size_change(audit, method, small=21, large=200, budget=4, mask=.25):
    grouped = {}
    for row in audit["rows"]:
        if row["method"] != method or row["budget"] != budget \
                or row["provenance_missing_rate"] != mask \
                or row["archive_size"] not in {small, large}:
            continue
        grouped.setdefault(row["task_key"], {}).setdefault(row["archive_size"], []).append(
            row["weighted_recall"]
        )
    differences = {
        task: mean(values[large]) - mean(values[small])
        for task, values in grouped.items() if small in values and large in values
    }
    return bootstrap_task_difference(differences, seed=260806 + large)


def recovery_difference(recovery, left_method, right_method=None,
                        left_size=200, right_size=21, budget=4):
    grouped = {}
    for row in recovery["rows"]:
        left = row["method"] == left_method and row["archive_size"] == left_size
        if right_method is None:
            right = row["method"] == left_method and row["archive_size"] == right_size
        else:
            right = row["method"] == right_method and row["archive_size"] == right_size
        if row["budget"] != budget or not (left or right):
            continue
        side = "left" if left else "right"
        grouped.setdefault(row["task_key"], {}).setdefault(side, []).append(
            float(row["post_success"])
        )
    differences = {
        task: mean(values["left"]) - mean(values["right"])
        for task, values in grouped.items() if {"left", "right"} <= set(values)
    }
    return bootstrap_task_difference(differences, seed=260906 + left_size + right_size)


def main() -> None:
    audits = {split: json.loads((RESULTS / f"metaworld_scalability_{split}.json").read_text(encoding="utf-8"))
              for split in ("development", "validation", "test")}
    recoveries = {split: json.loads((RESULTS / f"metaworld_scalability_recovery_{split}.json").read_text(encoding="utf-8"))
                  for split in ("development", "validation", "test")}
    memory = json.loads((RESULTS / "metaworld_scalability_memory_profile.json").read_text(encoding="utf-8"))
    sizes = audits["test"]["archive_sizes"]
    methods = audits["test"]["methods"]
    primary = {}
    for split, audit in audits.items():
        primary[split] = {
            str(size): {
                method: audit["summary"][f"n{size}_b4_m0.25_{method}"]
                for method in methods
            }
            for size in sizes
        }
    recovery_primary = {}
    for split, recovery in recoveries.items():
        recovery_primary[split] = {
            str(size): {
                method: recovery["summaries"][f"n{size}_b4_{method}"]
                for method in methods
            }
            for size in sizes
        }
    test = audits["test"]
    test_recovery = recoveries["test"]
    construction = {}
    for size in sizes:
        selected = [row for row in test["construction"]
                    if row["archive_size"] == size
                    and row["provenance_missing_rate"] == .25]
        construction[str(size)] = {
            "archive_count": len(selected),
            "all_distractors_verified_successful": all(
                row["all_distractors_verified_successful"] for row in selected
            ),
            "mean_distractor_marginal": mean(row["mean_distractor_marginal"] for row in selected),
            "mean_harmful_marginal": mean(row["mean_harmful_marginal"] for row in selected),
            "mean_posterior_seconds_shared_load": mean(row["posterior_seconds"] for row in selected),
            "mean_posterior_worlds": mean(row["posterior_worlds"] for row in selected),
        }
    profiles = {
        f"n{row['archive_size']}_m{row['provenance_missing_rate']:.2f}": row
        for row in memory["memory_profiles"]
    }
    output = {
        "protocol": "sc-dcta/metaworld-scalability-analysis-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_accuracy": primary,
        "primary_recovery": recovery_primary,
        "test_size_change_200_minus_21": {
            method: audit_size_change(test, method) for method in methods
        },
        "test_sc_dcta_primary_comparisons_at_200": {
            method: test["primary_comparisons"][f"n200_sc_minus_{method}"]
            for method in methods if method != "sc_dcta"
        },
        "test_recovery_change_sc_200_minus_21": recovery_difference(
            test_recovery, "sc_dcta"
        ),
        "test_recovery_sc_minus_ens_at_200": recovery_difference(
            test_recovery, "sc_dcta", "ens", left_size=200, right_size=200,
        ),
        "test_sc_recovery_budget_200": {
            str(budget): test_recovery["summaries"][f"n200_b{budget}_sc_dcta"]
            for budget in (2, 4, 8)
        },
        "construction_primary_test": construction,
        "memory_profiles": profiles,
        "runtime_note": "Acquisition and posterior wall times in full split ledgers were recorded under shared parallel CPU load; use within-run scaling ratios, not standalone latency claims.",
        "input_paths": [
            f"results/metaworld_scalability_{split}.json" for split in audits
        ] + [f"results/metaworld_scalability_recovery_{split}.json" for split in recoveries]
          + ["results/metaworld_scalability_memory_profile.json"],
    }
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "sc_accuracy_change": output["test_size_change_200_minus_21"]["sc_dcta"],
        "sc_recovery_change": output["test_recovery_change_sc_200_minus_21"],
        "sc_minus_ens_200": output["test_sc_dcta_primary_comparisons_at_200"]["ens"],
        "recovery_sc_minus_ens_200": output["test_recovery_sc_minus_ens_at_200"],
    }, indent=2))


if __name__ == "__main__":
    main()
