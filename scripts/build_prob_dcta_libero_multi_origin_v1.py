"""Build separated public/private multi-origin LIBERO ledgers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.prob_dcta_libero import build_composite_ledgers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    args = parser.parse_args()
    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    evaluator_sha256 = hashlib.sha256(args.evaluator.read_bytes()).hexdigest()
    implementation_paths = {
        "prob_dcta_benchmark": Path("src/mcx/prob_dcta_benchmark.py"),
        "prob_dcta_libero": Path("src/mcx/prob_dcta_libero.py"),
        "active_search_baselines": Path("src/mcx/active_search_baselines.py"),
        "directional_transition": Path("src/mcx/directional_transition.py"),
    }
    implementation_sha256 = {
        key: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in implementation_paths.items()
    }
    public, private = build_composite_ledgers(
        generation, evaluator_sha256, implementation_sha256
    )
    args.public.parent.mkdir(parents=True, exist_ok=True)
    args.private.parent.mkdir(parents=True, exist_ok=True)
    args.public.write_text(json.dumps(public, indent=2) + "\n", encoding="utf-8")
    args.private.write_text(json.dumps(private, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": True,
        "base_archive_count": public["base_archive_count"],
        "composite_archive_count": public["archive_count"],
        "evaluator_sha256_before_label_join": evaluator_sha256,
        "implementation_sha256_before_label_join": implementation_sha256,
        "public_sha256": hashlib.sha256(args.public.read_bytes()).hexdigest(),
        "private_sha256": hashlib.sha256(args.private.read_bytes()).hexdigest(),
    }, indent=2))


if __name__ == "__main__":
    main()
