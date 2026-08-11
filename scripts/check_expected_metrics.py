"""Compare reproduced aggregate reports with compact paper-facing expectations."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path,
                        default=Path("expected/paper_metrics_v1.json"))
    parser.add_argument("--metaworld", type=Path)
    parser.add_argument("--babyai-unlockpickup", type=Path)
    parser.add_argument("--babyai-opendoorcolor", type=Path)
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    if args.metaworld:
        report = json.loads(args.metaworld.read_text(encoding="utf-8"))
        target = expected["metaworld"]
        checks["metaworld_status"] = report["status"] == "EXECUTABLE"
        checks["metaworld_counts"] = (
            report["summaries"]["test"]["tr_dcta"]["episodes"] == target["episodes"]
            and report["counts"]["tasks"] == target["all49"]["tasks"]
            and report["counts"]["archives"] == target["all49"]["archives"])
        for method, count in target["recovery_counts"].items():
            checks[f"test_recovery_{method}"] = (
                report["summaries"]["test"][method]["behavioral_recovery_count"] == count)
        checks["all49_tr_recovery"] = (
            report["summaries"]["all49"]["tr_dcta"]["behavioral_recovery_count"]
            == target["all49"]["tr_dcta_recoveries"])
        comparisons = {(row["left"], row["right"], row["metric"]): row
                       for row in report["paired_bootstrap"]["test"]}
        for label, right in (("sc_dcta", "sc_dcta"), ("sc_ens", "sc_ens")):
            actual = comparisons[("tr_dcta", right, "post_success")]
            wanted = target["task_clustered_recovery_differences"][
                f"tr_dcta_minus_{label}"]
            checks[f"bootstrap_{label}"] = all(
                close(actual[key], wanted[key])
                for key in ("estimate", "lower_95", "upper_95"))
    if args.babyai_unlockpickup:
        report = json.loads(args.babyai_unlockpickup.read_text(encoding="utf-8"))
        target = expected["babyai_unlockpickup"]
        rows = {(row["condition"], row["method"], int(row["budget"])): row
                for row in report["summary"]}
        method_names = {name: name for name in target["recovery_rates"]}
        method_names["known_source_dcta"] = "oracle_source"
        for expected_name, wanted in target["recovery_rates"].items():
            method = method_names[expected_name]
            values = [rows[(condition, method, int(target["primary_budget"]))]
                      ["mean_robot_recovery_success"]
                      for condition in target["primary_views"]]
            checks[f"unlockpickup_{expected_name}"] = close(sum(values) / len(values), wanted)
    if args.babyai_opendoorcolor:
        report = json.loads(args.babyai_opendoorcolor.read_text(encoding="utf-8"))
        target = expected["babyai_opendoorcolor"]
        rows = {(row["condition"], row["method"], int(row["budget"])): row
                for row in report["summary"]}
        for condition, methods in target["recovery_counts"].items():
            for method, wanted in methods.items():
                row = rows[(condition, method, int(target["budget"]))]
                actual = round(float(row["mean_robot_recovery_success"]) * int(row["runs"]))
                checks[f"opendoorcolor_{condition}_{method}"] = actual == wanted
    if not checks:
        parser.error("provide at least one reproduced report")
    output = {"verified": all(checks.values()), "checks": checks}
    print(json.dumps(output, indent=2))
    return 0 if output["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
