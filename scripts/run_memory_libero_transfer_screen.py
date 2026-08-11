"""Screen LIBERO-Spatial policy transfers for deterministic failure pairs.

Run this script inside the isolated LIBERO Python environment under WSL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Dict, Sequence

import h5py
import numpy as np

from libero.libero import benchmark, get_libero_path
from libero.libero.envs import OffScreenRenderEnv
from libero.libero.envs.env_wrapper import ControlEnv


PROTOCOL = "memory-libero/source-conditioned-provenance-pilot-v0.1"
LIBERO_COMMIT = "8f1084e3132a39270c3a13ebe37270a43ece2a01"


def load_demos(suite, task_index: int, demo_indices: Sequence[int]) -> Dict[int, dict]:
    path = Path(get_libero_path("datasets")) / suite.get_task_demonstration(task_index)
    result = {}
    with h5py.File(path, "r") as handle:
        for demo_index in demo_indices:
            demo = handle["data"][f"demo_{demo_index}"]
            result[demo_index] = {
                "actions": demo["actions"][()].astype(np.float64),
                "init_state": np.asarray(demo.attrs["init_state"], dtype=np.float64),
                "stored_success": bool(np.max(demo["rewards"][()])),
                "action_sha256": hashlib.sha256(
                    demo["actions"][()].astype(np.float64).tobytes()
                ).hexdigest(),
            }
    return result


def replay(env, init_state: np.ndarray, actions: np.ndarray) -> dict:
    env.reset()
    env.set_init_state(init_state)
    rewards = []
    for action in actions:
        _, reward, _, _ = env.step(action)
        rewards.append(float(reward))
    state = np.asarray(env.sim.get_state().flatten(), dtype=np.float64)
    return {
        "steps": int(len(actions)),
        "success": bool(max(rewards, default=0.0)),
        "first_success_step": next(
            (index for index, reward in enumerate(rewards) if reward > 0.0), None
        ),
        "final_reward": rewards[-1] if rewards else 0.0,
        "final_state_sha256": hashlib.sha256(state.tobytes()).hexdigest(),
    }


def make_env(suite, task_index: int, camera_size: int, use_camera_obs: bool):
    common = {
        "bddl_file_name": suite.get_task_bddl_file_path(task_index),
        "camera_heights": camera_size,
        "camera_widths": camera_size,
    }
    if use_camera_obs:
        return OffScreenRenderEnv(**common)
    return ControlEnv(
        **common,
        use_camera_obs=False,
        has_renderer=False,
        has_offscreen_renderer=False,
    )


def write_checkpoint(
    path: Path,
    task_names: Sequence[str],
    replays: Sequence[dict],
    use_camera_obs: bool,
) -> None:
    completed_targets = sorted({row["target_index"] for row in replays})
    payload = {
        "protocol": PROTOCOL,
        "libero_commit": LIBERO_COMMIT,
        "suite": "libero_spatial",
        "complete": False,
        "rendering_mode": "camera_observations" if use_camera_obs else "physics_only",
        "demo_indices": [0, 1],
        "task_count": len(task_names),
        "completed_target_indices": completed_targets,
        "replay_count": len(replays),
        "task_names": list(task_names),
        "replays": list(replays),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--camera-size", type=int, default=32)
    parser.add_argument("--use-camera-obs", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a compatible incomplete checkpoint at --output.",
    )
    args = parser.parse_args()

    suite = benchmark.get_benchmark_dict()["libero_spatial"]()
    task_names = suite.get_task_names()
    demos = {
        task_index: load_demos(suite, task_index, (0, 1))
        for task_index in range(suite.get_num_tasks())
    }
    replays = []
    if args.resume and args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        expected_mode = "camera_observations" if args.use_camera_obs else "physics_only"
        if checkpoint.get("protocol") != PROTOCOL:
            raise ValueError("Checkpoint protocol does not match this runner")
        if checkpoint.get("rendering_mode") != expected_mode:
            raise ValueError("Checkpoint rendering mode does not match this run")
        replays = checkpoint.get("replays", [])
    completed_targets = {row["target_index"] for row in replays}
    for target_index, target_name in enumerate(task_names):
        if target_index in completed_targets:
            print(f"target {target_index + 1}/{len(task_names)} already complete", flush=True)
            continue
        started = time.perf_counter()
        env = make_env(suite, target_index, args.camera_size, args.use_camera_obs)
        env.seed(0)
        for donor_index, donor_name in enumerate(task_names):
            for demo_index in (0, 1):
                outcome = replay(
                    env,
                    demos[target_index][demo_index]["init_state"],
                    demos[donor_index][demo_index]["actions"],
                )
                replays.append({
                    "target_index": target_index,
                    "target_name": target_name,
                    "target_language": suite.get_task(target_index).language,
                    "donor_index": donor_index,
                    "donor_name": donor_name,
                    "donor_language": suite.get_task(donor_index).language,
                    "demo_index": demo_index,
                    "donor_action_sha256": demos[donor_index][demo_index]["action_sha256"],
                    "donor_stored_success": demos[donor_index][demo_index]["stored_success"],
                    **outcome,
                })
        env.close()
        write_checkpoint(args.output, task_names, replays, args.use_camera_obs)
        print(
            f"target {target_index + 1}/{len(task_names)} complete "
            f"({time.perf_counter() - started:.1f}s; {len(replays)} replays)",
            flush=True,
        )

    by_key = {
        (row["target_index"], row["donor_index"], row["demo_index"]): row
        for row in replays
    }
    selected_pairs = []
    for target_index, target_name in enumerate(task_names):
        native_ok = all(
            by_key[(target_index, target_index, demo_index)]["success"]
            for demo_index in (0, 1)
        )
        eligible = []
        if native_ok:
            for donor_index, donor_name in enumerate(task_names):
                if donor_index == target_index:
                    continue
                if all(
                    not by_key[(target_index, donor_index, demo_index)]["success"]
                    for demo_index in (0, 1)
                ):
                    eligible.append((donor_name, donor_index))
        if eligible:
            donor_name, donor_index = sorted(eligible)[0]
            selected_pairs.append({
                "target_index": target_index,
                "target_name": target_name,
                "target_language": suite.get_task(target_index).language,
                "donor_index": donor_index,
                "donor_name": donor_name,
                "donor_language": suite.get_task(donor_index).language,
                "eligible_donor_count": len(eligible),
            })

    # Rerun the selected native and donor policies twice to verify outcome and
    # final-state determinism independently of the screen pass.
    verification = []
    for pair in selected_pairs:
        target_index = pair["target_index"]
        env = make_env(suite, target_index, args.camera_size, args.use_camera_obs)
        env.seed(0)
        for role, donor_index in (
            ("native", target_index),
            ("donor", pair["donor_index"]),
        ):
            for demo_index in (0, 1):
                outcomes = [
                    replay(
                        env,
                        demos[target_index][demo_index]["init_state"],
                        demos[donor_index][demo_index]["actions"],
                    )
                    for _ in range(2)
                ]
                verification.append({
                    "target_index": target_index,
                    "donor_index": donor_index,
                    "role": role,
                    "demo_index": demo_index,
                    "outcomes": outcomes,
                    "deterministic": (
                        outcomes[0]["success"] == outcomes[1]["success"]
                        and outcomes[0]["final_state_sha256"]
                        == outcomes[1]["final_state_sha256"]
                    ),
                })
        env.close()

    payload = {
        "protocol": PROTOCOL,
        "libero_commit": LIBERO_COMMIT,
        "suite": "libero_spatial",
        "complete": True,
        "rendering_mode": (
            "camera_observations" if args.use_camera_obs else "physics_only"
        ),
        "demo_indices": [0, 1],
        "task_count": len(task_names),
        "replay_count": len(replays),
        "selected_pair_count": len(selected_pairs),
        "feasibility_gate_passed": len(selected_pairs) >= 5,
        "task_names": task_names,
        "selected_pairs": selected_pairs,
        "verification": verification,
        "replays": replays,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        key: payload[key]
        for key in (
            "protocol", "task_count", "replay_count", "selected_pair_count",
            "feasibility_gate_passed", "selected_pairs",
        )
    }, indent=2))


if __name__ == "__main__":
    main()
