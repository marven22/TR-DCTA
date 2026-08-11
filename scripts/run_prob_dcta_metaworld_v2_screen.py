"""Frozen native/cross-policy screen for the Meta-World v2 extension."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import time
from typing import Any

import gymnasium as gym
import metaworld
import mujoco
import numpy as np
from metaworld.policies import ENV_POLICY_MAP

from mcx.metaworld_publication_v2 import (
    PROTOCOL,
    action_is_valid,
    donor_order,
    task_language,
    validate_config,
)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def evaluate(target: str, policy_name: str, seed: int) -> dict[str, Any]:
    """Run one fresh deterministic episode and retain an auditable action hash."""
    started = time.perf_counter()
    action_digest = hashlib.sha256()
    success_once = False
    steps = 0
    error = None
    env = None
    try:
        env = gym.make("Meta-World/MT1", env_name=target, seed=seed)
        observation, _ = env.reset(seed=seed)
        policy = ENV_POLICY_MAP[policy_name]()
        horizon = int(env.spec.max_episode_steps or 500)
        for _ in range(horizon):
            action = np.asarray(policy.get_action(observation), dtype=np.float64)
            if not action_is_valid(action):
                raise ValueError(f"invalid action shape/values: {action!r}")
            action_digest.update(action.tobytes(order="C"))
            observation, _, terminated, truncated, info = env.step(action)
            steps += 1
            success_once = success_once or bool(info.get("success", False))
            if terminated or truncated:
                break
    except Exception as exc:  # Cross-task scripted policies can reject alien states.
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if env is not None:
            env.close()
    return {
        "seed": seed,
        "policy_name": policy_name,
        "success": success_once,
        "valid": error is None,
        "steps": steps,
        "action_sha256": action_digest.hexdigest(),
        "error": error,
        "elapsed_seconds": time.perf_counter() - started,
    }


def package_fingerprint() -> dict[str, Any]:
    policy_path = Path(metaworld.__file__).parent / "policies" / "__init__.py"
    return {
        "python_packages": {
            "metaworld": metadata.version("metaworld"),
            "mujoco": metadata.version("mujoco"),
            "gymnasium": metadata.version("gymnasium"),
            "numpy": metadata.version("numpy"),
        },
        "metaworld_module": str(Path(metaworld.__file__).resolve()),
        "metaworld_init_sha256": file_sha256(metaworld.__file__),
        "policy_map_module": str(policy_path.resolve()),
        "policy_map_sha256": file_sha256(policy_path),
        "mujoco_runtime_version": mujoco.__version__,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    task_names = tuple(sorted(ENV_POLICY_MAP))
    if len(task_names) != 50 or any(not name.endswith("-v3") for name in task_names):
        raise ValueError(f"unexpected Meta-World policy population: {len(task_names)}")

    payload: dict[str, Any] = {
        "protocol": f"{PROTOCOL}/metaworld-screen",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(args.config),
        "config_payload": config,
        "fingerprint": package_fingerprint(),
        "task_population": list(task_names),
        "complete": False,
        "targets": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != f"{PROTOCOL}/metaworld-screen":
            raise ValueError("incompatible Meta-World v2 checkpoint")
        if payload.get("config_payload") != config:
            raise ValueError("screen configuration changed since checkpoint")
        if payload.get("task_population") != list(task_names):
            raise ValueError("Meta-World task population changed since checkpoint")

    completed = {row["target_name"] for row in payload["targets"]}
    seeds = tuple(int(seed) for seed in config["seeds"])
    required = int(config["required_donors_per_target"])
    for target in task_names:
        if target in completed:
            print(f"{target} already complete", flush=True)
            continue
        started = time.perf_counter()
        native = [evaluate(target, target, seed) for seed in seeds]
        native_verified = all(row["valid"] and row["success"] for row in native)
        tested_donors: list[dict[str, Any]] = []
        selected_donors: list[dict[str, Any]] = []
        order = donor_order(target, task_names)
        if native_verified:
            for donor in order:
                outcomes = [evaluate(target, donor, seed) for seed in seeds]
                valid = all(row["valid"] for row in outcomes)
                verified_failure = valid and all(not row["success"] for row in outcomes)
                record = {
                    "donor_name": donor,
                    "donor_language": task_language(donor),
                    "outcomes": outcomes,
                    "valid": valid,
                    "verified_failure": verified_failure,
                }
                tested_donors.append(record)
                if verified_failure:
                    selected_donors.append(record)
                    if len(selected_donors) == required:
                        break
        record = {
            "target_name": target,
            "target_language": task_language(target),
            "native": native,
            "native_verified": native_verified,
            "donor_order": list(order),
            "tested_donors": tested_donors,
            "selected_donors": selected_donors,
            "eligible": len(selected_donors) == required,
            "elapsed_seconds": time.perf_counter() - started,
        }
        payload["targets"].append(record)
        checkpoint(args.output, payload)
        print(
            f"{target}: native={native_verified} eligible={record['eligible']} "
            f"donors={len(selected_donors)} ({record['elapsed_seconds']:.1f}s)",
            flush=True,
        )

    eligible = [row for row in payload["targets"] if row["eligible"]]
    minimum = int(config["minimum_eligible_targets"])
    payload.update({
        "complete": len(payload["targets"]) == len(task_names),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "eligible_targets": [{
            "target_name": row["target_name"],
            "target_language": row["target_language"],
            "donors": [{
                "donor_name": donor["donor_name"],
                "donor_language": donor["donor_language"],
            } for donor in row["selected_donors"]],
        } for row in eligible],
        "feasibility_gate": {
            "eligible_target_count": len(eligible),
            "minimum_eligible_targets": minimum,
            "passed": len(eligible) >= minimum,
        },
    })
    checkpoint(args.output, payload)
    print(json.dumps({
        "complete": payload["complete"],
        "feasibility_gate": payload["feasibility_gate"],
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
