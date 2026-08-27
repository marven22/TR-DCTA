"""Compose DDXPlus memory archives with a pinned Qwen checkpoint.

Structurally identical to the template generator: it consumes the same plan
from ``mcx.ddxplus_writer``, so the graph, the recommended procedures, the
citations, and every label are unchanged.  Only the prose comes from the model.

Generation is checkpointed after each task because a full pass writes roughly
sixty memories per task across forty-four tasks.  Re-running resumes from the
cache instead of regenerating text already accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import _bootstrap  # noqa: F401

from mcx.ddxplus import PROTOCOL
from mcx.ddxplus_qwen_writer import forbidden_terms, generate_texts
from mcx.ddxplus_writer import assemble_record, intended_contamination, plan_record
from mcx.publication_v2_archive import MASK_RATES, materialize_task


ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "src" / "mcx" / "ddxplus_qwen_writer.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_generate(config: dict[str, Any], device: str | None) -> Callable[[str], str]:
    from mcx.config import Config, GenerationSettings
    from mcx.model import build_backend
    from mcx.model.base import GenerationRequest

    if device:
        os.environ["MCX_DEVICE"] = device
    backend = build_backend(Config(
        backend="qwen",
        model_checkpoint=str(config["writer_model"]),
        model_revision=str(config["writer_revision"]),
        generation=GenerationSettings(max_new_tokens=int(config["max_new_tokens"])),
    ))

    def generate(prompt: str) -> str:
        return backend.generate(GenerationRequest(
            purpose="reflection", prompt=prompt, task={},
            max_new_tokens=int(config["max_new_tokens"])))

    return generate


def main() -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path,
                        default=ROOT / "results" / "ddxplus_qwen_cache_v1.json")
    parser.add_argument("--checkpoint", help="override the frozen writer model")
    parser.add_argument("--device", help="torch device; defaults to auto-selection")
    parser.add_argument("--limit", type=int, help="generate only the first N tasks")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("protocol") != "ddxplus_qwen_generation_v1":
        raise ValueError("frozen DDXPlus Qwen generation configuration required")
    if tuple(config["mask_rates"]) != MASK_RATES:
        raise ValueError("DDXPlus must reuse the frozen provenance mask rates")
    if args.checkpoint:
        config = {**config, "writer_model": args.checkpoint, "writer_revision": "main"}

    population = json.loads(
        (ROOT / config["population_ledger"]).read_text(encoding="utf-8"))
    pinned = config.get("population_identity_sha256")
    if pinned and pinned != population["population_identity_sha256"]:
        raise ValueError("task population drifted")
    tasks = population["tasks"][:args.limit] if args.limit else population["tasks"]

    cache: dict[str, list[str]] = {}
    if args.cache.is_file():
        cache = json.loads(args.cache.read_text(encoding="utf-8"))
    generate = build_generate(config, args.device)

    records, incidents, reused, written = [], [], 0, 0
    for index, task in enumerate(tasks, start=1):
        plan = plan_record(task)
        task_id = str(task["task_id"])
        forbidden = forbidden_terms(task)
        prefix = f"{task_id}|"
        task_cache = {key[len(prefix):]: value for key, value in cache.items()
                      if key.startswith(prefix) and isinstance(value, dict)}
        texts, task_incidents, task_reused = generate_texts(
            plan, generate, forbidden=forbidden,
            attempts=int(config["attempts_per_memory"]), cache=task_cache)
        incidents.extend({**item, "task_id": task_id} for item in task_incidents)
        reused += task_reused
        written += len(texts) - task_reused
        for key, value in task_cache.items():
            cache[prefix + key] = value
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        args.cache.write_text(json.dumps(cache, indent=1) + "\n", encoding="utf-8")
        record = assemble_record(plan, texts, str(config["writer"]))
        materialize_task(record)  # structural acceptance test
        records.append(record)
        print(f"[DDXPlus Qwen writer] {index}/{len(tasks)} {task_id}", flush=True)

    public_rows, private_rows = [], []
    label_divergences, silent_memories = [], []
    for task, record in zip(tasks, records):
        public, private = materialize_task(record)
        public_rows.extend(public)
        private_rows.extend(private)
        plan = plan_record(task)
        # The auditor never sees recommended_policy_id, so a corrupted memory
        # whose public text matches its clean counterpart carries no signal at
        # all even though its label is still correct.
        clean_text = {}
        for branch in record["branches"]:
            for memory in branch["memories"]:
                parsed = memory["counterfactual"]["parsed"]
                clean_text[str(memory["memory_id"])] = (
                    parsed["lesson"], parsed["expected_outcome"])
        for slot in plan["slots"]:
            if slot["copy_of"] or slot["container"] != "branches" \
                    or slot["variant"] != "factual":
                continue
            node = str(slot["memory_id"])
            variant = next(
                (memory["factual"]["parsed"] for branch in record["branches"]
                 for memory in branch["memories"]
                 if str(memory["memory_id"]) == node), None)
            if variant is not None and (variant["lesson"],
                                        variant["expected_outcome"]) == clean_text[node]:
                silent_memories.append({"task_id": str(task["task_id"]), "node": node})
        for row in private:
            intended = intended_contamination(plan, int(row["rotation"]))
            actual = set(map(str, row["contaminated_ids"]))
            if intended != actual:
                label_divergences.append({
                    "archive_id": row["archive_id"],
                    "intended_not_materialized": sorted(intended - actual),
                    "materialized_not_intended": sorted(actual - intended)})
    affected = [len(row["affected_ids"]) for row in private_rows]
    contaminated = [len(row["contaminated_ids"]) for row in private_rows]
    lessons = [str(item["parsed"]["lesson"])
               for record in records for branch in record["branches"]
               for memory in branch["memories"] for item in
               (memory["factual"], memory["counterfactual"])]

    integrity = {
        "row_counts_exact": len(public_rows) == len(tasks) * 3 * len(MASK_RATES),
        "every_archive_has_harm": all(count > 0 for count in affected),
        "harm_is_subset_of_contamination": all(
            set(row["affected_ids"]) <= set(row["contaminated_ids"])
            for row in private_rows),
        "harm_is_strictly_smaller_somewhere": any(
            len(row["affected_ids"]) < len(row["contaminated_ids"])
            for row in private_rows),
        # A degenerate writer collapses to a handful of phrases; Qwen-2.5-0.5B
        # produced a 9% distinct ratio while 7B produces roughly a third. The
        # properties that actually matter are gated separately below, so this
        # only rules out outright collapse.
        "writer_not_collapsed": len(set(lessons)) >= max(1, len(lessons) // 7),
        # A writer that emits the same prose for a corrupted memory and its
        # clean counterpart silently relabels it, so intent must match labels.
        "labels_match_planned_contamination": not label_divergences,
        "corrupted_text_is_visibly_different": not silent_memories,
    }
    payload = {
        "protocol": f"{PROTOCOL}/ddxplus-generation-qwen",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_payload": config,
        "artifact_hashes": {"config": digest(args.config),
                            "builder": digest(Path(__file__)),
                            "writer": digest(WRITER)},
        "counts": {"tasks": len(tasks), "memories_written": written,
                   "memories_reused_from_cache": reused,
                   "public_rows": len(public_rows),
                   "distinct_lessons": len(set(lessons)),
                   "distinct_lesson_ratio": round(
                       len(set(lessons)) / max(1, len(lessons)), 4)},
        "label_summary": {
            "mean_affected": statistics.fmean(affected),
            "mean_contaminated": statistics.fmean(contaminated),
        },
        "generation_incidents": incidents,
        "label_divergences": label_divergences[:50],
        "silent_corrupted_memories": silent_memories[:50],
        "integrity": integrity,
        "archives": records,
        "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": payload["counts"], "integrity": integrity,
                      "incidents": len(incidents),
                      "elapsed_s": payload["elapsed_s"]}, indent=2))
    return 0 if all(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
