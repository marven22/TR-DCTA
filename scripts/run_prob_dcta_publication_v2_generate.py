"""Generate paired Qwen memories for the frozen publication-v2 archive DAG."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import _bootstrap
import run_memory_libero_generate_v0_3_1 as writer
import run_memory_libero_generate_v0_3_2  # noqa: F401 - installs format validator
from memory_libero_external_batch import GenerationJob, generate_jobs
from run_memory_libero_generate_v0_4 import render_prompt

from mcx.config import GenerationSettings, config_from_env
from mcx.model import build_backend
from mcx.publication_v2 import PROTOCOL, graph_spec, stable_digest


LEGACY_PROMPT_VERSION = "multi-origin-v2-locally-valid-transfer-and-overlap-v1"
R2_PROMPT_VERSION = "multi-origin-v2-selective-replay-consolidation-v2"
R3_PROMPT_VERSION = "multi-origin-v2-explicit-policy-inheritance-v3"
R4_PROMPT_VERSION = "multi-origin-v2-causally-ranked-inheritance-v4"
REGIMES = ("persistent", "recovery", "revival")


def checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_freeze(value: Mapping[str, object]) -> None:
    if value.get("protocol") not in {
        f"{PROTOCOL}/generation-freeze", f"{PROTOCOL}/generation-pilot-r2",
        f"{PROTOCOL}/generation-final-freeze",
    }:
        raise ValueError("frozen v2 generation configuration required")
    if value.get("writer_model") != "Qwen/Qwen2.5-14B-Instruct":
        raise ValueError("writer model changed")
    if tuple(value.get("branch_regimes", ())) != REGIMES:
        raise ValueError("branch regimes changed")
    if int(value.get("branch_depth", 0)) != 5 or int(value.get("shared_node_count", 0)) != 6:
        raise ValueError("archive shape changed")


def regime_order(task_id: str) -> tuple[str, ...]:
    return tuple(sorted(REGIMES, key=lambda value: (stable_digest("regime", task_id, value), value)))


def parsed_record(memory_id: str, result: Mapping[str, object]) -> dict[str, object]:
    parsed = result.get("parsed")
    if not isinstance(parsed, dict):
        raise ValueError(
            f"Qwen failed both validation attempts for {memory_id}: "
            + json.dumps(result.get("attempts"), ensure_ascii=False)
        )
    return {"memory_id": memory_id, **parsed}


def run_jobs(backend, jobs: Sequence[GenerationJob], batch_size: int) -> list[dict]:
    output: list[dict] = []
    for start in range(0, len(jobs), batch_size):
        chunk = jobs[start:start + batch_size]
        generated = generate_jobs(backend, chunk)
        for result, generation_job in zip(generated, chunk):
            if result.get("parsed") is not None:
                continue
            # A deterministic privacy guard may redact leaked opaque identifiers
            # after both model attempts. It never changes the selected policy,
            # citations, or any private outcome/label.
            attempts = result.get("attempts", [])
            if not attempts:
                continue
            try:
                value = json.loads(attempts[-1]["raw"])
                for field in ("lesson", "expected_outcome"):
                    if isinstance(value.get(field), str):
                        for identifier in sorted(generation_job.forbidden_ids,
                                                 key=len, reverse=True):
                            value[field] = value[field].replace(
                                identifier, "the selected procedure"
                            )
                if isinstance(value.get("cited_memory_ids"), list):
                    allowed_citations = {
                        str(item["memory_id"]) for item in generation_job.retrieved
                    }
                    value["cited_memory_ids"] = [
                        citation for citation in value["cited_memory_ids"]
                        if isinstance(citation, str) and citation in allowed_citations
                    ]
                result["parsed"] = writer.validate(
                    json.dumps(value), generation_job.allowed,
                    [item["memory_id"] for item in generation_job.retrieved],
                    generation_job.forbidden_ids,
                )
                result["privacy_sanitization"] = {
                    "applied": True,
                    "reason": "both Qwen attempts exposed a forbidden opaque identifier",
                    "changes_recommended_policy": False,
                    "citation_policy": "remove identifiers not directly retrieved",
                }
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        output.extend(generated)
    return output


def make_prompt(
    *, memory_id: str, depth: int, task: str, retrieved: Sequence[Mapping[str, object]],
    selected: str, allowed: Sequence[str], success: Sequence[bool] | None, feedback: str,
    prompt_version: str,
) -> str:
    if prompt_version == LEGACY_PROMPT_VERSION:
        if success is None:
            raise ValueError("legacy writer requires explicit simulator evidence")
        return render_prompt(
            memory_id=memory_id, depth=min(depth, 3), task_language=task,
            retrieved=retrieved, selected_policy_id=selected,
            allowed_policy_ids=allowed, simulator_success_by_demo=success,
            feedback=feedback,
        )
    if prompt_version not in {R2_PROMPT_VERSION, R3_PROMPT_VERSION, R4_PROMPT_VERSION}:
        raise ValueError(f"unknown writer prompt: {prompt_version}")
    evidence: dict[str, object] = {
        "new_memory_id": memory_id, "formation_task": task,
        "retrieved_memories": [{key: value[key] for key in (
            "memory_id", "recommended_policy_id", "lesson", "expected_outcome"
        ) if key in value} for value in retrieved],
        "selected_policy_id": selected, "allowed_policy_ids": list(allowed),
        "feedback": feedback,
        "style_instruction": writer.STYLES[min(depth, 3)],
    }
    if success is None:
        evidence["target_replay_evidence"] = "not_observed_during_this_consolidation"
        if prompt_version in {R3_PROMPT_VERSION, R4_PROMPT_VERSION} and retrieved:
            evidence["policy_inheritance_rule"] = (
                "Set recommended_policy_id exactly to the first retrieved memory's "
                "recommended_policy_id. Do not infer a replacement from the task name."
            )
    else:
        evidence["observed_success_by_policy"] = {
            policy: outcome for policy, outcome in zip(allowed, success)
        }
    return render_prompt(
        memory_id=memory_id, depth=min(depth, 3), task_language=task,
        retrieved=retrieved, selected_policy_id=selected,
        allowed_policy_ids=allowed, simulator_success_by_demo=(success or [False] * len(allowed)),
        feedback=feedback,
    ).split("\n", 1)[0].replace(
        "Create one reusable persistent robot-experience memory from all supplied evidence.",
        "Create one reusable persistent robot-experience memory from all supplied evidence. "
        "When no target replay was observed, consolidate retrieved experience without inventing an outcome."
    ) + "\n" + json.dumps(evidence, ensure_ascii=False, sort_keys=True)


def job(
    prompt: str, task: str, allowed: Sequence[str],
    retrieved: Sequence[Mapping[str, object]], forbidden: Sequence[str],
) -> GenerationJob:
    return GenerationJob(prompt, task, list(allowed), list(retrieved), list(forbidden))


def root_pair_jobs(
    task: Mapping[str, object], source_id: str, donor: Mapping[str, str], prompt_version: str,
):
    native = str(task["native_policy"]); bad = donor["policy"]
    forbidden = [source_id, native, bad]
    factual = make_prompt(
        memory_id=source_id, depth=1, task=donor["language"], retrieved=[],
        selected=bad, allowed=[bad], success=[True],
        feedback="The procedure succeeded on its formation task; retain the locally verified experience for future reuse.",
        prompt_version=prompt_version,
    )
    corrected = make_prompt(
        memory_id=source_id, depth=1, task=str(task["target_language"]), retrieved=[],
        selected=native, allowed=[native], success=[True],
        feedback="The procedure succeeded on its formation task; retain the locally verified experience for future reuse.",
        prompt_version=prompt_version,
    )
    return (
        job(factual, donor["language"], [bad], [], forbidden),
        job(corrected, str(task["target_language"]), [native], [], forbidden),
    )


def branch_inputs(
    regime: str, depth: int, factual_parent: Mapping[str, object],
    clean_parent: Mapping[str, object], factual_source: Mapping[str, object],
    clean_source: Mapping[str, object], native: str,
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]], str, list[bool] | None, str]:
    factual, clean = [factual_parent], [clean_parent]
    if regime == "persistent" or depth <= 2:
        selected = "NONE"
        success = None
        feedback = "Preserve the most reusable procedural regularity from retrieved experience during this offline consolidation."
    elif regime == "recovery":
        selected = native
        success = None
        feedback = "Treat the verified target replay as authoritative and correct prior advice that conflicts with it."
    elif regime == "revival" and depth == 3:
        selected = native
        success = None
        feedback = "Treat the verified target replay as authoritative and record the current correction."
    elif regime == "revival" and depth == 4:
        factual.insert(0, factual_source); clean.insert(0, clean_source)
        selected = "NONE"
        success = None
        feedback = "Reconcile the older formation experience with the recent correction; preserve any procedure that appears reusable across both."
    elif regime == "revival":
        selected = "NONE"
        success = None
        feedback = "Consolidate the retrieved experience into a reusable rule while retaining its operative procedural recommendation."
    else:
        raise ValueError(regime)
    # Recovery steps are the only descendants that observe a target replay.
    if regime == "recovery" and depth >= 3 or regime == "revival" and depth == 3:
        success = [False, True]
    return factual, clean, selected, success, feedback


def generate_task(
    backend, task: Mapping[str, object], batch_size: int, prompt_version: str,
) -> dict[str, object]:
    task_id = str(task["task_id"]); language = str(task["target_language"])
    native = str(task["native_policy"]); donors = list(task["donors"])
    donor_policies = [str(value["policy"]) for value in donors]
    allowed_all = donor_policies + [native]
    success_all = [False, False, False, True]
    graph = graph_spec(task_id)
    source_ids = graph["source_ids"]
    branches = graph["branch_ids"]
    forbidden_all = list(source_ids) + list(graph["candidate_ids"]) + allowed_all

    roots_raw = run_jobs(backend, [
        root_job
        for source, donor in zip(source_ids, donors)
        for root_job in root_pair_jobs(task, source, donor, prompt_version)
    ], batch_size)
    roots = []
    for index, (source, donor) in enumerate(zip(source_ids, donors)):
        roots.append({
            "source_id": source, "donor": donor,
            "factual": roots_raw[index * 2], "counterfactual": roots_raw[index * 2 + 1],
        })

    variants: dict[str, dict[object, dict[str, object]]] = {}
    branch_records = []
    for branch_index, (nodes, donor, root, regime) in enumerate(zip(
        branches, donors, roots, regime_order(task_id)
    )):
        bad = str(donor["policy"])
        factual_source = parsed_record(str(root["source_id"]), root["factual"])
        clean_source = parsed_record(str(root["source_id"]), root["counterfactual"])
        factual_parent, clean_parent = factual_source, clean_source
        records = []
        for depth, memory_id in enumerate(nodes, start=1):
            factual_retrieved, clean_retrieved, selected, observed_success, feedback = branch_inputs(
                regime, depth, factual_parent, clean_parent, factual_source, clean_source, native
            )
            common = dict(memory_id=memory_id, depth=depth, task=language,
                          selected=selected, allowed=[bad, native],
                          success=observed_success, feedback=feedback,
                          prompt_version=prompt_version)
            prompts = (
                make_prompt(**common, retrieved=factual_retrieved),
                make_prompt(**common, retrieved=clean_retrieved),
            )
            generated = run_jobs(backend, [
                job(prompts[0], language, [bad, native], factual_retrieved, forbidden_all),
                job(prompts[1], language, [bad, native], clean_retrieved, forbidden_all),
            ], batch_size)
            factual_parent = parsed_record(memory_id, generated[0])
            clean_parent = parsed_record(memory_id, generated[1])
            variants[memory_id] = {branch_index: factual_parent, "clean": clean_parent}
            records.append({"memory_id": memory_id, "depth": depth,
                            "factual": generated[0], "counterfactual": generated[1]})
        branch_records.append({"branch": branch_index, "regime": regime, "memories": records})

    parent_map: dict[str, list[str]] = {node: [] for node in graph["candidate_ids"]}
    for left, right in graph["formation_edges"]:
        if right in parent_map:
            parent_map[right].append(left)
    node_branch = {node: index for index, values in enumerate(branches) for node in values}
    shared_records = []
    for shared_id in graph["shared_ids"]:
        generated_variants: dict[str, object] = {}
        jobs = []
        state_keys: list[object] = [0, 1, 2, "clean"]
        retrieved_by_state = []
        for state in state_keys:
            retrieved = []
            for parent in parent_map[shared_id]:
                if parent in node_branch:
                    active = state == node_branch[parent]
                    retrieved.append(variants[parent][node_branch[parent] if active else "clean"])
                else:
                    retrieved.append(variants[parent][state])
            influenced = state != "clean" and any(
                value != variants[parent]["clean"]
                for parent, value in zip(parent_map[shared_id], retrieved)
            )
            if influenced:
                # Active descendants rank first under content-based retrieval;
                # the set of observed parents and the formation graph stay fixed.
                active = int(state)
                retrieved.sort(key=lambda value: (
                    str(value["recommended_policy_id"]) == native,
                    str(value["memory_id"]),
                ))
            retrieved_by_state.append(retrieved)
            prompt = make_prompt(
                memory_id=shared_id, depth=3, task=language, retrieved=retrieved,
                selected="NONE", allowed=allowed_all, success=None,
                feedback="Synthesize the retrieved histories. If recommendations conflict without a target replay, retain the highest-ranked first memory's operative procedure.",
                prompt_version=prompt_version,
            )
            jobs.append(job(prompt, language, allowed_all, retrieved, forbidden_all))
        outputs = run_jobs(backend, jobs, batch_size)
        for state, output in zip(state_keys, outputs):
            key = "clean" if state == "clean" else f"active_{state}"
            generated_variants[key] = output
        variants[shared_id] = {
            state: parsed_record(shared_id, output)
            for state, output in zip(state_keys, outputs)
        }
        shared_records.append({"memory_id": shared_id, "parents": parent_map[shared_id],
                               "variants": generated_variants})

    return {
        "task_id": task_id, "benchmark": task["benchmark"], "stratum": task["stratum"],
        "split": task["split"], "target_name": task["target_name"],
        "target_language": language, "native_policy": native, "donors": donors,
        "policy_success": {**{policy: False for policy in donor_policies}, native: True, "NONE": False},
        "graph": graph, "roots": roots, "branches": branch_records,
        "shared_memories": shared_records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "validation", "test", "all"), default="all")
    parser.add_argument("--limit-per-benchmark", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed-ledger", type=Path)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()
    population = json.loads(args.population.read_text(encoding="utf-8"))
    freeze = json.loads(args.config.read_text(encoding="utf-8")); validate_freeze(freeze)
    prompt_version = str(freeze.get("prompt_version", LEGACY_PROMPT_VERSION))
    if population.get("protocol") != f"{PROTOCOL}/production-population" or population.get("task_count") != 69:
        raise ValueError("frozen 69-task production population required")
    selected = [row for row in population["tasks"]
                if args.split == "all" or row["split"] == args.split]
    if args.limit_per_benchmark is not None:
        selected = [row for benchmark in ("libero", "metaworld") for row in sorted(
            (item for item in selected if item["benchmark"] == benchmark),
            key=lambda item: (stable_digest("pilot", item["task_id"]), item["task_id"]),
        )[:args.limit_per_benchmark]]
    if args.shard_count <= 0 or not 0 <= args.shard_index < args.shard_count:
        raise ValueError("invalid shard specification")
    selected = [row for index, row in enumerate(selected)
                if index % args.shard_count == args.shard_index]
    selected_ids = [row["task_id"] for row in selected]
    config = config_from_env(backend="qwen", generation=GenerationSettings(max_new_tokens=256))
    payload = {
        "protocol": f"{PROTOCOL}/generation", "prompt_version": prompt_version,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "population_path": str(args.population),
        "population_sha256": hashlib.sha256(args.population.read_bytes()).hexdigest(),
        "freeze_path": str(args.config), "freeze_payload": freeze,
        "selection": {"split": args.split, "limit_per_benchmark": args.limit_per_benchmark,
                      "shard_count": args.shard_count, "shard_index": args.shard_index,
                      "task_ids": selected_ids},
        "model": config.as_log_dict(), "expected_tasks": len(selected),
        "complete": False, "archives": [],
    }
    if args.seed_ledger and not args.output.exists():
        seed = json.loads(args.seed_ledger.read_text(encoding="utf-8"))
        if seed.get("protocol") != f"{PROTOCOL}/generation":
            raise ValueError("v2 seed generation ledger required")
        if seed.get("prompt_version") != prompt_version:
            raise ValueError("seed writer prompt differs from frozen writer")
        allowed_seed_ids = set(selected_ids)
        seeded = [row for row in seed["archives"] if row["task_id"] in allowed_seed_ids]
        if len(seeded) != len({row["task_id"] for row in seeded}):
            raise ValueError("seed ledger contains duplicate selected tasks")
        payload["seed_ledger"] = str(args.seed_ledger)
        payload["seed_ledger_sha256"] = hashlib.sha256(args.seed_ledger.read_bytes()).hexdigest()
        payload["archives"] = seeded
        checkpoint(args.output, payload)
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != f"{PROTOCOL}/generation" or payload.get("selection", {}).get("task_ids") != selected_ids:
            raise ValueError("generation checkpoint selection is incompatible")
        if payload.get("freeze_payload") != freeze:
            raise ValueError("generation freeze changed since checkpoint")
    completed = {row["task_id"] for row in payload["archives"]}
    backend = build_backend(config)
    batch_size = int(freeze["generation_batch_size"])
    for task in selected:
        if task["task_id"] in completed:
            print(f"{task['task_id']} already complete", flush=True); continue
        record = generate_task(backend, task, batch_size, prompt_version)
        payload["archives"].append(record); checkpoint(args.output, payload)
        print(f"generated {len(payload['archives'])}/{len(selected)} {task['task_id']}", flush=True)
    payload["complete"] = len(payload["archives"]) == len(selected)
    payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    checkpoint(args.output, payload)


if __name__ == "__main__":
    main()
