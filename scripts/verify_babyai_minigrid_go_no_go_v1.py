"""Verify the BabyAI/MiniGrid go/no-go artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "babyai_minigrid_go_no_go_freeze_v1.json"
REPORT = ROOT / "reports" / "babyai_minigrid_go_no_go_v1.json"
VERIFIED = ROOT / "reports" / "babyai_minigrid_go_no_go_verified_v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--output", type=Path, default=VERIFIED)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    q = config["qualification"]
    outcomes = report["outcomes"]
    transfers = report["transfers"]
    local_correct = [
        row for row in outcomes
        if row["strategy_color"] == row["target_color"] and row["success"]
    ]
    harmful_transfers = [row for row in transfers if row["harmful_transfer"]]
    by_target = defaultdict(list)
    for row in outcomes:
        by_target[row["seed"]].append(row)
    targets_with_recovery = {
        seed for seed, rows in by_target.items()
        if sum(row["strategy_color"] == row["target_color"] and row["success"] for row in rows)
        >= int(q["minimum_recovery_alternatives"])
    }
    recomputed_counts = {
        "contexts": len(report["contexts"]),
        "target_colors": len({row["target_color"] for row in report["contexts"]}),
        "outcomes": len(outcomes),
        "errors": len(report["errors"]),
        "local_correct_outcomes": len(local_correct),
        "family_target_transfers": len(transfers),
        "harmful_family_target_transfers": len(harmful_transfers),
        "targets_with_harm": len({row["target_seed"] for row in harmful_transfers}),
        "targets_with_recovery": len(targets_with_recovery),
        "harmful_source_colors": len({row["source_color"] for row in harmful_transfers}),
    }
    recomputed_gates = {
        "execution": len(outcomes) >= int(q["minimum_completed_outcomes"]) and not report["errors"],
        "context_coverage": len(report["contexts"]) >= int(q["minimum_contexts"])
        and recomputed_counts["target_colors"] >= int(q["minimum_target_colors"]),
        "local_correctness": len(local_correct) >= int(q["minimum_local_correct_outcomes"]),
        "harmful_transfers": len(harmful_transfers)
        >= int(q["minimum_harmful_family_target_transfers"]),
        "target_harm_coverage": recomputed_counts["targets_with_harm"]
        >= int(q["minimum_targets_with_harm"]),
        "recovery": len(targets_with_recovery) >= int(q["minimum_targets_with_recovery"]),
        "source_diversity": recomputed_counts["harmful_source_colors"]
        >= int(q["minimum_harmful_source_colors"]),
        "determinism": len(report["repeat_checks"]) >= int(q["minimum_repeat_checks"])
        and all(row["success_match"] and row["reward_match"] and row["steps_match"] for row in report["repeat_checks"]),
    }
    checks = {
        "protocol_matches": report["protocol"] == config["protocol"],
        "method_blind": not report["uses_sc_dcta"] and not report["uses_baselines"],
        "counts_reproduced": report["counts"] == recomputed_counts,
        "gates_reproduced": report["gates"] == recomputed_gates,
        "decision_reproduced": report["decision"] == ("GO" if all(recomputed_gates.values()) else "NO_GO"),
    }
    verified = {
        "verified": all(checks.values()),
        "decision": report["decision"],
        "checks": checks,
        "recomputed_counts": recomputed_counts,
        "recomputed_gates": recomputed_gates,
        "sha256": {
            "freeze_config": sha256(args.config),
            "raw_report": sha256(args.report),
        },
    }
    args.output.write_text(json.dumps(verified, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verified, indent=2))
    if not verified["verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
