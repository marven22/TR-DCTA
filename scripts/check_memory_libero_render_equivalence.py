"""Check that physics-only LIBERO replay matches camera-observation replay."""
from __future__ import annotations

import json
import time

from libero.libero import benchmark

from run_memory_libero_transfer_screen import load_demos, make_env, replay


def main() -> None:
    suite = benchmark.get_benchmark_dict()["libero_spatial"]()
    demo = load_demos(suite, 0, (0,))[0]
    outcomes = {}
    for label, use_camera_obs in (("camera_observations", True), ("physics_only", False)):
        env = make_env(suite, 0, 32, use_camera_obs)
        env.seed(0)
        started = time.perf_counter()
        outcome = replay(env, demo["init_state"], demo["actions"])
        outcome["elapsed_seconds"] = time.perf_counter() - started
        outcomes[label] = outcome
        env.close()
    equivalent = (
        outcomes["camera_observations"]["success"]
        == outcomes["physics_only"]["success"]
        and outcomes["camera_observations"]["first_success_step"]
        == outcomes["physics_only"]["first_success_step"]
        and outcomes["camera_observations"]["final_state_sha256"]
        == outcomes["physics_only"]["final_state_sha256"]
    )
    print(json.dumps({"equivalent": equivalent, "outcomes": outcomes}, indent=2))
    if not equivalent:
        raise SystemExit("Physics-only replay changed the scientific outcome")


if __name__ == "__main__":
    main()
