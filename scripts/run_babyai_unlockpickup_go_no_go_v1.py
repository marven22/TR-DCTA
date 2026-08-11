"""Run the frozen BabyAI UnlockPickup structural go/no-go audit."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from minigrid.utils.baby_ai_bot import BabyAIBot


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "babyai_unlockpickup_go_no_go_freeze_v1.json"
OUTPUT = ROOT / "reports" / "babyai_unlockpickup_go_no_go_v1.json"


def make_env(env_id: str):
    import gymnasium as gym
    import minigrid  # noqa: F401
    return gym.make(env_id, render_mode=None)


def target_color(mission: str) -> str:
    match = re.fullmatch(r"pick up the (\w+) box", mission)
    if not match:
        raise ValueError(f"unsupported UnlockPickup mission: {mission}")
    return match.group(1)


def object_profile(env) -> dict[str, Any]:
    objects = []
    for x in range(env.width):
        for y in range(env.height):
            obj = env.grid.get(x, y)
            if obj is not None and obj.type not in {"wall", "floor"}:
                objects.append(obj)
    doors = [obj for obj in objects if obj.type == "door"]
    if len(doors) != 1:
        raise RuntimeError(f"expected one required door, found {len(doors)}")
    target_objects = list(env.instrs.desc.obj_set)
    if len(target_objects) != 1:
        raise RuntimeError(f"expected one target box, found {len(target_objects)}")
    required_door = doors[0]
    matching_keys = [obj for obj in objects
                     if obj.type == "key" and obj.color == required_door.color]
    if not matching_keys:
        raise RuntimeError("required door has no matching key")
    distractor_count = len(objects) - 3
    return {
        "object_count": len(objects),
        "distractor_count": distractor_count,
        "required_door_color": required_door.color,
        "target_box_color": target_objects[0].color,
        "object_type_counts": dict(Counter(obj.type for obj in objects)),
    }


def execute(
    env_id: str, seed: int, source_color: str, variant: str,
) -> dict[str, Any]:
    env = make_env(env_id)
    observation, _ = env.reset(seed=int(seed))
    unwrapped = env.unwrapped
    unwrapped.instrs.reset_verifier(unwrapped)
    mission = str(observation["mission"])
    target = target_color(mission)
    profile = object_profile(unwrapped)
    target_box = unwrapped.instrs.desc.obj_set[0]
    required_door = next(
        unwrapped.grid.get(x, y)
        for x in range(unwrapped.width) for y in range(unwrapped.height)
        if (unwrapped.grid.get(x, y) is not None
            and unwrapped.grid.get(x, y).type == "door")
    )
    bot = BabyAIBot(env)
    action_taken = None
    action_trace: list[int] = []
    milestones = {
        "required_key_acquired": False,
        "required_door_opened": False,
        "target_room_entered": False,
        "target_box_reached": False,
    }
    reward = 0.0
    terminated = False
    truncated = False
    stop_reason = "max_steps"
    mismatch = source_color != target
    variants = {"early_bind", "post_unlock_bind", "terminal_bind"}
    if variant not in variants:
        raise ValueError(f"unknown descendant variant: {variant}")

    for _ in range(int(unwrapped.max_steps)):
        action = bot.replan(action_taken)
        carrying = unwrapped.carrying
        if carrying is not None and carrying.type == "key" \
                and carrying.color == required_door.color:
            milestones["required_key_acquired"] = True
        if required_door.is_open:
            milestones["required_door_opened"] = True
        if int(unwrapped.agent_pos[0]) > 5:
            milestones["target_room_entered"] = True
        forward = unwrapped.grid.get(*(unwrapped.agent_pos + unwrapped.dir_vec))
        target_pickup = int(action) == int(unwrapped.actions.pickup) and forward is target_box
        if target_pickup:
            milestones["target_box_reached"] = True

        abort = mismatch and (
            (variant == "early_bind" and milestones["required_key_acquired"])
            or (variant == "post_unlock_bind" and milestones["required_door_opened"])
            or (variant == "terminal_bind" and milestones["target_box_reached"])
        )
        if abort:
            stop_reason = "source_guard_abort"
            break

        _, reward, terminated, truncated, _ = env.step(action)
        action_trace.append(int(action))
        action_taken = action
        carrying = unwrapped.carrying
        if carrying is not None and carrying.type == "key" \
                and carrying.color == required_door.color:
            milestones["required_key_acquired"] = True
        milestones["required_door_opened"] |= bool(required_door.is_open)
        milestones["target_room_entered"] |= int(unwrapped.agent_pos[0]) > 5
        if terminated or truncated:
            stop_reason = "success" if terminated and reward > 0.0 else (
                "terminated" if terminated else "truncated")
            break

    success = bool(terminated and reward > 0.0)
    result = {
        "seed": int(seed), "mission": mission, "target_color": target,
        "source_color": source_color, "variant": variant,
        "mismatch": mismatch, "success": success, "reward": float(reward),
        "steps": len(action_trace), "stop_reason": stop_reason,
        "milestones": milestones, "actions": action_trace,
        "object_profile": profile,
    }
    env.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    colors = tuple(config["source_colors"])
    variants = tuple(config["descendant_variants"])
    start = int(config["context_seeds"]["start"])
    count = int(config["context_seeds"]["count"])
    started = time.perf_counter()
    outcomes = []
    errors = []
    contexts = []

    for index, seed in enumerate(range(start, start + count), start=1):
        for source in colors:
            for variant in variants:
                try:
                    outcomes.append(execute(config["env_id"], seed, source, variant))
                except Exception as exc:  # pragma: no cover - preserved as audit evidence
                    errors.append({
                        "seed": seed, "source_color": source, "variant": variant,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
        target_rows = [row for row in outcomes if row["seed"] == seed]
        if target_rows:
            contexts.append({
                "seed": seed, "mission": target_rows[0]["mission"],
                "target_color": target_rows[0]["target_color"],
                "object_profile": target_rows[0]["object_profile"],
            })
        if index % 10 == 0:
            print(f"[contexts] {index}/{count}", flush=True)

    by_seed_source: dict[tuple[int, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in outcomes:
        by_seed_source[(row["seed"], row["source_color"])][row["variant"]] = row
    strict_order = []
    for (seed, source), rows in sorted(by_seed_source.items()):
        target = rows[variants[0]]["target_color"]
        if source == target or len(rows) != 3:
            continue
        strict_order.append({
            "seed": seed, "source_color": source,
            "early_steps": rows["early_bind"]["steps"],
            "post_unlock_steps": rows["post_unlock_bind"]["steps"],
            "terminal_steps": rows["terminal_bind"]["steps"],
            "strict": rows["early_bind"]["steps"]
            < rows["post_unlock_bind"]["steps"] < rows["terminal_bind"]["steps"],
        })

    matching = [row for row in outcomes if not row["mismatch"]]
    harmful = [row for row in outcomes if row["mismatch"] and not row["success"]]
    early = [row for row in harmful if row["variant"] == "early_bind"
             and row["milestones"]["required_key_acquired"]]
    middle = [row for row in harmful if row["variant"] == "post_unlock_bind"
              and row["milestones"]["required_door_opened"]]
    late = [row for row in harmful if row["variant"] == "terminal_bind"
            and row["milestones"]["target_box_reached"]]
    recovery_targets = {
        context["seed"] for context in contexts
        if sum(row["seed"] == context["seed"] and not row["mismatch"] and row["success"]
               for row in outcomes) >= 3
    }
    donors = {}
    for color in colors:
        donors[color] = min(row["seed"] for row in matching
                            if row["target_color"] == color and row["success"])
    donor_checks = [
        row for row in matching if row["seed"] == donors[row["target_color"]]
    ]

    repeat_checks = []
    for row in outcomes[: int(config["repeat_checks"])]:
        again = execute(config["env_id"], row["seed"], row["source_color"], row["variant"])
        repeat_checks.append({
            "seed": row["seed"], "source_color": row["source_color"],
            "variant": row["variant"],
            "success_match": row["success"] == again["success"],
            "stop_reason_match": row["stop_reason"] == again["stop_reason"],
            "steps_match": row["steps"] == again["steps"],
            "milestones_match": row["milestones"] == again["milestones"],
            "actions_match": row["actions"] == again["actions"],
        })

    q = config["qualification"]
    gates = {
        "execution": len(outcomes) == int(q["transfer_outcomes"]) and not errors,
        "context_and_color_coverage": len(contexts) == int(q["contexts"])
        and len({row["target_color"] for row in contexts}) == int(q["target_colors"]),
        "distractor_coverage": all(
            row["object_profile"]["distractor_count"] >= int(config["minimum_distractors"])
            for row in contexts),
        "matching_local_correctness": len(matching) == int(q["matching_local_successes"])
        and all(row["success"] for row in matching),
        "mismatched_selective_harm": len(harmful) == int(q["mismatched_harmful_transfers"])
        and all(row["stop_reason"] == "source_guard_abort" for row in harmful),
        "early_key_progress": len(early) == int(q["early_key_progress"]),
        "post_unlock_progress": len(middle) == int(q["post_unlock_progress"]),
        "terminal_target_progress": len(late) == int(q["terminal_target_reached"]),
        "strict_stage_order": len(strict_order) == int(q["strict_stage_order_pairs"])
        and all(row["strict"] for row in strict_order),
        "recoverability": len(recovery_targets)
        == int(q["targets_with_three_recovery_alternatives"]),
        "source_diversity": len({row["source_color"] for row in harmful})
        == int(q["harmful_source_colors"]),
        "donor_correctness": len(donor_checks) == len(colors) * len(variants)
        and all(row["success"] for row in donor_checks),
        "determinism": len(repeat_checks) == int(q["repeat_checks"])
        and all(all(value for key, value in row.items() if key.endswith("_match"))
                for row in repeat_checks),
    }
    decision = "GO" if all(gates.values()) else "NO_GO"
    report = {
        "schema_version": "babyai-unlockpickup-go-no-go-v1",
        "protocol": config["protocol"], "phase": config["phase"],
        "uses_sc_dcta": False, "uses_baselines": False,
        "decision": decision, "gates": gates,
        "counts": {
            "contexts": len(contexts), "target_colors": len({r["target_color"] for r in contexts}),
            "transfer_outcomes": len(outcomes), "execution_errors": len(errors),
            "matching_local_successes": sum(row["success"] for row in matching),
            "mismatched_harmful_transfers": len(harmful),
            "early_key_progress": len(early), "post_unlock_progress": len(middle),
            "terminal_target_reached": len(late),
            "strict_stage_order_pairs": sum(row["strict"] for row in strict_order),
            "targets_with_recovery": len(recovery_targets),
            "donor_checks": len(donor_checks), "repeat_checks": len(repeat_checks),
        },
        "target_color_counts": dict(Counter(row["target_color"] for row in contexts)),
        "harmful_source_counts": dict(Counter(row["source_color"] for row in harmful)),
        "mean_stop_steps_by_variant": {
            variant: sum(row["steps"] for row in harmful if row["variant"] == variant)
            / sum(row["variant"] == variant for row in harmful)
            for variant in variants
        },
        "donor_seeds": donors, "contexts": contexts, "donor_checks": donor_checks,
        "strict_order_checks": strict_order, "repeat_checks": repeat_checks,
        "errors": errors, "outcomes": outcomes,
        "elapsed_s": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": decision, "counts": report["counts"], "gates": gates,
        "target_color_counts": report["target_color_counts"],
        "harmful_source_counts": report["harmful_source_counts"],
        "mean_stop_steps_by_variant": report["mean_stop_steps_by_variant"],
        "elapsed_s": report["elapsed_s"],
    }, indent=2))
    return 0 if decision == "GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
