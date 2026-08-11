"""Independently verify the full-49 MetaWorld TR-DCTA report."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401

from mcx.memaudit_libero import memory_text
from mcx.metaworld_recovery import first_survivor, forced_exposure_ranking, selected_success


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "METAWORLD_TR_DCTA_FULL49_PROTOCOL_V1.md"
RUNNER = ROOT / "scripts" / "run_metaworld_tr_dcta_full49_v1.py"
ADAPTER = ROOT / "src" / "mcx" / "metaworld_terminal_recovery_dcta.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(name: str) -> str:
    return {"ens": "sc_ens", "source_then_dcta": "sc_source_then_dcta"}.get(name, name)


def summarize(rows: list[dict]) -> dict:
    quarantined = [r for r in rows if r["anchor_quarantined"]]
    return {
        "episodes": len(rows),
        "anchor_quarantine_count": sum(bool(r["anchor_quarantined"]) for r in rows),
        "anchor_quarantine_rate": statistics.fmean(float(r["anchor_quarantined"]) for r in rows),
        "behavioral_recovery_count": sum(bool(r["post_success"]) for r in rows),
        "behavioral_recovery_rate": statistics.fmean(float(r["post_success"]) for r in rows),
        "successful_fallback_given_anchor_quarantined": (
            statistics.fmean(float(r["post_success"]) for r in quarantined)
            if quarantined else None),
        "harmful_fallback_count": sum(bool(r["fallback_still_harmful"]) for r in rows),
    }


def bootstrap(rows: list[dict], right: str, metric: str, draws: int, seed: int) -> dict:
    by_task = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_task[row["task_key"]][row["method"]].append(float(row[metric]))
    tasks = sorted(t for t, values in by_task.items()
                   if "tr_dcta" in values and right in values)
    differences = [statistics.fmean(by_task[t]["tr_dcta"])
                   - statistics.fmean(by_task[t][right]) for t in tasks]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(
        differences[rng.randrange(len(tasks))] for _ in tasks) for _ in range(draws))
    return {"left": "tr_dcta", "right": right, "metric": metric,
            "task_count": len(tasks), "estimate": statistics.fmean(differences),
            "lower_95": samples[int(.025 * draws)],
            "upper_95": samples[min(int(.975 * draws), draws - 1)],
            "wins": sum(x > 0 for x in differences),
            "ties": sum(x == 0 for x in differences),
            "losses": sum(x < 0 for x in differences)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    paths = {name: ROOT / value for name, value in config["paths"].items()}

    observable_by_id, truth_by_id = {}, {}
    baseline_rows = []
    for split in ("development", "validation", "test"):
        observable = json.loads(paths[f"{split}_observable"].read_text(encoding="utf-8"))
        recovery = json.loads(paths[f"{split}_recovery_private"].read_text(encoding="utf-8"))
        forced = json.loads(paths[f"{split}_forced"].read_text(encoding="utf-8"))
        observable_by_id.update({a["archive_id"]: a for a in observable["archives"]})
        truth_by_id.update({a["archive_id"]: a for a in recovery["archives"]})
        for row in forced["rows"]:
            method = normalize(str(row["method"]))
            if method in config["comparators"]:
                copied = dict(row); copied["method"] = method; copied["split"] = split
                baseline_rows.append(copied)

    archive_results = report["archive_results"]
    tr_rows = report["tr_episode_rows"]
    tr_by_key = {(r["archive_id"], str(r["anchor_id"])): r for r in tr_rows}
    result_by_id = {r["archive_id"]: r for r in archive_results}
    labels_exact = all(
        r["labels"] == [int(node in set(map(str, truth_by_id[r["archive_id"]]["affected_ids"])))
                        for node in r["replayed_ids"]] for r in archive_results)
    quarantine_exact = all(
        set(r["quarantined_ids"]) == {node for node, label in zip(r["replayed_ids"], r["labels"])
                                      if int(label) == 1} for r in archive_results)

    # Independently reconstruct behavior for a deterministic sample spanning all splits.
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config["semantic_model"],
                                revision=config["semantic_model_revision"], device="cuda")
    sample_checks = []
    ordered_ids = sorted(result_by_id, key=lambda x: (result_by_id[x]["split"], x))
    sample_ids = sorted(set(ordered_ids[::12] + [ordered_ids[-1]]))
    for archive_id in sample_ids:
        obs = observable_by_id[archive_id]
        truth = truth_by_id[archive_id]
        result = result_by_id[archive_id]
        ids = list(map(str, obs["candidate_ids"]))
        vectors = model.encode(
            [obs["target_language"]]
            + [memory_text(obs["corrupted_memories"][node]) for node in ids],
            batch_size=32, convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False)
        scores = {node: float(vectors[0] @ vectors[index + 1])
                  for index, node in enumerate(ids)}
        for anchor in map(str, truth["affected_ids"]):
            ranking = forced_exposure_ranking(anchor, ids, scores, obs["created_at"])
            selected = first_survivor(ranking, result["quarantined_ids"])
            expected = tr_by_key[(archive_id, anchor)]
            sample_checks.append({
                "archive_id": archive_id, "split": result["split"], "anchor_id": anchor,
                "selected_match": selected == expected["post_selected_id"],
                "success_match": selected_success(
                    selected, truth["corrupted_policy_by_memory"], truth["success_by_policy"])
                    == bool(expected["post_success"]),
                "quarantine_match": (anchor in set(result["quarantined_ids"]))
                    == bool(expected["anchor_quarantined"]),
            })

    all_rows = baseline_rows + tr_rows
    scopes = {"all49": all_rows,
              "development": [r for r in all_rows if r["split"] == "development"],
              "validation": [r for r in all_rows if r["split"] == "validation"],
              "test": [r for r in all_rows if r["split"] == "test"]}
    methods = ["tr_dcta"] + list(config["comparators"])
    summaries, comparisons = {}, {}
    for scope_index, (scope, rows) in enumerate(scopes.items()):
        summaries[scope] = {m: summarize([r for r in rows if r["method"] == m])
                            for m in methods}
        comparisons[scope] = []
        for metric_index, metric in enumerate(("post_success", "anchor_quarantined")):
            for comparator_index, comparator in enumerate(config["comparators"]):
                comparisons[scope].append(bootstrap(
                    rows, comparator, metric, int(config["bootstrap_draws"]),
                    int(config["bootstrap_seed"]) + 1000 * scope_index
                    + 10 * metric_index + comparator_index))

    checks = {
        "schema_status_valid": report["schema_version"] == "metaworld-tr-dcta-full49-v1"
            and report["status"] == "EXECUTABLE",
        "inputs_pinned": all(digest(path) == config["hashes"][name]
                             for name, path in paths.items())
            and digest(ADAPTER) == config["hashes"]["adapter"],
        "artifact_hashes_match": report["artifact_hashes"] == {
            "config": digest(args.config), "protocol": digest(PROTOCOL),
            "runner": digest(RUNNER), "adapter": digest(ADAPTER),
            **{name: digest(path) for name, path in paths.items()}},
        "exact_counts": len({r["task_key"] for r in archive_results}) == 49
            and len(archive_results) == 147 and len(tr_rows) == 919
            and len(tr_by_key) == 919,
        "labels_exact": labels_exact,
        "confirmed_quarantine_exact": quarantine_exact,
        "four_unique_replays": all(len(r["replayed_ids"]) == 4
                                   and len(set(r["replayed_ids"])) == 4
                                   for r in archive_results),
        "rollout_dominance": all(r["root_rollout_recovery"] >= r["root_base_recovery"] - 1e-12
                                 for r in archive_results),
        "sample_behavior_exact": bool(sample_checks) and all(
            c["selected_match"] and c["success_match"] and c["quarantine_match"]
            for c in sample_checks),
        "summaries_exact": summaries == report["summaries"],
        "bootstrap_exact": comparisons == report["paired_bootstrap"],
        "reported_integrity_all_true": all(report["integrity"].values()),
    }
    output = {"schema_version": "metaworld-tr-dcta-full49-verification-v1",
              "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "verified": all(checks.values()), "report_sha256": digest(args.report),
              "checks": checks, "sample_checks": sample_checks,
              "test_summary": summaries["test"], "all49_summary": summaries["all49"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verified": output["verified"], "checks": checks,
                      "report_sha256": output["report_sha256"],
                      "sample_episode_checks": len(sample_checks)}, indent=2))
    return 0 if output["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
