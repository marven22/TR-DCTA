"""Analyze benign utility and collateral damage of task-scoped quarantine."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import statistics


BUDGETS = (2, 4, 8)
SPLITS = ("development", "validation", "test")
ALIASES = {
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


def paths(split, budget):
    if split == "development" and budget == 4:
        stem = "metaworld_recovery_development"
    else:
        stem = f"metaworld_recovery_{split}_b{budget}"
    return Path(f"results/{stem}_observable.json"), Path(f"results/{stem}_private.json")


def mean(values):
    return statistics.fmean(values) if values else None


def summarize(rows):
    output = {}
    for method in sorted({row["method"] for row in rows}):
        chosen = [row for row in rows if row["method"] == method]
        total_replays = sum(row["replay_calls"] for row in chosen)
        harmful = sum(row["harmful_replays"] for row in chosen)
        benign_replays = sum(row["benign_replays"] for row in chosen)
        candidate_count = sum(row["candidate_count"] for row in chosen)
        benign_count = sum(row["target_benign_count"] for row in chosen)
        output[method] = {
            "archive_count": len(chosen),
            "task_count": len({row["task_key"] for row in chosen}),
            "replay_calls": total_replays,
            "confirmed_harmful_replays": harmful,
            "benign_replay_calls": benign_replays,
            "audit_yield": harmful / total_replays,
            "false_quarantines": sum(row["false_quarantines"] for row in chosen),
            "target_benign_memories": benign_count,
            "target_benign_memories_retained": sum(
                row["target_benign_retained"] for row in chosen),
            "target_benign_retention": sum(
                row["target_benign_retained"] for row in chosen) / benign_count,
            "candidate_memories": candidate_count,
            "candidate_memories_retained_in_target_context": sum(
                row["target_context_retained"] for row in chosen),
            "target_context_archive_retention": sum(
                row["target_context_retained"] for row in chosen) / candidate_count,
            "clean_counterfactual_quarantines": sum(
                row["clean_counterfactual_quarantines"] for row in chosen),
            "locally_valid_memories_global_delete_would_withdraw": sum(
                row["locally_valid_global_delete_risk"] for row in chosen),
            "task_scoped_cross_context_withdrawals": 0,
            "mean_benign_replays_per_archive": mean([
                row["benign_replays"] for row in chosen]),
        }
    return output


def main() -> None:
    rows_by_split_budget = {}
    clean_policy_failures = []
    for split in SPLITS:
        aliases = ALIASES[split]
        for budget in BUDGETS:
            observable_path, private_path = paths(split, budget)
            observable = json.loads(observable_path.read_text(encoding="utf-8"))
            private = json.loads(private_path.read_text(encoding="utf-8"))
            truth_by_id = {row["archive_id"]: row for row in private["archives"]}
            rows = []
            for archive in observable["archives"]:
                truth = truth_by_id[archive["archive_id"]]
                affected = set(map(str, truth["affected_ids"]))
                candidates = set(map(str, archive["candidate_ids"]))
                benign = candidates - affected
                clean_failing = {
                    node for node in candidates
                    if not truth["success_by_policy"].get(
                        truth["clean_policy_by_memory"][node], False)
                }
                if clean_failing:
                    clean_policy_failures.append({"archive_id": archive["archive_id"],
                                                  "ids": sorted(clean_failing)})
                for source_name, method in aliases.items():
                    replayed = list(map(str, archive["replayed_ids"][source_name]))
                    removed = set(map(str, archive["quarantined_ids"][source_name]))
                    false_quarantine = removed - affected
                    locally_valid = {
                        node for node in removed
                        if truth["corrupted_policy_by_memory"][node] != "NONE"
                    }
                    rows.append({
                        "split": split, "budget": budget,
                        "archive_id": archive["archive_id"], "task_key": archive["task_key"],
                        "method": method, "replay_calls": len(replayed),
                        "harmful_replays": len(set(replayed) & affected),
                        "benign_replays": len(set(replayed) - affected),
                        "false_quarantines": len(false_quarantine),
                        "candidate_count": len(candidates),
                        "target_benign_count": len(benign),
                        "target_benign_retained": len(benign - removed),
                        "target_context_retained": len(candidates - removed),
                        "clean_counterfactual_quarantines": len(set(replayed) & clean_failing),
                        "locally_valid_global_delete_risk": len(locally_valid),
                    })
            rows_by_split_budget[split, budget] = rows

    if clean_policy_failures:
        raise ValueError(f"clean counterfactual contains failing policies: {clean_policy_failures[:3]}")
    split_results = {split: {str(budget): summarize(rows_by_split_budget[split, budget])
                             for budget in BUDGETS} for split in SPLITS}
    all_results = {}
    for budget in BUDGETS:
        pooled = sum((rows_by_split_budget[split, budget] for split in SPLITS), [])
        if len({row["task_key"] for row in pooled}) != 49:
            raise ValueError("expected 49 distinct tasks")
        all_results[str(budget)] = summarize(pooled)
    payload = {
        "protocol": "sc-dcta/metaworld-quarantine-utility-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "quarantine_scope": "target-task only",
        "split_results": split_results, "all_49_descriptive": all_results,
        "clean_counterfactual_policy_failure_count": 0,
        "rows": sum((rows_by_split_budget[key] for key in rows_by_split_budget), []),
    }
    output = Path("results/metaworld_quarantine_utility_all49.json")
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_49_sc_dcta": {
        budget: all_results[str(budget)]["sc_dcta"] for budget in BUDGETS
    }}, indent=2))


if __name__ == "__main__":
    main()
