"""Frozen native/donor procedure screen for the DDXPlus extension.

This is the DDXPlus analogue of the Meta-World screen.  It selects one
eligible patient case per pathology, where eligible means the procedure
anchored on the true pathology diagnoses the record correctly and every
confusable donor procedure drawn from the record's own differential fails.

The emitted ledger has the field names the production-population builder
expects, so DDXPlus tasks join the existing split and archive machinery.
No dataset bytes are written into the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from mcx.ddxplus import (
    PROTOCOL, chief_complaint, condition_language, evidence_specificity,
    iter_patients, load_conditions, load_evidences,
    patient_presentation, policy_id, presentation_mentions_pathology, screen_case,
    stable_digest, validate_screen_config, validate_sources,
)


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "src" / "mcx" / "ddxplus.py"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def collect_candidates(
    patients_path: Path, scan_limit: int, per_pathology: int,
) -> dict[str, list]:
    """Stream the release once and retain a bounded candidate pool per pathology."""
    pools: dict[str, list] = defaultdict(list)
    for patient in iter_patients(patients_path, limit=scan_limit):
        pool = pools[patient.pathology]
        if len(pool) < per_pathology:
            pool.append(patient)
    return dict(pools)


def main() -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=None,
                        help="override the config's relative dataset directory")
    parser.add_argument("--scan-limit", type=int, default=None,
                        help="override candidate_scan_limit for a smoke run")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_screen_config(config)
    base = args.data_root if args.data_root is not None else ROOT
    paths = {name: (base / Path(value).name if args.data_root is not None
                    else ROOT / value)
             for name, value in config["paths"].items()}
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(
                f"missing DDXPlus release file '{name}' at {path.as_posix()}; "
                "see docs/DATASETS.md for the download instructions")

    evidences = load_evidences(paths["evidences"])
    conditions = load_conditions(paths["conditions"])
    counts = validate_sources(evidences, conditions)

    scan_limit = int(args.scan_limit if args.scan_limit is not None
                     else config["candidate_scan_limit"])
    pools = collect_candidates(
        paths["patients"], scan_limit, int(config["max_candidates_per_pathology"]))

    specificity = evidence_specificity(conditions)
    donor_count = int(config["donor_count"])
    penalty = float(config["contradiction_penalty"])
    minimum = int(config["minimum_evidences"])
    quota = int(config["cases_per_pathology"])

    eligible_targets: list[dict[str, Any]] = []
    per_pathology: list[dict[str, Any]] = []
    for pathology in sorted(pools):
        # Hash ordering makes the accepted case independent of file order.
        candidates = sorted(
            pools[pathology],
            key=lambda patient: (stable_digest("candidate", patient.case_id),
                                 patient.case_id))
        accepted, attempts, reasons = [], 0, defaultdict(int)
        for patient in candidates:
            if len(accepted) >= quota:
                break
            attempts += 1
            verdict = screen_case(
                patient, conditions, evidences, donor_count=donor_count,
                contradiction_penalty=penalty, minimum_evidences=minimum)
            if not verdict["eligible"]:
                reasons[verdict["reason"]] += 1
                continue
            presentation = patient_presentation(
                patient, evidences, specificity=specificity,
                top=int(config["presentation_findings"]))
            accepted.append(patient)
            eligible_targets.append({
                "self_referential_presentation": presentation_mentions_pathology(
                    presentation, pathology),
                "task_id": f"ddxplus/{pathology}",
                "benchmark": "ddxplus",
                "stratum": f"severity-{verdict['severity']}",
                "target_name": pathology,
                "target_language": presentation,
                "chief_complaint": chief_complaint(patient, evidences),
                "case_id": patient.case_id,
                "native_policy": policy_id(pathology),
                "native_language": condition_language(pathology, conditions, evidences),
                "native_language_alt": condition_language(
                    pathology, conditions, evidences, skip=2),
                "donors": verdict["donors"],
                "simulator_evidence": {
                    "native_success": bool(verdict["native_success"]),
                    "donor_success": [bool(value) for value in verdict["donor_success"]],
                },
                "evidence_count": verdict["evidence_count"],
                "differential_length": verdict["differential_length"],
                "severity": verdict["severity"],
            })
        per_pathology.append({
            "pathology": pathology, "candidates": len(candidates),
            "screened": attempts, "accepted": len(accepted),
            "rejection_reasons": dict(reasons),
        })

    short = [row["pathology"] for row in per_pathology if row["accepted"] < quota]
    minimum = int(config["minimum_eligible_pathologies"])
    eligible_pathologies = len(per_pathology) - len(short)
    gate = {
        "passed": eligible_pathologies >= minimum,
        "eligible_pathologies": eligible_pathologies,
        "minimum_eligible_pathologies": minimum,
        "required_cases_per_pathology": quota,
        "pathologies_screened": len(per_pathology),
        "pathologies_short": short,
        "eligible_target_count": len(eligible_targets),
        "self_referential_presentations": sum(
            bool(target["self_referential_presentation"])
            for target in eligible_targets),
    }
    payload = {
        "protocol": f"{PROTOCOL}/ddxplus-screen",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": args.config.as_posix(),
        "config_payload": config,
        "fingerprint": {
            "adapter_sha256": digest(ADAPTER),
            "runner_sha256": digest(Path(__file__)),
            "config_sha256": digest(args.config),
            **{f"{name}_sha256": digest(path) for name, path in paths.items()},
            "release_counts": counts,
            "scan_limit": scan_limit,
        },
        "complete": True,
        "feasibility_gate": gate,
        "per_pathology": per_pathology,
        "eligible_targets": eligible_targets,
        "elapsed_s": time.perf_counter() - started,
    }
    checkpoint(args.output, payload)
    print(json.dumps({"gate": gate, "release_counts": counts,
                      "elapsed_s": payload["elapsed_s"]}, indent=2))
    return 0 if gate["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
