"""Fit and freeze the Meta-World-adapted validation candidate on development."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.publication_v2_posterior import fit_cascade_parameters
from mcx.publication_v2_source import fit_source_estimator, source_features


PUBLIC = Path("results/prob_dcta_publication_v2_development_public.json")
PRIVATE = Path("results/prob_dcta_publication_v2_development_private.json")
SOURCE_OUTPUT = Path("configs/prob_dcta_metaworld_adapted_source_validation.json")
CASCADE_OUTPUT = Path("configs/prob_dcta_metaworld_adapted_cascade_validation.json")
FREEZE_OUTPUT = Path("configs/prob_dcta_metaworld_adapted_validation_freeze.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def estimator_json(value):
    return {"means": list(value.means), "scales": list(value.scales),
            "coefficients": list(value.coefficients)}


def main():
    public = json.loads(PUBLIC.read_text(encoding="utf-8"))
    private = json.loads(PRIVATE.read_text(encoding="utf-8"))
    labels = {row["archive_id"]: row for row in private["archives"]}
    training = [row for row in public["archives"] if row["benchmark"] == "metaworld"
                and row["split"] == "development"
                and float(row["provenance_missing_rate"]) == 0.0]
    tasks = {row["task_key"] for row in training}
    if len(tasks) != 10 or len(training) != 30:
        raise ValueError("expected 10 tasks and 30 full-graph development rotations")
    source_rows = [
        (source_features(archive, str(source)),
         int(str(source) == str(labels[archive["archive_id"]]["active_source_id"])))
        for archive in training for source in archive["source_ids"]
    ]
    estimator = fit_source_estimator(source_rows, l2=1.0)
    cascade, counts = fit_cascade_parameters(training, labels, l2=1.0)
    created = datetime.now(timezone.utc).isoformat()
    source_payload = {
        "protocol": "memory-corruption/multi-origin-publication-v2/metaworld-adapted-source-validation-freeze",
        "created_at_utc": created, "model": "binary-logit-normalized",
        "features": ["source_target", "direct_target", "reachable_target",
                     "source_reachable", "edge_coherence", "reachable_size"],
        "l2": 1.0, "minimum_source_probability": 0.05,
        **estimator_json(estimator), "training_task_count": len(tasks),
        "training_archive_count": len(training), "training_row_count": len(source_rows),
        "development_only": True,
    }
    cascade_payload = {
        "protocol": "memory-corruption/multi-origin-publication-v2/metaworld-adapted-cascade-validation-freeze",
        "created_at_utc": created, "l2": 1.0,
        "contamination_features": ["root", "merge", "parent_similarity", "extra_parents", "target_similarity"],
        "emission_features": ["target_similarity", "source_similarity", "parent_similarity",
                              "depth", "merge", "citation_count"],
        "contamination": estimator_json(cascade.contamination),
        "emission": estimator_json(cascade.emission),
        "latent_edge_probability": cascade.latent_edge_probability,
        "training_counts": counts, "training_task_count": len(tasks),
        "training_archive_count": len(training), "development_only": True,
    }
    SOURCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_OUTPUT.write_text(json.dumps(source_payload, indent=2) + "\n", encoding="utf-8")
    CASCADE_OUTPUT.write_text(json.dumps(cascade_payload, indent=2) + "\n", encoding="utf-8")
    implementation_paths = {
        "evaluator": Path("scripts/evaluate_prob_dcta_publication_v2.py"),
        "posterior": Path("src/mcx/publication_v2_posterior.py"),
        "source": Path("src/mcx/publication_v2_source.py"),
        "acquisition": Path("src/mcx/prob_dcta_benchmark.py"),
        "ens": Path("src/mcx/active_search_baselines.py"),
        "citation_mask": Path("src/mcx/publication_v2_masking.py"),
        "ledger_builder": Path("scripts/build_prob_dcta_metaworld_mask_consistent_ledgers.py"),
        "inference": Path("configs/prob_dcta_publication_v2_inference_final.json"),
        "acis": Path("configs/acis_risk_calibrator_v1.json"),
        "crossfit_protocol": Path("docs/METAWORLD_CROSSFIT_POSTERIOR_PROTOCOL.md"),
        "source_config": SOURCE_OUTPUT, "cascade_config": CASCADE_OUTPUT,
    }
    freeze = {
        "protocol": "memory-corruption/multi-origin-publication-v2/metaworld-adapted-validation-evaluation-freeze",
        "created_at_utc": created, "development_only_at_freeze": True,
        "validation_task_count": 10, "primary_budget": 4,
        "primary_provenance_missing_rate": 0.25,
        "validation_gates": {
            "adapted_beats_external_source_prob_dcta": True,
            "adapted_within_003_of_same_posterior_ens": True,
            "adapted_retains_085_known_source": True,
            "adapted_improves_source_brier_over_external": True,
        },
        "no_post_freeze_model_changes": True,
        "artifact_hashes": {name: sha256(path) for name, path in implementation_paths.items()},
        "development_hashes": {"public": sha256(PUBLIC), "private": sha256(PRIVATE)},
    }
    FREEZE_OUTPUT.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source_output": str(SOURCE_OUTPUT), "cascade_output": str(CASCADE_OUTPUT),
                      "freeze_output": str(FREEZE_OUTPUT), "training_tasks": len(tasks),
                      "artifact_hashes": freeze["artifact_hashes"]}, indent=2))


if __name__ == "__main__":
    main()
