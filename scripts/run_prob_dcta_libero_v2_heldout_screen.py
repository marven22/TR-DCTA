"""Fresh three-donor simulator screen for the frozen v2 held-out tasks.

Run inside the pinned WSL LIBERO environment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from libero.libero import benchmark

from run_memory_libero_transfer_screen import LIBERO_COMMIT, load_demos, make_env, replay

from mcx.libero_publication_v2 import (
    PROTOCOL, donor_order, feasibility_gate, validate_manifest,
)


def checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def replay_record(env, demos, target: int, policy: int, demo: int, repeat: int) -> dict:
    result = replay(
        env, demos[target][demo]["init_state"], demos[policy][demo]["actions"]
    )
    return {
        "policy_task_index": policy,
        "demo_index": demo,
        "repeat": repeat,
        "action_sha256": demos[policy][demo]["action_sha256"],
        **result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    payload = {
        "protocol": f"{PROTOCOL}/heldout-screen",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "libero_commit": LIBERO_COMMIT,
        "manifest": str(args.manifest),
        "manifest_payload": manifest,
        "rendering_mode": "physics_only",
        "complete": False,
        "targets": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != f"{PROTOCOL}/heldout-screen":
            raise ValueError("incompatible v2 screen checkpoint")
        if payload.get("manifest_payload") != manifest:
            raise ValueError("held-out manifest changed since checkpoint")
    completed = {(row["suite"], int(row["target_index"])) for row in payload["targets"]}
    benchmark_dict = benchmark.get_benchmark_dict()
    for suite_name, entry in manifest["suites"].items():
        suite = benchmark_dict[suite_name]()
        task_count = suite.get_num_tasks()
        expected_count = 90 if suite_name == "libero_90" else 10
        if task_count != expected_count:
            raise ValueError(f"unexpected task count for {suite_name}: {task_count}")
        demos_indices = tuple(int(value) for value in entry["demo_indices"])
        demos = {index: load_demos(suite, index, demos_indices)
                 for index in range(task_count)}
        names = suite.get_task_names()
        for target in entry["task_indices"]:
            target = int(target)
            if (suite_name, target) in completed:
                print(f"{suite_name}/{target} already complete", flush=True)
                continue
            started = time.perf_counter()
            env = make_env(suite, target, 32, False)
            env.seed(0)
            try:
                native = [
                    replay_record(env, demos, target, target, demo, repeat)
                    for demo in demos_indices for repeat in (0, 1)
                ]
                donors = []
                tested = []
                if all(row["success"] for row in native):
                    for donor in donor_order(suite_name, target, task_count):
                        outcomes = [
                            replay_record(env, demos, target, donor, demo, repeat)
                            for demo in demos_indices for repeat in (0, 1)
                        ]
                        verified_failure = all(not row["success"] for row in outcomes)
                        tested.append({
                            "donor_index": donor,
                            "donor_name": names[donor],
                            "donor_language": suite.get_task(donor).language,
                            "outcomes": outcomes,
                            "verified_failure": verified_failure,
                        })
                        if verified_failure:
                            donors.append(tested[-1])
                            if len(donors) == int(manifest["required_donors_per_target"]):
                                break
                eligible = len(donors) == int(manifest["required_donors_per_target"])
                payload["targets"].append({
                    "suite": suite_name,
                    "target_index": target,
                    "target_name": names[target],
                    "target_language": suite.get_task(target).language,
                    "demo_indices": list(demos_indices),
                    "native": native,
                    "native_verified": all(row["success"] for row in native),
                    "donor_order": list(donor_order(suite_name, target, task_count)),
                    "tested_donors": tested,
                    "selected_donors": donors,
                    "eligible": eligible,
                    "elapsed_seconds": time.perf_counter() - started,
                })
            finally:
                env.close()
            checkpoint(args.output, payload)
            latest = payload["targets"][-1]
            print(
                f"{suite_name}/{target}: eligible={latest['eligible']} "
                f"donors={len(latest['selected_donors'])} "
                f"({latest['elapsed_seconds']:.1f}s)", flush=True,
            )
    eligible = [row for row in payload["targets"] if row["eligible"]]
    gate = feasibility_gate(eligible, manifest)
    payload.update({
        "complete": len(payload["targets"]) == 40,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "eligible_targets": [{
            "suite": row["suite"],
            "target_index": row["target_index"],
            "target_name": row["target_name"],
            "target_language": row["target_language"],
            "demo_indices": row["demo_indices"],
            "donors": [{
                "donor_index": donor["donor_index"],
                "donor_name": donor["donor_name"],
                "donor_language": donor["donor_language"],
            } for donor in row["selected_donors"]],
        } for row in eligible],
        "feasibility_gate": gate,
    })
    checkpoint(args.output, payload)
    print(json.dumps({
        "complete": payload["complete"],
        "feasibility_gate": gate,
    }, indent=2))


if __name__ == "__main__":
    main()
