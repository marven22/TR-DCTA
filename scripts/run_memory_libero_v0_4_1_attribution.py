"""Post-hoc mechanism attribution for the frozen v0.4.1 result."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.memory_libero_v041 import BUDGETS, MOTIFS, PROTOCOL, build_archive


def bootstrap(rows, left, right, draws=10000):
    archives = sorted({r["archive_id"] for r in rows})
    values = {(r["archive_id"], r["method"]): r["recall"] for r in rows}
    rng = random.Random(411); samples = []
    for _ in range(draws):
        chosen = [rng.choice(archives) for _ in archives]
        samples.append(statistics.fmean(values[a, left]-values[a, right] for a in chosen))
    samples.sort()
    return {"mean": statistics.fmean(samples), "lower_95": samples[int(.025*draws)],
            "upper_95": samples[int(.975*draws)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    if evaluation.get("protocol") != PROTOCOL or not evaluation.get("complete"):
        raise ValueError("complete v0.4.1 evaluation required")
    primary = [r for r in evaluation["rows"] if r["split"] == "heldout"
               and r["budget"] == 4 and r["affected_count"] > 0]
    archives = [build_archive(r) for r in generation["archives"] if r["split"] == "heldout"]
    comparisons = {
        "adaptive_probability_minus_static": bootstrap(
            primary, "acis_probability", "static_source_probability"),
        "acis_risk_minus_static": bootstrap(
            primary, "acis_risk", "static_source_probability"),
        "acis_risk_minus_adaptive_probability": bootstrap(
            primary, "acis_risk", "acis_probability"),
        "delta_minus_positive_frontier": bootstrap(
            primary, "delta_frontier", "positive_frontier"),
    }
    sequences = {}
    for left, right in (("delta_frontier", "positive_frontier"),
                        ("acis_risk", "acis_probability")):
        same = 0
        for archive in archives:
            l = next(r["replayed_ids"] for r in primary
                     if r["archive_id"] == archive.archive_id and r["method"] == left)
            rr = next(r["replayed_ids"] for r in primary
                      if r["archive_id"] == archive.archive_id and r["method"] == right)
            same += l == rr
        sequences[f"{left}_vs_{right}"] = {"identical": same, "units": len(archives)}
    payload = {
        "protocol": PROTOCOL + "/posthoc-attribution-v0.1",
        "diagnostic_not_preregistered": True, "complete": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "bootstrap_comparisons": comparisons,
        "identical_replay_sequences": sequences,
        "heldout_archive_effects": [
            {"archive_id": a.archive_id, "affected": len(a.affected_ids),
             "deep_affected": len(a.affected_ids-a.direct_gateways)} for a in archives
        ],
        "heldout_extension_effects": {
            motif: sum(a.candidate_ids[-6+index] in a.affected_ids for a in archives)
            for index, motif in enumerate(MOTIFS)
        },
        "budget_curves": {
            str(budget): {
                method: evaluation["summary"]["heldout"][str(budget)][method]["macro_recall_positive_archives"]
                for method in ("static_source_probability", "acis_probability", "acis_risk",
                               "positive_frontier", "delta_frontier")
            } for budget in BUDGETS
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

