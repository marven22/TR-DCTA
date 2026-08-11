"""Independently verify the BabyAI UnlockPickup structural audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from run_babyai_unlockpickup_go_no_go_v1 import execute


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "babyai_unlockpickup_go_no_go_v1.json"
OUTPUT = ROOT / "reports" / "babyai_unlockpickup_go_no_go_verified_v1.json"
CONFIG = ROOT / "configs" / "babyai_unlockpickup_go_no_go_freeze_v1.json"
PROTOCOL = ROOT / "docs" / "BABYAI_UNLOCKPICKUP_GO_NO_GO_PROTOCOL_V1.md"
RUNNER = ROOT / "scripts" / "run_babyai_unlockpickup_go_no_go_v1.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    outcomes = report["outcomes"]
    colors = tuple(config["source_colors"])
    variants = tuple(config["descendant_variants"])
    keys = [(row["seed"], row["source_color"], row["variant"]) for row in outcomes]
    matching = [row for row in outcomes if not row["mismatch"]]
    harmful = [row for row in outcomes if row["mismatch"]]

    groups = defaultdict(dict)
    for row in harmful:
        groups[(row["seed"], row["source_color"])][row["variant"]] = row
    ordering_valid = all(
        values["early_bind"]["steps"] < values["post_unlock_bind"]["steps"]
        < values["terminal_bind"]["steps"]
        for values in groups.values()
    )
    milestone_valid = all(
        (row["variant"] != "early_bind" or row["milestones"]["required_key_acquired"])
        and (row["variant"] != "post_unlock_bind"
             or row["milestones"]["required_door_opened"])
        and (row["variant"] != "terminal_bind"
             or row["milestones"]["target_box_reached"])
        for row in harmful
    )

    # Re-execute one matching and two mismatching source families for each target
    # color, spanning all descendant stages, without trusting cached actions.
    repeat_rows = []
    for target in colors:
        seed = min(row["seed"] for row in matching if row["target_color"] == target)
        selected_sources = (target,) + tuple(color for color in colors if color != target)[:2]
        for source, variant in zip(selected_sources, variants):
            cached = next(row for row in outcomes if row["seed"] == seed
                          and row["source_color"] == source and row["variant"] == variant)
            again = execute(config["env_id"], seed, source, variant)
            repeat_rows.append({
                "seed": seed, "target_color": target, "source_color": source,
                "variant": variant,
                "success_match": cached["success"] == again["success"],
                "steps_match": cached["steps"] == again["steps"],
                "stop_reason_match": cached["stop_reason"] == again["stop_reason"],
                "actions_match": cached["actions"] == again["actions"],
                "milestones_match": cached["milestones"] == again["milestones"],
            })

    checks = {
        "schema_protocol_decision_valid": report["schema_version"]
        == "babyai-unlockpickup-go-no-go-v1"
        and report["protocol"] == config["protocol"] and report["decision"] == "GO",
        "frozen_artifacts_present": CONFIG.exists() and PROTOCOL.exists() and RUNNER.exists(),
        "grid_complete_unique": len(outcomes) == 1080 and len(set(keys)) == 1080
        and set(keys) == {(seed, source, variant) for seed in range(60)
                          for source in colors for variant in variants},
        "six_target_colors": set(row["target_color"] for row in outcomes) == set(colors),
        "matching_correct": len(matching) == 180 and all(row["success"] for row in matching),
        "mismatched_harmful": len(harmful) == 900 and all(
            not row["success"] and row["stop_reason"] == "source_guard_abort"
            for row in harmful),
        "stage_milestones_valid": milestone_valid,
        "strict_order_valid": len(groups) == 300 and ordering_valid,
        "distractors_valid": all(row["object_profile"]["distractor_count"] >= 4
                                 for row in outcomes),
        "donor_checks_valid": len(report["donor_checks"]) == 18
        and all(row["success"] for row in report["donor_checks"]),
        "stored_repeat_checks_valid": len(report["repeat_checks"]) == 30
        and all(all(value for key, value in row.items() if key.endswith("_match"))
                for row in report["repeat_checks"]),
        "independent_reexecution_exact": len(repeat_rows) == 18 and all(
            all(value for key, value in row.items() if key.endswith("_match"))
            for row in repeat_rows),
        "reported_gates_all_true": all(report["gates"].values()),
    }
    verified = all(checks.values())
    output = {
        "schema_version": "babyai-unlockpickup-go-no-go-verification-v1",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "verified": verified, "report_sha256": digest(args.report),
        "artifact_hashes": {"config": digest(CONFIG), "protocol": digest(PROTOCOL),
                            "runner": digest(RUNNER)},
        "checks": checks,
        "reexecuted_cases": len(repeat_rows),
        "target_color_counts": dict(Counter(row["target_color"] for row in matching)),
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
