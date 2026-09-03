"""Compute cluster-bootstrap uncertainty for the frozen RQ1 results."""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
METHODS = ("lantern", "cacwr", "immediate_harm")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interval(values: dict[str, dict[str, float]], method: str, draws: int, seed: int) -> dict[str, float | int]:
    ids = sorted(values)
    observations = [values[item][method] for item in ids]
    rng = random.Random(seed)
    samples = sorted(
        statistics.fmean(observations[rng.randrange(len(observations))] for _ in observations)
        for _ in range(draws)
    )
    return {"estimate": statistics.fmean(observations), "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[min(int(.975 * draws), draws - 1)], "clusters": len(ids)}


def paired(values: dict[str, dict[str, float]], right: str, draws: int, seed: int) -> dict[str, float | int]:
    ids = sorted(values)
    observations = [values[item]["lantern"] - values[item][right] for item in ids]
    rng = random.Random(seed)
    samples = sorted(
        statistics.fmean(observations[rng.randrange(len(observations))] for _ in observations)
        for _ in range(draws)
    )
    return {"estimate": statistics.fmean(observations), "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[min(int(.975 * draws), draws - 1)], "clusters": len(ids),
            "wins": sum(item > 0 for item in observations), "ties": sum(item == 0 for item in observations),
            "losses": sum(item < 0 for item in observations)}


def meta_values(report: dict, condition: str) -> dict[tuple[str, int], dict[str, dict[str, float]]]:
    output: dict[tuple[str, int], dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    names = {"lantern": "lantern", "dcta_risk": "cacwr", "immediate_harm": "immediate_harm"}
    for source, target in names.items():
        for budget, rows in report["episode_rows"][source].items():
            for row in rows:
                output[(condition, int(budget))][row["task_key"]][target].append(float(row["post_success"]))
    return {key: {task: {method: statistics.fmean(scores) for method, scores in method_scores.items()}
                  for task, method_scores in task_values.items()}
            for key, task_values in output.items()}


def baby_values(report: dict) -> dict[tuple[str, str, int], dict[str, dict[str, float]]]:
    output: dict[tuple[str, str, int], dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    names = {"lantern": "lantern", "cascade_aware_continuation": "cacwr", "immediate_harm": "immediate_harm"}
    for row in report["rows"]:
        if row["method"] not in names:
            continue
        output[(row["family"], row["condition"], int(row["budget"]))][row["archive_id"]][names[row["method"]]] = float(row["robot_recovery_success"])
    return dict(output)


def complete(values: dict[str, dict[str, float]]) -> bool:
    return bool(values) and all(set(item) == set(METHODS) for item in values.values())


def main() -> int:
    source_paths = {
        "metaworld_partial_25": ROOT / "reports/metaworld_theory_alignment_partial25_v1.json",
        "metaworld_partial_50": ROOT / "reports/metaworld_theory_alignment_v1.json",
        "babyai": ROOT / "reports/babyai_rq1_theory_alignment_v1.json",
    }
    sources = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in source_paths.items()}
    draws, seed = 10_000, 260901
    records = []
    comparison_records = []
    meta = {}
    meta.update(meta_values(sources["metaworld_partial_25"], "partial_25"))
    meta.update(meta_values(sources["metaworld_partial_50"], "partial_50"))
    for (condition, budget), values in sorted(meta.items()):
        if not complete(values):
            raise ValueError(f"incomplete MetaWorld condition {condition}, {budget}")
        identity = {"dataset": "MetaWorld", "condition": condition.replace("partial_", ""), "budget": budget}
        for index, method in enumerate(METHODS):
            records.append({**identity, "method": method, **interval(values, method, draws, seed + len(records) + index)})
        for index, method in enumerate(METHODS[1:]):
            comparison_records.append({**identity, "left": "lantern", "right": method,
                                       **paired(values, method, draws, seed + 1000 + len(comparison_records) + index)})
    for (family, condition, budget), values in sorted(baby_values(sources["babyai"]).items()):
        if not complete(values):
            raise ValueError(f"incomplete BabyAI condition {family}, {condition}, {budget}")
        identity = {"dataset": family, "condition": condition.replace("partial_", ""), "budget": budget}
        for index, method in enumerate(METHODS):
            records.append({**identity, "method": method, **interval(values, method, draws, seed + len(records) + index)})
        for index, method in enumerate(METHODS[1:]):
            comparison_records.append({**identity, "left": "lantern", "right": method,
                                       **paired(values, method, draws, seed + 1000 + len(comparison_records) + index)})
    report = {
        "schema_version": "rq1-cluster-bootstrap-uncertainty-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "draws": draws,
        "resampling_unit": {"MetaWorld": "held-out task", "OpenDoorColor": "held-out context",
                              "UnlockPickup": "held-out context"},
        "method_mapping": {"lantern": "LANTERN", "cacwr": "cascade-aware continuation without rollout",
                           "immediate_harm": "Immediate-Harm"},
        "absolute_safe_recovery_intervals": records,
        "paired_lantern_advantage_intervals": comparison_records,
        "artifact_hashes": {name: digest(path) for name, path in source_paths.items()},
    }
    output = ROOT / "paper_results/rq1_paired_bootstrap_95_v1.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "absolute_intervals": len(records),
                      "paired_intervals": len(comparison_records)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
