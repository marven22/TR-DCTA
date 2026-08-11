"""Verify the frozen Meta-World archive-scalability evidence package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CONFIG = ROOT / "configs" / "metaworld_scalability_freeze_v1.json"
OUTPUT = RESULTS / "metaworld_scalability_verification.json"
SPLITS = ("development", "validation", "test")
LEGACY_METHODS = {
    "sc_dcta",
    "ens",
    "hard_source_dcta",
    "acis_risk",
    "floored_prob_dcta",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def verify() -> dict:
    config = load(CONFIG)
    checks: list[dict] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    # The frozen configuration binds the underlying archives and fitted models.
    hash_mismatches = []
    for label, expected in config["artifact_hashes"].items():
        path = ROOT / config["paths"][label]
        observed = sha256(path) if path.is_file() else None
        if observed != expected:
            hash_mismatches.append({"label": label, "expected": expected, "observed": observed})
    record("frozen_input_hashes", not hash_mismatches,
           f"{len(config['artifact_hashes'])} hashes checked; {len(hash_mismatches)} mismatches")

    audits = {split: load(RESULTS / f"metaworld_scalability_{split}.json") for split in SPLITS}
    recoveries = {
        split: load(RESULTS / f"metaworld_scalability_recovery_{split}.json")
        for split in SPLITS
    }
    expected_base = {"development": 90, "validation": 90, "test": 261}
    expected_tasks = {"development": 10, "validation": 10, "test": 29}

    grid_details = {}
    for split, audit in audits.items():
        base = expected_base[split]
        expected_rows = base * len(config["archive_sizes"]) * len(config["replay_budgets"]) * len(config["methods"])
        expected_construction = base * len(config["archive_sizes"])
        row_keys = {
            (row["archive_id"], row["provenance_missing_rate"], row["archive_size"],
             row["budget"], row["method"])
            for row in audit["rows"]
        }
        construction_keys = {
            (row["archive_id"], row["provenance_missing_rate"], row["archive_size"])
            for row in audit["construction"]
        }
        ok = (
            audit["complete"]
            and audit["base_archive_count"] == base
            and audit["task_count"] == expected_tasks[split]
            and len(audit["rows"]) == len(row_keys) == expected_rows
            and len(audit["construction"]) == len(construction_keys) == expected_construction
        )
        grid_details[split] = {
            "base_archives": base,
            "tasks": audit["task_count"],
            "rows": len(audit["rows"]),
            "construction_rows": len(audit["construction"]),
            "unique_rows": len(row_keys),
        }
        record(f"{split}_audit_grid", ok, json.dumps(grid_details[split], sort_keys=True))

        construction_ok = all(
            row["all_distractors_verified_successful"]
            and row["distractors"] == row["archive_size"] - row["original_candidates"]
            and row["original_candidates"] == 21
            for row in audit["construction"]
        )
        record(f"{split}_distractor_integrity", construction_ok,
               f"{len(audit['construction'])} nested archive constructions checked")

        # Recompute every stored summary from raw rows.
        summary_ok = True
        for key, summary in audit["summary"].items():
            selected = [
                row for row in audit["rows"]
                if row["archive_size"] == summary["archive_size"]
                and row["budget"] == summary["budget"]
                and row["provenance_missing_rate"] == summary["provenance_missing_rate"]
                and row["method"] == summary["method"]
            ]
            recomputed = {
                "weighted_recall": statistics.fmean(row["weighted_recall"] for row in selected),
                "audit_yield": statistics.fmean(row["audit_yield"] for row in selected),
                "distractor_replay_fraction": statistics.fmean(
                    row["distractor_replays"] / row["budget"] for row in selected
                ),
            }
            summary_ok = summary_ok and len(selected) == summary["archive_count"] and all(
                close(summary[field], value) for field, value in recomputed.items()
            )
            if not summary_ok:
                break
        record(f"{split}_summary_recomputation", summary_ok,
               f"{len(audit['summary'])} aggregate cells recomputed from raw rows")

    recovery_details = {}
    for split, recovery in recoveries.items():
        expected_rows = (
            recovery["exposure_episode_count"] * len(config["archive_sizes"])
            * len(config["replay_budgets"]) * len(config["methods"])
        )
        keys = {
            (row["archive_id"], row["anchor_id"], row["archive_size"], row["budget"], row["method"])
            for row in recovery["rows"]
        }
        ok = (
            recovery["task_count"] == expected_tasks[split]
            and len(recovery["rows"]) == len(keys) == expected_rows
        )
        recovery_details[split] = {
            "episodes": recovery["exposure_episode_count"],
            "rows": len(recovery["rows"]),
            "unique_rows": len(keys),
        }
        record(f"{split}_recovery_grid", ok, json.dumps(recovery_details[split], sort_keys=True))

        summary_ok = True
        for summary in recovery["summaries"].values():
            selected = [
                row for row in recovery["rows"]
                if row["archive_size"] == summary["archive_size"]
                and row["budget"] == summary["budget"]
                and row["method"] == summary["method"]
            ]
            localized = sum(bool(row["anchor_quarantined"]) for row in selected)
            recovered = sum(bool(row["post_success"]) for row in selected)
            summary_ok = summary_ok and (
                len(selected) == summary["exposure_episode_count"]
                and localized == summary["localized_count"]
                and recovered == summary["recovered_count"]
                and close(recovered / len(selected), summary["micro_recovery"])
                and close(recovered / localized if localized else 0.0,
                          summary["recovery_given_localization"])
            )
            if not summary_ok:
                break
        record(f"{split}_recovery_summary_recomputation", summary_ok,
               f"{len(recovery['summaries'])} recovery cells recomputed from episode rows")

    # At N=21, all substantive scalability methods must be a literal replay of
    # the earlier corrected-ledger experiment. Random uses a separately named,
    # deterministic scaling-study draw and is documented as an exception.
    legacy = load(RESULTS / "sc_dcta_metaworld_baselines.json")
    legacy_rows = {
        (row["archive_id"], row["provenance_missing_rate"], row["budget"], row["method"]): row
        for row in legacy["rows"] if row["method"] in LEGACY_METHODS
    }
    scale_rows = {
        (row["archive_id"], row["provenance_missing_rate"], row["budget"], row["method"]): row
        for row in audits["test"]["rows"]
        if row["archive_size"] == 21 and row["method"] in LEGACY_METHODS
    }
    exact = set(legacy_rows) == set(scale_rows) and all(
        legacy_rows[key]["replayed_ids"] == scale_rows[key]["replayed_ids"]
        and close(legacy_rows[key]["weighted_recall"], scale_rows[key]["weighted_recall"])
        and close(legacy_rows[key]["audit_yield"], scale_rows[key]["audit_yield"])
        for key in scale_rows
    )
    record("legacy_n21_substantive_methods_exact", exact,
           f"{len(scale_rows)} rows checked across {len(LEGACY_METHODS)} methods")
    record("legacy_n21_random_exception_documented", True,
           "Scalability random uses stable_digest('scalability-random', ...), whereas the legacy control used stable_digest('random', ...); it is a separate deterministic control draw.")

    old_recovery = load(RESULTS / "metaworld_forced_exposure_all49_aggregate.json")["split_results"]["test"]
    mapping = {
        "sc_dcta": "sc_dcta",
        "ens": "ens_shared_posterior",
        "hard_source_dcta": "hard_source_dcta",
        "floored_prob_dcta": "floored_prob_dcta",
    }
    recovery_exact = True
    compared = 0
    for budget in config["replay_budgets"]:
        for new_name, old_name in mapping.items():
            new = recoveries["test"]["summaries"][f"n21_b{budget}_{new_name}"]
            old = old_recovery[str(budget)]["methods"][old_name]
            recovery_exact = recovery_exact and (
                new["exposure_episode_count"] == old["exposure_episode_count"]
                and close(new["micro_recovery"], old["micro_behavioral_recovery_rate"])
                and close(new["recovery_given_localization"], old["micro_recovery_given_quarantine"])
                and close(new["task_macro_recovery"]["estimate"],
                          old["task_macro_behavioral_recovery"]["estimate"])
            )
            compared += 1
    record("legacy_n21_recovery_exact", recovery_exact,
           f"{compared} method-budget estimates checked")

    memory = load(RESULTS / "metaworld_scalability_memory_profile.json")
    memory_keys = {
        (row["archive_size"], row["provenance_missing_rate"])
        for row in memory["memory_profiles"]
    }
    expected_memory_keys = {
        (size, mask) for size in config["archive_sizes"]
        for mask in config["provenance_missing_rates"]
    }
    record("memory_profile_grid", memory_keys == expected_memory_keys,
           f"{len(memory_keys)} representative size/mask profiles present")

    passed = all(check["passed"] for check in checks)
    output = {
        "protocol": "sc-dcta/metaworld-scalability-verification-v1",
        "passed": passed,
        "check_count": len(checks),
        "passed_count": sum(check["passed"] for check in checks),
        "failed_count": sum(not check["passed"] for check in checks),
        "checks": checks,
        "hash_mismatches": hash_mismatches,
        "scope_note": "This verifies frozen inputs, grid completeness, uniqueness, aggregate arithmetic, distractor integrity flags, legacy N=21 reproduction, and memory-profile coverage. It does not independently rerun every simulator trajectory.",
    }
    return output


def main() -> None:
    output = verify()
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("passed", "check_count", "passed_count", "failed_count")}, indent=2))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
