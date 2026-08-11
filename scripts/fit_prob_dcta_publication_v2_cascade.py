"""Fit the latent-contamination and harmful-emission models on development."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _bootstrap

from mcx.publication_v2 import PROTOCOL
from mcx.publication_v2_posterior import fit_cascade_parameters


def estimator_json(value):
    return {"means": list(value.means), "scales": list(value.scales),
            "coefficients": list(value.coefficients)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = json.loads(args.public.read_text(encoding="utf-8"))
    private = json.loads(args.private.read_text(encoding="utf-8"))
    if public.get("protocol") != f"{PROTOCOL}/public" or private.get("protocol") != f"{PROTOCOL}/private":
        raise ValueError("publication-v2 ledgers required")
    rows = [row for row in public["archives"] if row["provenance_missing_rate"] == 0.0]
    if any(row["split"] != "development" for row in rows):
        raise ValueError("cascade model can only fit development archives")
    labels = {row["archive_id"]: row for row in private["archives"]}
    parameters, counts = fit_cascade_parameters(rows, labels, l2=1.0)
    payload = {
        "protocol": f"{PROTOCOL}/cascade-development-fit",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "l2": 1.0,
        "contamination_features": ["root", "merge", "parent_similarity", "extra_parents", "target_similarity"],
        "emission_features": ["target_similarity", "source_similarity", "parent_similarity", "depth", "merge", "citation_count"],
        "contamination": estimator_json(parameters.contamination),
        "emission": estimator_json(parameters.emission),
        "latent_edge_probability": parameters.latent_edge_probability,
        "training_counts": counts,
        "source_hashes": {"public": hashlib.sha256(args.public.read_bytes()).hexdigest(),
                          "private": hashlib.sha256(args.private.read_bytes()).hexdigest()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
