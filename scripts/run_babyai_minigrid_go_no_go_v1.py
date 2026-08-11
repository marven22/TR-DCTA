"""Run the frozen BabyAI/MiniGrid structural go/no-go audit."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "babyai_minigrid_go_no_go_freeze_v1.json"
OUTPUT_PATH = ROOT / "reports" / "babyai_minigrid_go_no_go_v1.json"

DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]


def target_color(mission: str) -> str:
    match = re.search(r"open the (\w+) door", mission)
    if not match:
        raise ValueError(f"Unsupported mission: {mission}")
    return match.group(1)


def make_env(env_id: str):
    import gymnasium as gym
    import minigrid  # noqa: F401

    return gym.make(env_id, render_mode=None)


def passable(env, pos: tuple[int, int]) -> bool:
    x, y = pos
    if x < 0 or y < 0 or x >= env.width or y >= env.height:
        return False
    obj = env.grid.get(x, y)
    return obj is None or obj.can_overlap()


def shortest_path(env, start: tuple[int, int], goals: set[tuple[int, int]]):
    queue = deque([start])
    prev = {start: None}
    while queue:
        pos = queue.popleft()
        if pos in goals:
            path = []
            while pos is not None:
                path.append(pos)
                pos = prev[pos]
            return path[::-1]
        for dx, dy in DIRS:
            nxt = (pos[0] + dx, pos[1] + dy)
            if nxt not in prev and passable(env, nxt):
                prev[nxt] = pos
                queue.append(nxt)
    return None


def actions_to_path(path: list[tuple[int, int]], start_dir: int, final_face: int) -> list[int]:
    actions = []
    direction = int(start_dir)
    for src, dst in zip(path, path[1:]):
        wanted = DIRS.index((dst[0] - src[0], dst[1] - src[1]))
        while direction != wanted:
            if (wanted - direction) % 4 == 1:
                actions.append(1)  # right
                direction = (direction + 1) % 4
            else:
                actions.append(0)  # left
                direction = (direction - 1) % 4
        actions.append(2)  # forward
    while direction != final_face:
        if (final_face - direction) % 4 == 1:
            actions.append(1)
            direction = (direction + 1) % 4
        else:
            actions.append(0)
            direction = (direction - 1) % 4
    actions.append(5)  # toggle
    actions.append(6)  # done
    return actions


def candidate_doors(env, color: str):
    candidates = []
    for x in range(env.width):
        for y in range(env.height):
            obj = env.grid.get(x, y)
            if obj is None or obj.type != "door" or obj.color != color:
                continue
            for direction, (dx, dy) in enumerate(DIRS):
                adjacent = (x + dx, y + dy)
                face_door = (direction + 2) % 4
                if not passable(env, adjacent):
                    continue
                path = shortest_path(env, tuple(env.agent_pos), {adjacent})
                if path is not None:
                    candidates.append({
                        "door": (x, y),
                        "path": path,
                        "face": face_door,
                        "distance": len(path),
                    })
    return sorted(candidates, key=lambda row: (row["distance"], row["door"]))


def plan(env, color: str, variant: str) -> list[int]:
    candidates = candidate_doors(env, color)
    if not candidates:
        return [6]
    if variant == "nearest":
        selected = candidates[0]
    elif variant == "farthest":
        selected = candidates[-1]
    elif variant == "middle":
        selected = candidates[len(candidates) // 2]
    else:
        raise ValueError(f"Unknown strategy variant: {variant}")
    return actions_to_path(selected["path"], int(env.agent_dir), int(selected["face"]))


def execute(env_id: str, seed: int, color: str, variant: str, max_steps: int) -> dict:
    env = make_env(env_id)
    obs, _ = env.reset(seed=int(seed))
    mission = obs["mission"]
    actual_target = target_color(mission)
    actions = plan(env.unwrapped, color, variant)
    reward = 0.0
    terminated = False
    truncated = False
    steps = 0
    for action in actions[:max_steps]:
        obs, reward, terminated, truncated, _ = env.step(action)
        steps += 1
        if terminated or truncated:
            break
    env.close()
    return {
        "mission": mission,
        "target_color": actual_target,
        "strategy_color": color,
        "variant": variant,
        "steps": steps,
        "planned_steps": len(actions),
        "success": bool(terminated and reward > 0.0),
        "reward": float(reward),
        "terminated": bool(terminated),
        "truncated": bool(truncated),
    }


def select_contexts(config: dict) -> list[dict]:
    env_id = config["env_id"]
    contexts = []
    color_counts = Counter()
    for seed in range(int(config["seed_scan_limit"])):
        env = make_env(env_id)
        obs, _ = env.reset(seed=seed)
        color = target_color(obs["mission"])
        env.close()
        if color not in config["strategy_colors"]:
            continue
        contexts.append({"seed": seed, "mission": obs["mission"], "target_color": color})
        color_counts[color] += 1
        if len(contexts) >= int(config["num_contexts"]):
            break
    if len(contexts) < int(config["num_contexts"]):
        raise RuntimeError(f"Only found {len(contexts)} contexts")
    return contexts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    started = time.perf_counter()
    contexts = select_contexts(config)
    outcomes = []
    errors = []
    for context in contexts:
        for color in config["strategy_colors"]:
            for variant in config["strategy_variants"]:
                try:
                    row = execute(
                        config["env_id"],
                        int(context["seed"]),
                        color,
                        variant,
                        int(config["max_steps"]),
                    )
                    outcomes.append({"seed": context["seed"], **row})
                except Exception as exc:
                    errors.append({
                        "seed": context["seed"],
                        "strategy_color": color,
                        "variant": variant,
                        "error": f"{type(exc).__name__}: {exc}",
                    })

    by_target = defaultdict(list)
    for row in outcomes:
        by_target[row["seed"]].append(row)

    transfers = []
    for seed, rows in by_target.items():
        target = rows[0]["target_color"]
        recovery = [
            row for row in rows
            if row["strategy_color"] == target and row["success"]
        ]
        for color in config["strategy_colors"]:
            if color == target:
                continue
            active = [row for row in rows if row["strategy_color"] == color]
            harmful = [row for row in active if not row["success"]]
            transfers.append({
                "target_seed": seed,
                "target_color": target,
                "source_color": color,
                "active_total": len(active),
                "active_harmful": len(harmful),
                "recovery_alternatives": len(recovery),
                "harmful_transfer": len(harmful) == len(active) and len(recovery) >= 3,
            })

    repeat_checks = []
    for row in outcomes[: int(config["qualification"]["minimum_repeat_checks"])]:
        again = execute(
            config["env_id"],
            int(row["seed"]),
            row["strategy_color"],
            row["variant"],
            int(config["max_steps"]),
        )
        repeat_checks.append({
            "seed": row["seed"],
            "strategy_color": row["strategy_color"],
            "variant": row["variant"],
            "success_match": row["success"] == again["success"],
            "reward_match": row["reward"] == again["reward"],
            "steps_match": row["steps"] == again["steps"],
        })

    q = config["qualification"]
    local_correct = [
        row for row in outcomes
        if row["strategy_color"] == row["target_color"] and row["success"]
    ]
    harmful_transfers = [row for row in transfers if row["harmful_transfer"]]
    targets_with_recovery = {
        seed for seed, rows in by_target.items()
        if sum(row["strategy_color"] == row["target_color"] and row["success"] for row in rows)
        >= int(q["minimum_recovery_alternatives"])
    }
    gates = {
        "execution": len(outcomes) >= int(q["minimum_completed_outcomes"]) and not errors,
        "context_coverage": len(contexts) >= int(q["minimum_contexts"])
        and len({row["target_color"] for row in contexts}) >= int(q["minimum_target_colors"]),
        "local_correctness": len(local_correct) >= int(q["minimum_local_correct_outcomes"]),
        "harmful_transfers": len(harmful_transfers)
        >= int(q["minimum_harmful_family_target_transfers"]),
        "target_harm_coverage": len({row["target_seed"] for row in harmful_transfers})
        >= int(q["minimum_targets_with_harm"]),
        "recovery": len(targets_with_recovery) >= int(q["minimum_targets_with_recovery"]),
        "source_diversity": len({row["source_color"] for row in harmful_transfers})
        >= int(q["minimum_harmful_source_colors"]),
        "determinism": len(repeat_checks) >= int(q["minimum_repeat_checks"])
        and all(row["success_match"] and row["reward_match"] and row["steps_match"] for row in repeat_checks),
    }
    decision = "GO" if all(gates.values()) else "NO_GO"
    report = {
        "protocol": config["protocol"],
        "phase": config["phase"],
        "uses_sc_dcta": False,
        "uses_baselines": False,
        "decision": decision,
        "elapsed_s": time.perf_counter() - started,
        "counts": {
            "contexts": len(contexts),
            "target_colors": len({row["target_color"] for row in contexts}),
            "outcomes": len(outcomes),
            "errors": len(errors),
            "local_correct_outcomes": len(local_correct),
            "family_target_transfers": len(transfers),
            "harmful_family_target_transfers": len(harmful_transfers),
            "targets_with_harm": len({row["target_seed"] for row in harmful_transfers}),
            "targets_with_recovery": len(targets_with_recovery),
            "harmful_source_colors": len({row["source_color"] for row in harmful_transfers}),
        },
        "gates": gates,
        "contexts": contexts,
        "target_color_counts": dict(Counter(row["target_color"] for row in contexts)),
        "transfers": transfers,
        "repeat_checks": repeat_checks,
        "errors": errors,
        "outcomes": outcomes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": decision,
        "elapsed_s": report["elapsed_s"],
        "counts": report["counts"],
        "gates": gates,
        "target_color_counts": report["target_color_counts"],
    }, indent=2))


if __name__ == "__main__":
    main()
