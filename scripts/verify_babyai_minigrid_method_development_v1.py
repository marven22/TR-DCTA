"""Independently verify the BabyAI/MiniGrid method-development artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from run_babyai_minigrid_go_no_go_v1 import execute


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "babyai_minigrid_method_development_v1.json"
OUTPUT = ROOT / "reports" / "babyai_minigrid_method_development_verified_v1.json"
CONFIG = ROOT / "configs" / "babyai_minigrid_method_development_freeze_v1.json"
PROTOCOL = ROOT / "docs" / "BABYAI_MINIGRID_METHOD_DEVELOPMENT_PROTOCOL_V1.md"
RUNNER = ROOT / "scripts" / "run_babyai_minigrid_method_development_v1.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean_for(rows: list[dict], method: str, budget: int) -> float:
    values = [float(row["corrupt_descendant_recall"]) for row in rows
              if row["method"] == method and int(row["budget"]) == budget]
    return sum(values) / len(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    rows = report["rows"]
    archives = report["archives"]
    structured = tuple(method for method in config["methods"] if method != "random")
    budgets = tuple(map(int, config["budgets"]))
    expected_structured = 60 * len(structured) * len(budgets)
    expected_random = 60 * int(config["random_replicates"]) * len(budgets)

    structured_keys = [
        (row["archive_id"], int(row["budget"]), row["method"])
        for row in rows if row["method"] != "random"
    ]
    random_keys = [
        (row["archive_id"], int(row["budget"]), int(row["replicate"]))
        for row in rows if row["method"] == "random"
    ]
    environment_truth_valid = all(
        (node in set(archive["affected_ids"])) == (not bool(value["success"]))
        for archive in archives for node, value in archive["replay_map"].items()
    )
    row_labels_valid = all(
        row["labels"] == [int(node in set(next(
            archive["affected_ids"] for archive in archives
            if archive["archive_id"] == row["archive_id"]
        ))) for node in row["replayed_ids"]]
        for row in rows
    )

    # Re-execute a fixed, evenly spaced sample rather than trusting cached outcomes.
    repeat_checks = []
    for archive in archives[::5]:
        node = sorted(archive["replay_map"])[0]
        cached = archive["replay_map"][node]
        again = execute(
            config["env_id"], int(archive["target_seed"]),
            cached["behavior_color"], cached["variant"], int(config["max_steps"]),
        )
        repeat_checks.append({
            "archive_id": archive["archive_id"],
            "node_id": node,
            "success_match": bool(again["success"]) == bool(cached["success"]),
            "reward_match": math.isclose(float(again["reward"]), float(cached["reward"])),
            "steps_match": int(again["steps"]) == int(cached["steps"]),
        })

    sc4 = mean_for(rows, "sc_dcta", 4)
    ens4 = mean_for(rows, "ens", 4)
    random4 = mean_for(rows, "random", 4)
    primary = report["primary_budget_4_comparison"]
    checks = {
        "schema_valid": report["schema_version"] == "babyai-minigrid-method-development-v1",
        "frozen_hashes_match": report["artifact_hashes"] == {
            "config": digest(CONFIG), "protocol": digest(PROTOCOL), "runner": digest(RUNNER)
        },
        "archive_count_60": len(archives) == 60,
        "regimes_balanced": Counter(a["regime"] for a in archives)
        == Counter({name: 15 for name in config["confidence_regimes"]}),
        "environment_truth_valid": environment_truth_valid,
        "local_correctness_valid": len(report["local_checks"]) == 180
        and all(row["success"] for row in report["local_checks"]),
        "structured_grid_complete": len(structured_keys) == expected_structured
        and len(set(structured_keys)) == expected_structured,
        "random_grid_complete": len(random_keys) == expected_random
        and len(set(random_keys)) == expected_random,
        "row_labels_valid": row_labels_valid,
        "budgets_exact": all(len(row["replayed_ids"]) == int(row["budget"]) for row in rows),
        "replays_unique": all(len(row["replayed_ids"]) == len(set(row["replayed_ids"]))
                              for row in rows),
        "repeat_executions_exact": len(repeat_checks) == 12 and all(
            row["success_match"] and row["reward_match"] and row["steps_match"]
            for row in repeat_checks
        ),
        "primary_metrics_recomputed": all((
            math.isclose(sc4, float(primary["sc_dcta"]), abs_tol=1e-12),
            math.isclose(ens4, float(primary["ens"]), abs_tol=1e-12),
            math.isclose(random4, float(primary["random"]), abs_tol=1e-12),
        )),
        "decision_recomputed": report["decision"] == (
            "GO" if sc4 >= ens4 - 1e-12 and sc4 > random4 + 1e-12 else "NO_GO"
        ),
    }
    verified = all(checks.values())
    output = {
        "schema_version": "babyai-minigrid-method-development-verification-v1",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "verified": verified,
        "report_sha256": digest(args.report),
        "checks": checks,
        "recomputed_primary_budget_4": {
            "sc_dcta": sc4, "ens": ens4, "random": random4,
        },
        "repeat_checks": repeat_checks,
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
