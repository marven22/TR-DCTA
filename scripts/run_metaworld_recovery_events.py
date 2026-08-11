"""Run retrieval and Qwen choice using only the observable recovery manifest."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.config import GenerationSettings, config_from_env
from mcx.memaudit_libero import (
    memory_text, parse_selected_memory, retrieve_by_similarity, selection_prompt,
)
from mcx.model import build_backend
from mcx.model.base import GenerationRequest


PROTOCOL = "sc-dcta/metaworld-recovery-events-v1"
OBS_PROTOCOL = "sc-dcta/metaworld-recovery-observable-v1"
SEMANTIC_MODEL = "sentence-transformers/all-mpnet-base-v2"
SEMANTIC_REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selection_job(archive, memories, scores, excluded, condition):
    ids = retrieve_by_similarity(
        archive["candidate_ids"], scores, archive["created_at"], 5, excluded,
    )
    return {
        "archive_id": archive["archive_id"], "task_key": archive["task_key"],
        "condition": condition, "excluded_ids": list(excluded),
        "retrieved_ids": list(ids), "task": archive["target_language"],
        "prompt": selection_prompt(archive["target_language"], ids, memories),
        "visible": [{"memory_id": node,
                     "lesson": memories[node].get("lesson", ""),
                     "expected_outcome": memories[node].get("expected_outcome", "")}
                    for node in ids],
    }


def run_batch(backend, jobs, chunk_size=6):
    results = []
    for start in range(0, len(jobs), chunk_size):
        chunk = jobs[start:start + chunk_size]
        requests = [GenerationRequest(purpose="plan", prompt=row["prompt"],
                                      task={"language": row["task"]},
                                      memories=row["visible"]) for row in chunk]
        raw_values = backend.generate_batch(requests)
        for row, raw in zip(chunk, raw_values):
            attempts = [{"raw": raw, "valid": False, "error": None}]
            try:
                selected = parse_selected_memory(raw, row["retrieved_ids"])
                attempts[0]["valid"] = True
            except (json.JSONDecodeError, ValueError) as error:
                attempts[0]["error"] = str(error)
                prompt = row["prompt"] + "\nYour previous response was invalid: " + str(error) + ". Return corrected JSON only."
                request = GenerationRequest(purpose="plan", prompt=prompt,
                                            task={"language": row["task"]},
                                            memories=row["visible"])
                repaired = backend.generate(request)
                try:
                    selected = parse_selected_memory(repaired, row["retrieved_ids"])
                    attempts.append({"raw": repaired, "valid": True, "error": None})
                except (json.JSONDecodeError, ValueError) as second:
                    selected = None
                    attempts.append({"raw": repaired, "valid": False,
                                     "error": str(second)})
            results.append({key: value for key, value in row.items() if key != "prompt"}
                           | {"attempts": attempts, "selected_id": selected})
        print(f"qwen {min(start + len(chunk), len(jobs))}/{len(jobs)}", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    manifest = json.loads(args.observable.read_text(encoding="utf-8"))
    if manifest.get("protocol") != OBS_PROTOCOL:
        raise ValueError("wrong observable manifest protocol")
    archives = list(manifest["archives"])
    if args.limit is not None:
        archives = archives[:args.limit]

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(SEMANTIC_MODEL, revision=SEMANTIC_REVISION, device="cuda")
    jobs = []
    for index, archive in enumerate(archives, start=1):
        ids = list(map(str, archive["candidate_ids"]))
        score_sets = {}
        for variant in ("corrupted", "clean"):
            memories = archive[f"{variant}_memories"]
            vectors = model.encode(
                [archive["target_language"]] + [memory_text(memories[node]) for node in ids],
                batch_size=32, convert_to_numpy=True, normalize_embeddings=True,
                show_progress_bar=False,
            )
            score_sets[variant] = {node: float(vectors[0] @ vectors[offset + 1])
                                   for offset, node in enumerate(ids)}
        jobs.append(selection_job(archive, archive["corrupted_memories"],
                                  score_sets["corrupted"], (), "corrupted"))
        jobs.append(selection_job(archive, archive["clean_memories"],
                                  score_sets["clean"], (), "clean"))
        # Deduplicate methods that produce the same quarantine set, while retaining aliases.
        groups = {}
        for method, removed in archive["quarantined_ids"].items():
            groups.setdefault(tuple(removed), []).append(method)
        for removed, methods in groups.items():
            job = selection_job(archive, archive["corrupted_memories"],
                                score_sets["corrupted"], removed,
                                "post:" + ",".join(sorted(methods)))
            job["methods"] = sorted(methods)
            jobs.append(job)
        print(f"semantic {index}/{len(archives)} {archive['archive_id']}", flush=True)
    del model
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except (ImportError, RuntimeError):
        pass

    config = config_from_env(backend="qwen", generation=GenerationSettings(max_new_tokens=64))
    backend = build_backend(config)
    events = run_batch(backend, jobs)
    invalid = sum(row["selected_id"] is None for row in events)
    payload = {
        "protocol": PROTOCOL, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "observable_sha256": sha256(args.observable), "archive_count": len(archives),
        "semantic_model": f"{SEMANTIC_MODEL}@{SEMANTIC_REVISION}",
        "agent": config.as_log_dict(), "invalid_count": invalid, "events": events,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if invalid:
        raise ValueError(f"{invalid} selections invalid after one repair")
    print(f"wrote {len(events)} behavioral selections to {args.output}")


if __name__ == "__main__":
    main()
