"""Screen one LIBERO suite for v0.3 donor and same-task clean policies."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from libero.libero import benchmark

from run_memory_libero_transfer_screen import load_demos, make_env, replay


PROTOCOL = "memory-libero/hard-evidence-heldout-v0.3"


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=("libero_object", "libero_goal", "libero_10", "libero_spatial"),
        required=True,
    )
    parser.add_argument("--split", choices=("development", "heldout"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    expected_split = "heldout" if args.suite == "libero_10" else "development"
    if args.split != expected_split:
        raise ValueError("suite/split assignment violates the frozen protocol")

    suite = benchmark.get_benchmark_dict()[args.suite]()
    names = suite.get_task_names()
    demos = {index: load_demos(suite, index, tuple(range(10))) for index in range(10)}
    payload = {
        "protocol": PROTOCOL, "suite": args.suite, "split": args.split,
        "complete": False, "rendering_mode": "physics_only",
        "task_names": names, "task_count": 10, "rows": [],
    }
    if args.resume and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        if payload.get("protocol") != PROTOCOL or payload.get("suite") != args.suite:
            raise ValueError("incompatible checkpoint")
    completed = {row["target_index"] for row in payload["rows"]}

    for target_index, target_name in enumerate(names):
        if target_index in completed:
            print(f"{args.suite} target {target_index + 1}/10 already complete", flush=True)
            continue
        started = time.perf_counter()
        env = make_env(suite, target_index, 32, False)
        env.seed(0)
        transfers = []
        for donor_index, donor_name in enumerate(names):
            for demo_index in (0, 1):
                transfers.append({
                    "donor_index": donor_index, "donor_name": donor_name,
                    "demo_index": demo_index,
                    "action_sha256": demos[donor_index][demo_index]["action_sha256"],
                    **replay(env, demos[target_index][demo_index]["init_state"],
                             demos[donor_index][demo_index]["actions"]),
                })
        clean_native = []
        for demo_index in range(2, 10):
            clean_native.append({
                "demo_index": demo_index,
                "action_sha256": demos[target_index][demo_index]["action_sha256"],
                **replay(env, demos[target_index][demo_index]["init_state"],
                         demos[target_index][demo_index]["actions"]),
            })
        env.close()
        payload["rows"].append({
            "target_index": target_index, "target_name": target_name,
            "target_language": suite.get_task(target_index).language,
            "transfers": transfers, "clean_native": clean_native,
        })
        write(args.output, payload)
        print(f"{args.suite} target {target_index + 1}/10 complete "
              f"({time.perf_counter() - started:.1f}s)", flush=True)

    selected = []
    for row in payload["rows"]:
        target = row["target_index"]
        native = [item for item in row["transfers"] if item["donor_index"] == target]
        clean = [item for item in row["clean_native"] if item["success"]]
        eligible_donors = []
        if len(native) == 2 and all(item["success"] for item in native) and len(clean) >= 3:
            for donor in range(10):
                if donor == target:
                    continue
                donor_rows = [item for item in row["transfers"] if item["donor_index"] == donor]
                if len(donor_rows) == 2 and all(not item["success"] for item in donor_rows):
                    eligible_donors.append((names[donor], donor))
        if eligible_donors:
            donor_name, donor = sorted(eligible_donors)[0]
            selected.append({
                "target_index": target, "target_name": row["target_name"],
                "target_language": row["target_language"],
                "donor_index": donor, "donor_name": donor_name,
                "donor_language": suite.get_task(donor).language,
                "eligible_donor_count": len(eligible_donors),
                "clean_demo_indices": [item["demo_index"] for item in clean[:3]],
            })

    verification = []
    for pair in selected:
        target, donor = pair["target_index"], pair["donor_index"]
        env = make_env(suite, target, 32, False)
        env.seed(0)
        jobs = [("native", target, index, demos[target][index]["init_state"])
                for index in (0, 1)]
        jobs += [("donor", donor, index, demos[target][index]["init_state"])
                 for index in (0, 1)]
        jobs += [("clean", target, index, demos[target][index]["init_state"])
                 for index in pair["clean_demo_indices"]]
        for role, policy_task, demo_index, init_state in jobs:
            outcomes = [replay(env, init_state, demos[policy_task][demo_index]["actions"])
                        for _ in range(2)]
            verification.append({
                "target_index": target, "donor_index": policy_task,
                "role": role, "demo_index": demo_index, "outcomes": outcomes,
                "outcome_deterministic": outcomes[0]["success"] == outcomes[1]["success"],
            })
        env.close()

    payload.update({
        "complete": True, "selected_pairs": selected,
        "selected_pair_count": len(selected), "verification": verification,
        "suite_gate_passed": len(selected) >= 5,
    })
    write(args.output, payload)
    print(json.dumps({
        "suite": args.suite, "selected_pair_count": len(selected),
        "suite_gate_passed": payload["suite_gate_passed"],
        "selected_pairs": selected,
    }, indent=2))


if __name__ == "__main__":
    main()
