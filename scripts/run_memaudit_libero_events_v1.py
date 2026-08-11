"""Run the frozen paper-level MemAudit reconstruction on Memory-LIBERO.

This stage never loads private affected-memory labels. It builds observable
harmful events with Qwen policy selection, computes leave-one-memory-out CMIS,
computes MPNet/DeBERTa CAS, ranks memories, and measures post-removal task harm.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Mapping, Sequence

import _bootstrap

from mcx.config import GenerationSettings, config_from_env
from mcx.memaudit import HarmfulEvent, MemAuditParameters, memaudit_rank
from mcx.memaudit_libero import (
    memory_text, parse_selected_memory, policy_harm, retrieve_by_similarity,
    selection_prompt, symmetric_knn,
)
from mcx.model import build_backend
from mcx.model.base import GenerationRequest


PROTOCOL = "memaudit-libero-v1/observable-events"
PUBLIC_PROTOCOL = "memory-libero/external-validation-v1/public"
SCREEN_PROTOCOL = "memory-libero/external-validation-v1/screen"
CONFIG_PROTOCOL = "memaudit-libero-v1/paper-reconstruction-freeze"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def target_index(archive_id: str) -> int:
    match = re.search(r"_(\d+)$", archive_id)
    if not match:
        raise ValueError(f"archive ID lacks target index: {archive_id}")
    return int(match.group(1))


def policy_outcomes(screen: Mapping[str, object]) -> dict[int, dict[str, bool]]:
    output = {}
    for row in screen["targets"]:  # type: ignore[index]
        if not row["verified"]:
            continue
        target = int(row["target_index"])
        donor = int(row["selected_donor_index"])
        output[target] = {
            f"libero_90/task_{target:02d}/demo_0_1": True,
            f"libero_90/task_{donor:02d}/demo_0_1": False,
        }
    return output


def release_gpu() -> None:
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except (ImportError, RuntimeError):
        pass


def semantic_stage(archives, config):
    import numpy as np
    from sentence_transformers import SentenceTransformer

    choice = config["declared_reconstruction_choices"]
    model = SentenceTransformer(
        choice["semantic_model"], revision=choice["semantic_model_revision"],
        device="cuda",
    )
    output = {}
    for index, archive in enumerate(archives, start=1):
        ids = tuple(str(node) for node in archive["candidate_ids"])
        texts = [memory_text(archive["memories"][node]) for node in ids]
        vectors = model.encode(
            [str(archive["target_language"]), *texts], batch_size=32,
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        )
        retrieval = {node: float(vectors[0] @ vectors[offset + 1])
                     for offset, node in enumerate(ids)}
        similarities = {}
        for left_index, left in enumerate(ids):
            for right_index, right in enumerate(ids):
                if left != right:
                    similarities[left, right] = float(
                        vectors[left_index + 1] @ vectors[right_index + 1]
                    )
        neighbors = symmetric_knn(ids, similarities, int(choice["semantic_neighbors"]))
        output[str(archive["archive_id"])] = {
            "retrieval_scores": retrieval,
            "similarities": {f"{left}|{right}": value
                             for (left, right), value in similarities.items()},
            "neighbors": {node: list(values) for node, values in neighbors.items()},
        }
        print(f"semantic {index}/{len(archives)} {archive['archive_id']}", flush=True)
    del model
    release_gpu()
    return output


def nli_stage(archives, semantic, config):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    choice = config["declared_reconstruction_choices"]
    name, revision = choice["nli_model"], choice["nli_model_revision"]
    tokenizer = AutoTokenizer.from_pretrained(name, revision=revision)
    model = AutoModelForSequenceClassification.from_pretrained(
        name, revision=revision, torch_dtype=torch.float16,
    ).to("cuda").eval()
    contradiction_index = next(
        int(index) for index, label in model.config.id2label.items()
        if str(label).lower() == "contradiction"
    )
    pairs = []
    for archive in archives:
        archive_id = str(archive["archive_id"])
        for node, neighbors in semantic[archive_id]["neighbors"].items():
            for neighbor in neighbors:
                pairs.append((
                    archive_id, node, neighbor,
                    memory_text(archive["memories"][node]),
                    memory_text(archive["memories"][neighbor]),
                ))
    output = {str(archive["archive_id"]): {} for archive in archives}
    batch_size = 32
    for start in range(0, len(pairs), batch_size):
        batch = pairs[start:start + batch_size]
        encoded = tokenizer(
            [row[3] for row in batch], [row[4] for row in batch],
            padding=True, truncation=True, max_length=512, return_tensors="pt",
        ).to("cuda")
        with torch.no_grad():
            probabilities = torch.softmax(model(**encoded).logits.float(), dim=-1)
        for row, probability in zip(batch, probabilities[:, contradiction_index].tolist()):
            output[row[0]][f"{row[1]}|{row[2]}"] = float(probability)
        print(f"nli {min(start + len(batch), len(pairs))}/{len(pairs)}", flush=True)
    del model, tokenizer
    release_gpu()
    return output


def generation_request(prompt: str, task: str, memories) -> GenerationRequest:
    return GenerationRequest(
        purpose="plan", prompt=prompt, task={"language": task}, memories=memories,
    )


def select_batch(backend, jobs, chunk_size=6):
    """Run frozen greedy selection with exactly one format-repair attempt."""

    results = []
    for start in range(0, len(jobs), chunk_size):
        chunk = jobs[start:start + chunk_size]
        requests = [generation_request(job["prompt"], job["task"], job["visible"])
                    for job in chunk]
        raws = backend.generate_batch(requests)
        for job, raw in zip(chunk, raws):
            attempts = [{"raw": raw, "valid": False, "error": None}]
            try:
                selected = parse_selected_memory(raw, job["retrieved_ids"])
                attempts[0]["valid"] = True
            except (json.JSONDecodeError, ValueError) as error:
                attempts[0]["error"] = str(error)
                repair_prompt = (
                    job["prompt"] + "\nYour previous response was invalid: "
                    + str(error) + ". Return corrected JSON only."
                )
                repaired = backend.generate(generation_request(
                    repair_prompt, job["task"], job["visible"]
                ))
                try:
                    selected = parse_selected_memory(repaired, job["retrieved_ids"])
                    attempts.append({"raw": repaired, "valid": True, "error": None})
                except (json.JSONDecodeError, ValueError) as second:
                    attempts.append({"raw": repaired, "valid": False,
                                     "error": str(second)})
                    selected = None
            results.append({**job, "attempts": attempts, "selected_id": selected})
        print(f"qwen {min(start + len(chunk), len(jobs))}/{len(jobs)}", flush=True)
    return results


def selection_job(archive, retrieved_ids, tag):
    memories = archive["memories"]
    return {
        "archive_id": str(archive["archive_id"]), "tag": tag,
        "task": str(archive["target_language"]),
        "retrieved_ids": list(retrieved_ids),
        "visible": [
            {"memory_id": node, "lesson": memories[node].get("lesson", ""),
             "expected_outcome": memories[node].get("expected_outcome", "")}
            for node in retrieved_ids
        ],
        "prompt": selection_prompt(
            str(archive["target_language"]), retrieved_ids, memories
        ),
    }


def ranking_for_archive(archive, sem, nli, original, counterfactuals, alpha):
    ids = tuple(str(node) for node in archive["candidate_ids"])
    event = HarmfulEvent(
        event_id=f"{archive['archive_id']}:event",
        observed_harm=float(original["harm"]),
        retrieved_memory_ids=tuple(original["retrieved_ids"]),
    )
    cf_harm = {row["removed_id"]: float(row["harm"]) for row in counterfactuals}
    similarities = {
        tuple(key.split("|", 1)): value for key, value in sem["similarities"].items()
    }
    contradictions = {
        tuple(key.split("|", 1)): value for key, value in nli.items()
    }
    ranking, calls = memaudit_rank(
        ids, (event,), lambda _event, node: cf_harm[node],
        sem["neighbors"],
        lambda left, right: similarities[left, right],
        lambda left, right: contradictions[left, right],
        MemAuditParameters(alpha=float(alpha)),
    )
    return [score.__dict__ for score in ranking], calls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8"))
    screen = json.loads(args.screen.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if public.get("protocol") != PUBLIC_PROTOCOL:
        raise ValueError("frozen external public ledger required")
    if screen.get("protocol") != SCREEN_PROTOCOL or not screen.get("complete"):
        raise ValueError("complete frozen screen ledger required")
    if config.get("protocol") != CONFIG_PROTOCOL:
        raise ValueError("frozen MemAudit configuration required")
    archives = list(public["archives"])
    if args.limit is not None:
        archives = archives[:args.limit]
    outcomes = policy_outcomes(screen)
    for archive in archives:
        allowed = outcomes[target_index(str(archive["archive_id"]))]
        policies = {str(memory["recommended_policy_id"])
                    for memory in archive["memories"].values()}
        if not policies.issubset(allowed):
            raise ValueError(f"unverified policy in {archive['archive_id']}")

    semantic = semantic_stage(archives, config)
    nli = nli_stage(archives, semantic, config)
    qwen_config = config_from_env(
        backend="qwen", generation=GenerationSettings(max_new_tokens=64)
    )
    backend = build_backend(qwen_config)
    choice = config["declared_reconstruction_choices"]
    top_k = int(choice["retrieval_top_k"])
    original_jobs = []
    archive_by_id = {str(row["archive_id"]): row for row in archives}
    for archive in archives:
        archive_id = str(archive["archive_id"])
        retrieved = retrieve_by_similarity(
            archive["candidate_ids"], semantic[archive_id]["retrieval_scores"],
            archive["created_at"], top_k,
        )
        original_jobs.append(selection_job(archive, retrieved, "original"))
    originals = select_batch(backend, original_jobs)
    original_by_id = {}
    harmful_ids = []
    for row in originals:
        archive = archive_by_id[row["archive_id"]]
        if row["selected_id"] is None:
            row["harm"] = None
        else:
            row["harm"] = policy_harm(
                row["selected_id"], archive["memories"],
                outcomes[target_index(row["archive_id"])],
            )
            if row["harm"] == 1.0:
                harmful_ids.append(row["archive_id"])
        original_by_id[row["archive_id"]] = row

    counterfactual_jobs = []
    for archive_id in harmful_ids:
        archive = archive_by_id[archive_id]
        for removed in original_by_id[archive_id]["retrieved_ids"]:
            retrieved = retrieve_by_similarity(
                archive["candidate_ids"], semantic[archive_id]["retrieval_scores"],
                archive["created_at"], top_k, excluded=(removed,),
            )
            job = selection_job(archive, retrieved, f"without:{removed}")
            job["removed_id"] = removed
            counterfactual_jobs.append(job)
    counterfactual_results = select_batch(backend, counterfactual_jobs)
    counterfactual_by_id = {archive_id: [] for archive_id in harmful_ids}
    for row in counterfactual_results:
        archive = archive_by_id[row["archive_id"]]
        if row["selected_id"] is None:
            row["harm"] = None
        else:
            row["harm"] = policy_harm(
                row["selected_id"], archive["memories"],
                outcomes[target_index(row["archive_id"])],
            )
        counterfactual_by_id[row["archive_id"]].append(row)
    invalid = [row for row in originals + counterfactual_results
               if row["selected_id"] is None]
    if invalid:
        raise ValueError(f"{len(invalid)} Qwen selections invalid after repair")

    rankings = {}
    alpha = float(config["paper_parameters"]["alpha"])
    for archive_id in harmful_ids:
        ranking, calls = ranking_for_archive(
            archive_by_id[archive_id], semantic[archive_id], nli[archive_id],
            original_by_id[archive_id], counterfactual_by_id[archive_id], alpha,
        )
        rankings[archive_id] = {"scores": ranking, "counterfactual_calls": calls}

    post_jobs = []
    for archive_id in harmful_ids:
        archive = archive_by_id[archive_id]
        ordered = [row["memory_id"] for row in rankings[archive_id]["scores"]]
        for budget in choice["removal_budgets"]:
            removed = tuple(ordered[:int(budget)])
            retrieved = retrieve_by_similarity(
                archive["candidate_ids"], semantic[archive_id]["retrieval_scores"],
                archive["created_at"], top_k, excluded=removed,
            )
            job = selection_job(archive, retrieved, f"post_remove:{budget}")
            job["budget"] = int(budget); job["removed_ids"] = list(removed)
            post_jobs.append(job)
    post_results = select_batch(backend, post_jobs)
    for row in post_results:
        archive = archive_by_id[row["archive_id"]]
        if row["selected_id"] is None:
            raise ValueError("post-removal Qwen selection invalid after repair")
        row["harm"] = policy_harm(
            row["selected_id"], archive["memories"],
            outcomes[target_index(row["archive_id"])],
        )

    payload = {
        "protocol": PROTOCOL,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": args.limit is None and len(archives) == int(public["strict_archive_count"]),
        "engineering_limit": args.limit,
        "public_sha256": sha256(args.public), "screen_sha256": sha256(args.screen),
        "config_sha256": sha256(args.config),
        "runner_sha256": sha256(Path(__file__)),
        "config": config, "qwen_config": qwen_config.as_log_dict(),
        "archive_count": len(archives), "harmful_event_archive_count": len(harmful_ids),
        "harmful_archive_ids": harmful_ids,
        "semantic": semantic, "nli_contradictions": nli,
        "original_events": originals,
        "counterfactual_events": counterfactual_results,
        "rankings": rankings, "post_removal_events": post_results,
    }
    checkpoint(args.output, payload)
    print(json.dumps({
        "complete": payload["complete"], "archive_count": len(archives),
        "harmful_event_archive_count": len(harmful_ids),
        "mean_counterfactual_calls": (
            sum(row["counterfactual_calls"] for row in rankings.values()) / len(rankings)
            if rankings else 0.0
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
