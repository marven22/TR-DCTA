"""Deterministically screen untouched LIBERO-90 target/donor policy pairs.

Run under the frozen WSL LIBERO environment.  The script checkpoints after
every target and never selects a donor by inspecting aggregate study outcomes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from libero.libero import benchmark

from run_memory_libero_transfer_screen import (
    LIBERO_COMMIT, load_demos, make_env, replay,
)


PROTOCOL = "memory-libero/external-validation-v1/screen"
SUITE = "libero_90"
DEMO_INDICES = (0, 1)
MAX_DONORS = 12


def donor_order(target: int, task_count: int) -> list[int]:
    candidates = [index for index in range(task_count) if index != target]
    return sorted(candidates, key=lambda donor: (
        hashlib.sha256(f"{PROTOCOL}|{target}|{donor}".encode()).digest(), donor
    ))


def checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def outcome_record(role: str, policy_task: int, demo_index: int, result: dict,
                   action_sha256: str) -> dict:
    return {
        "role": role, "policy_task_index": policy_task,
        "demo_index": demo_index, "action_sha256": action_sha256, **result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    suite = benchmark.get_benchmark_dict()[SUITE]()
    task_count = suite.get_num_tasks()
    if task_count != 90:
        raise ValueError(f"frozen protocol requires 90 tasks, found {task_count}")
    names = suite.get_task_names()
    payload = {
        "protocol": PROTOCOL, "libero_commit": LIBERO_COMMIT, "suite": SUITE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": False, "rendering_mode": "physics_only",
        "demo_indices": list(DEMO_INDICES), "max_donors": MAX_DONORS,
        "task_count": task_count, "task_names": names, "targets": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != PROTOCOL or payload.get("task_count") != task_count:
            raise ValueError("incompatible external-v1 screen checkpoint")
    completed = {row["target_index"] for row in payload["targets"]}

    # Only two small action/state arrays are retained per task; images remain on disk.
    demos = {index: load_demos(suite, index, DEMO_INDICES)
             for index in range(task_count)}
    for target in range(task_count):
        if target in completed:
            print(f"target {target + 1}/{task_count} already complete", flush=True)
            continue
        started = time.perf_counter()
        env = make_env(suite, target, 32, False)
        env.seed(0)
        try:
            native = []
            for demo_index in DEMO_INDICES:
                native.append(outcome_record(
                    "native", target, demo_index,
                    replay(env, demos[target][demo_index]["init_state"],
                           demos[target][demo_index]["actions"]),
                    demos[target][demo_index]["action_sha256"],
                ))
            tested = []
            selected = None
            if all(row["success"] for row in native):
                for donor in donor_order(target, task_count)[:MAX_DONORS]:
                    outcomes = []
                    for demo_index in DEMO_INDICES:
                        outcomes.append(outcome_record(
                            "donor", donor, demo_index,
                            replay(env, demos[target][demo_index]["init_state"],
                                   demos[donor][demo_index]["actions"]),
                            demos[donor][demo_index]["action_sha256"],
                        ))
                    tested.append({"donor_index": donor, "outcomes": outcomes})
                    if all(not row["success"] for row in outcomes):
                        selected = donor
                        break
            verification = []
            if selected is not None:
                for role, policy_task in (("native", target), ("donor", selected)):
                    for demo_index in DEMO_INDICES:
                        verification.append(outcome_record(
                            role, policy_task, demo_index,
                            replay(env, demos[target][demo_index]["init_state"],
                                   demos[policy_task][demo_index]["actions"]),
                            demos[policy_task][demo_index]["action_sha256"],
                        ))
            deterministic = bool(selected is not None) and all(
                first["success"] == second["success"]
                for first, second in zip(native + tested[-1]["outcomes"], verification)
            )
            verified = deterministic and all(row["success"] for row in verification[:2]) \
                and all(not row["success"] for row in verification[2:])
            payload["targets"].append({
                "target_index": target, "target_name": names[target],
                "target_language": suite.get_task(target).language,
                "native": native, "donor_order": donor_order(target, task_count)[:MAX_DONORS],
                "tested_donors": tested,
                "selected_donor_index": selected,
                "selected_donor_name": names[selected] if selected is not None else None,
                "selected_donor_language": (
                    suite.get_task(selected).language if selected is not None else None
                ),
                "verification": verification, "deterministic": deterministic,
                "verified": verified,
                "elapsed_seconds": time.perf_counter() - started,
            })
        finally:
            env.close()
        checkpoint(args.output, payload)
        print(
            f"target {target + 1}/{task_count} complete; "
            f"verified={payload['targets'][-1]['verified']} "
            f"({payload['targets'][-1]['elapsed_seconds']:.1f}s)", flush=True,
        )

    verified_count = sum(row["verified"] for row in payload["targets"])
    payload.update({
        "complete": len(payload["targets"]) == task_count,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "verified_pair_count": verified_count,
        "feasibility_gate_passed": verified_count >= 60,
    })
    checkpoint(args.output, payload)
    print(json.dumps({
        "complete": payload["complete"], "verified_pair_count": verified_count,
        "feasibility_gate_passed": payload["feasibility_gate_passed"],
    }, indent=2))


if __name__ == "__main__":
    main()
