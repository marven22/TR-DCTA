"""Evaluate behavioral recovery from frozen Meta-World scalability audits."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.memaudit_libero import memory_text
from mcx.metaworld_recovery import first_survivor, forced_exposure_ranking, selected_success
from mcx.metaworld_scalability import scale_archive


MODEL = "sentence-transformers/all-mpnet-base-v2"
REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def average(values):
    return statistics.fmean(values) if values else None


def task_bootstrap(rows, method: str, size: int, budget: int,
                   draws: int = 10_000, seed: int = 260806):
    selected = [row for row in rows if row["method"] == method
                and row["archive_size"] == size and row["budget"] == budget]
    by_task = {}
    for row in selected:
        by_task.setdefault(row["task_key"], []).append(float(row["post_success"]))
    tasks = sorted(by_task)
    values = [average(by_task[task]) for task in tasks]
    rng = random.Random(seed + size + budget)
    samples = sorted(average(values[rng.randrange(len(values))] for _ in values)
                     for _ in range(draws))
    return {
        "estimate": average(values), "lower_95": samples[int(.025 * draws)],
        "upper_95": samples[int(.975 * draws)], "task_count": len(tasks),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/metaworld_scalability_freeze_v1.json"))
    parser.add_argument("--split", choices=("development", "validation", "test"), required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    paths = {key: Path(value) for key, value in config["paths"].items()}
    public = json.loads(paths[f"{args.split}_public"].read_text(encoding="utf-8"))
    private = json.loads(paths[f"{args.split}_private"].read_text(encoding="utf-8"))
    observable = json.loads(paths[f"{args.split}_recovery_observable"].read_text(encoding="utf-8"))
    recovery_private = json.loads(paths[f"{args.split}_recovery_private"].read_text(encoding="utf-8"))
    audits = json.loads(args.audit.read_text(encoding="utf-8"))
    if not audits.get("complete") or audits.get("split") != args.split:
        raise ValueError("complete matching scalability audit required")
    mask = float(config["primary_provenance_missing_rate"])
    public_rows = [row for row in public["archives"]
                   if float(row["provenance_missing_rate"]) == mask]
    truth_by_id = {str(row["archive_id"]): row for row in private["archives"]}
    obs_by_task = {(str(row["task_key"]), int(row["rotation"])): row
                   for row in observable["archives"]}
    recovery_by_task = {}
    obs_by_id = {str(row["archive_id"]): row for row in observable["archives"]}
    for row in recovery_private["archives"]:
        obs = obs_by_id[str(row["archive_id"])]
        recovery_by_task[(str(row["task_key"]), int(obs["rotation"]))] = row
    audit_by_key = {
        (str(row["archive_id"]), int(row["archive_size"]), int(row["budget"]), str(row["method"])): row
        for row in audits["rows"] if float(row["provenance_missing_rate"]) == mask
    }

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL, revision=REVISION, device="cuda")
    rows = []
    maximum_size = max(map(int, config["archive_sizes"]))
    for index, base in enumerate(public_rows, start=1):
        truth = truth_by_id[str(base["archive_id"])]
        key = (str(base["task_key"]), int(base["rotation"]))
        obs, recovery = obs_by_task[key], recovery_by_task[key]
        largest = scale_archive(
            base, truth, obs["clean_memories"], recovery["clean_policy_by_memory"],
            recovery["corrupted_policy_by_memory"], recovery["success_by_policy"],
            maximum_size,
        )
        largest_ids = list(map(str, largest.archive["candidate_ids"]))
        vectors = model.encode(
            [base["target_language"]]
            + [memory_text(largest.archive["memories"][node]) for node in largest_ids],
            batch_size=64, convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        )
        all_scores = {node: float(vectors[0] @ vectors[offset + 1])
                      for offset, node in enumerate(largest_ids)}
        for size in map(int, config["archive_sizes"]):
            scaled = scale_archive(
                base, truth, obs["clean_memories"], recovery["clean_policy_by_memory"],
                recovery["corrupted_policy_by_memory"], recovery["success_by_policy"], size,
            )
            ids = list(map(str, scaled.archive["candidate_ids"]))
            scores = {node: all_scores[node] for node in ids}
            for anchor in scaled.affected_ids:
                ranking = forced_exposure_ranking(
                    anchor, ids, scores, scaled.archive["created_at"],
                )
                if selected_success(
                    anchor, scaled.policy_by_memory, scaled.success_by_policy,
                ):
                    raise ValueError("harmful exposure anchor unexpectedly succeeds")
                for budget in map(int, config["replay_budgets"]):
                    for method in config["methods"]:
                        audit = audit_by_key[(str(base["archive_id"]), size, budget, method)]
                        removed = set(audit["replayed_ids"]) & scaled.affected_ids
                        selected = first_survivor(ranking, removed)
                        post_success = selected_success(
                            selected, scaled.policy_by_memory, scaled.success_by_policy,
                        )
                        rows.append({
                            "split": args.split, "archive_id": base["archive_id"],
                            "task_key": base["task_key"], "rotation": int(base["rotation"]),
                            "archive_size": size, "budget": budget, "method": method,
                            "anchor_id": anchor, "anchor_quarantined": anchor in removed,
                            "post_selected_id": selected, "post_success": post_success,
                            "fallback_still_harmful": anchor in removed and not post_success,
                        })
        print(f"{args.split} recovery: archive {index}/{len(public_rows)}", flush=True)

    summaries = {}
    for size in map(int, config["archive_sizes"]):
        for budget in map(int, config["replay_budgets"]):
            for method in config["methods"]:
                chosen = [row for row in rows if row["archive_size"] == size
                          and row["budget"] == budget and row["method"] == method]
                localized = [row for row in chosen if row["anchor_quarantined"]]
                summaries[f"n{size}_b{budget}_{method}"] = {
                    "archive_size": size, "budget": budget, "method": method,
                    "exposure_episode_count": len(chosen),
                    "localized_count": sum(row["anchor_quarantined"] for row in chosen),
                    "recovered_count": sum(row["post_success"] for row in chosen),
                    "micro_recovery": average(float(row["post_success"]) for row in chosen),
                    "recovery_given_localization": average(
                        float(row["post_success"]) for row in localized
                    ),
                    "task_macro_recovery": task_bootstrap(rows, method, size, budget),
                }
    output = {
        "protocol": config["protocol"] + "/behavioral-recovery-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "split": args.split, "task_count": len({row["task_key"] for row in rows}),
        "archive_count": len(public_rows),
        "exposure_episode_count": len({(row["archive_id"], row["anchor_id"])
                                       for row in rows}),
        "semantic_model": f"{MODEL}@{REVISION}",
        "summaries": summaries, "rows": rows,
        "input_hashes": {"audit": sha256(args.audit),
                         "public": sha256(paths[f"{args.split}_public"]),
                         "private": sha256(paths[f"{args.split}_private"])},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "split": args.split, "rows": len(rows),
        "exposure_episode_count": output["exposure_episode_count"],
    }, indent=2))


if __name__ == "__main__":
    main()
