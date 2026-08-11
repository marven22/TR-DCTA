"""Diagnose which descendants lose recovery when provenance is hidden."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.publication_v2_source import fit_source_estimator, source_features


SPLITS = ("development", "validation", "test")
METHOD_NAMES = {"development": ("sc_dcta", "sc_ens"),
                "validation": ("sc_dcta", "ens"),
                "test": ("sc_dcta", "ens")}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mean(values):
    return statistics.fmean(values) if values else None


def confidence_maps():
    output = {}
    for split, result_path in (
        ("development", "results/sc_dcta_metaworld_development.json"),
        ("test", "results/sc_dcta_metaworld_evaluation.json"),
    ):
        result = load(result_path)
        output[split] = {row["archive_id"]: row["target_prior"]
                         for row in result["posterior_diagnostics"]
                         if float(row["provenance_missing_rate"]) == 0.0}

    dev_public = load("results/prob_dcta_metaworld_development_public_mask_consistent.json")
    dev_private = load("results/prob_dcta_metaworld_development_private_mask_consistent.json")
    val_public = load("results/prob_dcta_metaworld_validation_public_mask_consistent.json")
    val_private = load("results/prob_dcta_metaworld_validation_private_mask_consistent.json")
    all_archives = dev_public["archives"] + val_public["archives"]
    labels = {row["archive_id"]: row for row in
              dev_private["archives"] + val_private["archives"]}
    val_tasks = sorted({row["task_key"] for row in val_public["archives"]})
    val_priors = {}
    for held_task in val_tasks:
        training = [row for row in all_archives if row["task_key"] != held_task
                    and float(row["provenance_missing_rate"]) == 0.0]
        source_rows = [
            (source_features(archive, str(source)),
             int(str(source) == str(labels[archive["archive_id"]]["active_source_id"])))
            for archive in training for source in archive["source_ids"]
        ]
        estimator = fit_source_estimator(source_rows, l2=1.0)
        for archive in val_public["archives"]:
            if archive["task_key"] == held_task and float(archive["provenance_missing_rate"]) == 0.0:
                val_priors[archive["archive_id"]] = estimator.prior(archive, 0.0)
    output["validation"] = val_priors
    return output


def reachability(edges, sources):
    children = defaultdict(list)
    for left, right in edges:
        children[str(left)].append(str(right))
    output = {}
    for source in sources:
        distance = {str(source): 0}; queue = [str(source)]
        for node in queue:
            for child in children[node]:
                if child not in distance:
                    distance[child] = distance[node] + 1; queue.append(child)
        output[str(source)] = distance
    return output


def eval_paths(split, mask):
    if mask == 0.0:
        return Path(f"results/metaworld_recovery_{split}_m0_b4_observable.json"), Path(f"results/metaworld_forced_exposure_{split}_m0_b4_evaluation.json")
    return Path(f"results/metaworld_recovery_{split}_m50_b4_observable.json"), Path(f"results/metaworld_forced_exposure_{split}_m50_b4_evaluation.json")


def task_interval(values_by_task, draws=10_000, seed=66319):
    tasks = sorted(values_by_task)
    if not tasks:
        return {"estimate": None, "lower_95": None, "upper_95": None, "task_count": 0}
    values = [values_by_task[t] for t in tasks]; rng = random.Random(seed)
    samples = sorted(mean([values[rng.randrange(len(values))] for _ in values])
                     for _ in range(draws))
    return {"estimate": mean(values), "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[int(.975 * draws)], "task_count": len(tasks)}


def grouped_task_means(rows, field):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["task_key"]].append(float(row[field]))
    return {task: mean(values) for task, values in grouped.items()}


def summarize(rows):
    sc_delta = grouped_task_means(rows, "sc_recovery_change")
    ens_delta = grouped_task_means(rows, "ens_recovery_change")
    tasks = sorted(set(sc_delta) & set(ens_delta))
    difference = {task: sc_delta[task] - ens_delta[task] for task in tasks}
    return {
        "episode_count": len(rows), "task_count": len({r["task_key"] for r in rows}),
        "sc_mask0_recovered": sum(r["sc_recovered_0"] for r in rows),
        "sc_mask50_recovered": sum(r["sc_recovered_50"] for r in rows),
        "sc_change": task_interval(sc_delta),
        "ens_mask0_recovered": sum(r["ens_recovered_0"] for r in rows),
        "ens_mask50_recovered": sum(r["ens_recovered_50"] for r in rows),
        "ens_change": task_interval(ens_delta),
        "sc_minus_ens_change": task_interval(difference, seed=66320),
    }


def stratum_values(row):
    return {
        "observed_path": "connected" if row["observed_reachable"] else "disconnected",
        "depth": "shallow_1_2" if row["true_depth"] <= 2 else "deep_3_plus",
        "exact_depth": str(row["true_depth"]),
        "ancestry": "single_source" if row["source_ancestor_count"] == 1 else "multi_source",
        "confidence": "high_ge_0.8" if row["source_max_probability"] >= .8 else "low_lt_0.8",
        "source_top1": "correct" if row["source_top1_correct"] else "wrong",
        "cascade_size": "small_le_6" if row["cascade_size"] <= 6 else "large_gt_6",
    }


def main() -> None:
    confidences = confidence_maps(); paired_rows = []
    for split in SPLITS:
        public = load(f"results/prob_dcta_metaworld_{'test' if split == 'test' else split}_public_mask_consistent.json")
        private = load(f"results/prob_dcta_metaworld_{'test' if split == 'test' else split}_private_mask_consistent.json")
        pub_by_mask_key = {(float(row["provenance_missing_rate"]), row["task_key"], int(row["rotation"])): row
                           for row in public["archives"]}
        private_by_id = {row["archive_id"]: row for row in private["archives"]}
        obs0_path, ev0_path = eval_paths(split, 0.0)
        obs50_path, ev50_path = eval_paths(split, .5)
        obs0, obs50 = load(obs0_path), load(obs50_path)
        ev0, ev50 = load(ev0_path), load(ev50_path)
        rotation0 = {row["archive_id"]: int(row["rotation"]) for row in obs0["archives"]}
        rotation50 = {row["archive_id"]: int(row["rotation"]) for row in obs50["archives"]}
        sc_name, ens_name = METHOD_NAMES[split]
        def event_map(events, rotations, method):
            return {(row["task_key"], rotations[row["archive_id"]], row["anchor_id"]): row
                    for row in events["rows"] if row["method"] == method}
        maps = {("sc", 0): event_map(ev0, rotation0, sc_name),
                ("ens", 0): event_map(ev0, rotation0, ens_name),
                ("sc", 50): event_map(ev50, rotation50, sc_name),
                ("ens", 50): event_map(ev50, rotation50, ens_name)}
        keys = sorted(set(maps["sc", 0]) & set(maps["sc", 50])
                      & set(maps["ens", 0]) & set(maps["ens", 50]))
        for task_key, rotation, anchor in keys:
            archive0 = pub_by_mask_key[0.0, task_key, rotation]
            archive50 = pub_by_mask_key[.5, task_key, rotation]
            truth = private_by_id[archive0["archive_id"]]
            active = str(truth["active_source_id"])
            true_reach = reachability(truth["true_formation_edges"], archive0["source_ids"])
            observed_reach = reachability(archive50["observed_formation_edges"], archive50["source_ids"])
            depth = true_reach[active].get(anchor)
            if depth is None:
                raise ValueError("affected descendant is unreachable from active source")
            prior = confidences[split][archive0["archive_id"]]
            sc0, sc50 = maps["sc", 0][task_key, rotation, anchor], maps["sc", 50][task_key, rotation, anchor]
            en0, en50 = maps["ens", 0][task_key, rotation, anchor], maps["ens", 50][task_key, rotation, anchor]
            paired_rows.append({
                "split": split, "task_key": task_key, "rotation": rotation,
                "anchor_id": anchor, "true_depth": depth,
                "observed_reachable": anchor in observed_reach[active],
                "source_ancestor_count": sum(anchor in true_reach[str(s)] for s in archive0["source_ids"]),
                "cascade_size": len(truth["affected_ids"]),
                "source_max_probability": max(prior.values()),
                "source_entropy": -sum(float(p) * math.log(max(float(p), 1e-15)) for p in prior.values()),
                "source_top1_correct": max(prior, key=prior.get) == active,
                "sc_localized_0": bool(sc0["anchor_quarantined"]),
                "sc_localized_50": bool(sc50["anchor_quarantined"]),
                "sc_recovered_0": bool(sc0["post_success"]),
                "sc_recovered_50": bool(sc50["post_success"]),
                "sc_recovery_change": int(bool(sc50["post_success"])) - int(bool(sc0["post_success"])),
                "ens_recovered_0": bool(en0["post_success"]),
                "ens_recovered_50": bool(en50["post_success"]),
                "ens_recovery_change": int(bool(en50["post_success"])) - int(bool(en0["post_success"])),
            })

    def analyze(rows):
        output = {"all": summarize(rows), "strata": {}}
        for dimension in ("observed_path", "depth", "exact_depth", "ancestry",
                          "confidence", "source_top1", "cascade_size"):
            groups = defaultdict(list)
            for row in rows:
                groups[stratum_values(row)[dimension]].append(row)
            output["strata"][dimension] = {name: summarize(values)
                                             for name, values in sorted(groups.items())}
        contrasts = {
            "disconnected_minus_connected": ("observed_path", "disconnected", "connected"),
            "deep_minus_shallow": ("depth", "deep_3_plus", "shallow_1_2"),
            "multi_minus_single_source": ("ancestry", "multi_source", "single_source"),
            "low_minus_high_confidence": ("confidence", "low_lt_0.8", "high_ge_0.8"),
            "large_minus_small_cascade": ("cascade_size", "large_gt_6", "small_le_6"),
        }
        output["within_sc_change_contrasts"] = {}
        for label, (dimension, focus, reference) in contrasts.items():
            focus_rows = [row for row in rows if stratum_values(row)[dimension] == focus]
            reference_rows = [row for row in rows if stratum_values(row)[dimension] == reference]
            left = grouped_task_means(focus_rows, "sc_recovery_change")
            right = grouped_task_means(reference_rows, "sc_recovery_change")
            tasks = sorted(set(left) & set(right))
            values = {task: left[task] - right[task] for task in tasks}
            output["within_sc_change_contrasts"][label] = task_interval(values, seed=66321)
        return output
    payload = {
        "protocol": "sc-dcta/metaworld-failure-strata-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "test": analyze([row for row in paired_rows if row["split"] == "test"]),
        "all_49_descriptive": analyze(paired_rows), "rows": paired_rows,
    }
    output = Path("results/metaworld_failure_strata.json")
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"test": payload["test"], "all_49_descriptive": payload["all_49_descriptive"]}, indent=2))


if __name__ == "__main__":
    main()
