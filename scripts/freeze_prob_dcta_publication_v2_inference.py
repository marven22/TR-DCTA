"""Hash-freeze the final v2 inference stack before any test generation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


IMPLEMENTATIONS = {
    "evaluator": Path("scripts/evaluate_prob_dcta_publication_v2.py"),
    "posterior": Path("src/mcx/publication_v2_posterior.py"),
    "source_prior": Path("src/mcx/publication_v2_source.py"),
    "latent_acquisition": Path("src/mcx/prob_dcta_benchmark.py"),
    "acis_adapter": Path("src/mcx/prob_dcta_libero_baselines.py"),
    "ens": Path("src/mcx/active_search_baselines.py"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--particle-validation", type=Path, required=True)
    parser.add_argument("--performance-validation", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--cascade-config", type=Path, required=True)
    parser.add_argument("--acis-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    particle = json.loads(args.particle_validation.read_text(encoding="utf-8"))
    validation = json.loads(args.performance_validation.read_text(encoding="utf-8"))
    if not particle.get("passed") or validation.get("expected_split") != "validation":
        raise ValueError("passing label-blind particle and completed validation results required")
    pooled = validation["primary_summary"]["pooled"]
    comparison = validation["comparisons"]["pooled"]
    checks = {
        "prob_beats_top1": pooled["prob_dcta"]["macro_recall"] > pooled["top1_dcta"]["macro_recall"],
        "prob_top1_ci_excludes_zero": comparison["prob_minus_top1"]["lower_95"] > 0,
        "prob_beats_acis": pooled["prob_dcta"]["macro_recall"] > pooled["acis_risk"]["macro_recall"],
        "prob_within_003_of_ens": pooled["prob_dcta"]["macro_recall"] >= pooled["ens"]["macro_recall"] - .03,
        "particle_validation_passed": True,
    }
    if not all(checks.values()):
        raise ValueError(f"validation freeze gate failed: {checks}")
    payload = {
        **candidate,
        "protocol": "memory-corruption/multi-origin-publication-v2/inference-final-freeze",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_method": "prob_dcta", "validation_checks": checks,
        "validation_primary_summary": pooled,
        "validation_comparisons": comparison,
        "particle_validation_summary": particle["summary"],
        "artifact_hashes": {
            **{name: sha256(path) for name, path in IMPLEMENTATIONS.items()},
            "source_config": sha256(args.source_config),
            "cascade_config": sha256(args.cascade_config),
            "acis_config": sha256(args.acis_config),
            "candidate_config": sha256(args.candidate),
            "particle_validation": sha256(args.particle_validation),
            "performance_validation": sha256(args.performance_validation),
        },
        "test_labels_seen": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
