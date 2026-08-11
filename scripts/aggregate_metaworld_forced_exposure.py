"""Aggregate frozen forced-exposure results without erasing split boundaries."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics


BUDGETS = (2, 4, 8)
SPLITS = ("development", "validation", "test")
METHOD_MAP = {
    "development": {
        "sc_dcta": "sc_dcta", "sc_ens": "ens_shared_posterior",
        "hard_source_dcta": "hard_source_dcta",
        "sc_source_then_dcta": "source_then_dcta",
        "floored_prob_dcta": "floored_prob_dcta",
        "known_source_dcta": "known_source_dcta",
        "full_information_oracle": "full_information_oracle",
    },
    "validation": {name: name for name in (
        "sc_dcta", "hard_source_dcta", "source_then_dcta",
        "floored_prob_dcta", "known_source_dcta", "full_information_oracle")}
        | {"ens": "ens_shared_posterior"},
    "test": {name: name for name in (
        "sc_dcta", "hard_source_dcta", "source_then_dcta",
        "floored_prob_dcta", "known_source_dcta", "full_information_oracle")}
        | {"ens": "ens_shared_posterior"},
}


def path_for(split, budget):
    if split == "development" and budget == 4:
        return Path("results/metaworld_forced_exposure_development_evaluation.json")
    return Path(f"results/metaworld_forced_exposure_{split}_b{budget}_evaluation.json")


def mean(values):
    return statistics.fmean(values) if values else None


def task_values(rows, field):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["task_key"], []).append(float(row[field]))
    return {task: mean(values) for task, values in grouped.items()}


def bootstrap(values_by_task, draws=10_000, seed=260806):
    tasks = sorted(values_by_task)
    values = [values_by_task[task] for task in tasks]
    rng = random.Random(seed)
    samples = sorted(mean([values[rng.randrange(len(values))] for _ in values])
                     for _ in range(draws))
    return {"estimate": mean(values), "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[int(.975 * draws)], "task_count": len(tasks)}


def paired_bootstrap(rows, left, right, draws=10_000, seed=260807):
    selected = {method: task_values([r for r in rows if r["method"] == method],
                                    "post_success") for method in (left, right)}
    tasks = sorted(set(selected[left]) & set(selected[right]))
    differences = {task: selected[left][task] - selected[right][task] for task in tasks}
    return bootstrap(differences, draws, seed)


def summarize(rows):
    output = {}
    for method in sorted({row["method"] for row in rows}):
        chosen = [row for row in rows if row["method"] == method]
        quarantined = [row for row in chosen if row["anchor_quarantined"]]
        output[method] = {
            "exposure_episode_count": len(chosen),
            "task_count": len({row["task_key"] for row in chosen}),
            "micro_anchor_quarantine_rate": mean([
                float(row["anchor_quarantined"]) for row in chosen]),
            "micro_behavioral_recovery_rate": mean([
                float(row["post_success"]) for row in chosen]),
            "micro_recovery_given_quarantine": mean([
                float(row["post_success"]) for row in quarantined]),
            "task_macro_behavioral_recovery": bootstrap(
                task_values(chosen, "post_success")),
            "harmful_fallback_count": sum(row["fallback_still_harmful"] for row in chosen),
        }
    return output


def main() -> None:
    rows_by_split_budget = {}
    input_paths = []
    for split in SPLITS:
        aliases = METHOD_MAP[split]
        for budget in BUDGETS:
            path = path_for(split, budget); input_paths.append(str(path))
            value = json.loads(path.read_text(encoding="utf-8"))
            rows = []
            for row in value["rows"]:
                if row["method"] not in aliases:
                    continue
                rows.append({**row, "method": aliases[row["method"]],
                             "split": split, "budget": budget})
            rows_by_split_budget[split, budget] = rows

    split_results = {}
    all_results = {}
    for split in SPLITS:
        split_results[split] = {}
        for budget in BUDGETS:
            rows = rows_by_split_budget[split, budget]
            split_results[split][str(budget)] = {
                "methods": summarize(rows),
                "sc_dcta_minus_ens_shared_posterior": paired_bootstrap(
                    rows, "sc_dcta", "ens_shared_posterior"),
            }
    for budget in BUDGETS:
        rows = sum((rows_by_split_budget[split, budget] for split in SPLITS), [])
        if len({row["task_key"] for row in rows}) != 49:
            raise ValueError("pooled result must contain exactly 49 tasks")
        all_results[str(budget)] = {
            "methods": summarize(rows),
            "sc_dcta_minus_ens_shared_posterior": paired_bootstrap(
                rows, "sc_dcta", "ens_shared_posterior"),
        }
    payload = {
        "protocol": "sc-dcta/metaworld-forced-exposure-aggregate-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_result": "test task-macro",
        "all_49_task_result_status": "descriptive; development and validation influenced method construction",
        "budgets": list(BUDGETS), "split_task_counts": {
            "development": 10, "validation": 10, "test": 29, "all": 49},
        "split_results": split_results, "all_49_descriptive": all_results,
        "input_paths": input_paths,
    }
    output = Path("results/metaworld_forced_exposure_all49_aggregate.json")
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"test": split_results["test"],
                      "all_49_descriptive": all_results}, indent=2))


if __name__ == "__main__":
    main()
