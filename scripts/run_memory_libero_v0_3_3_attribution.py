"""Post-hoc attribution diagnostic; not part of the v0.3.3 frozen gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

import _bootstrap

from mcx.memory_libero_v03 import (
    branch_belief, build_archive, fit_evidence, is_strict_record,
    logit_similarity, mask_edges, similarity,
)
from mcx.scacd_up import run_belief_policy


def normal_logpdf(value, mean, variance):
    import math
    return -0.5 * (math.log(2 * math.pi * variance) + (value - mean) ** 2 / variance)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generation = json.loads(args.generation.read_text(encoding="utf-8"))
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    archives = [build_archive(record) for record in generation["archives"] if is_strict_record(record)]
    development = [archive for archive in archives if archive.split == "development"]
    heldout = [archive for archive in archives if archive.split == "heldout"]
    evidence = fit_evidence(development)
    scacd_rows = {
        (row["archive_id"], row["mask_index"]): row
        for row in evaluation["rows"]
        if row["split"] == "heldout" and row["condition"] == "deleted_spurious"
        and row["budget"] == 3 and row["method"] == "scacd_up_continuous"
    }
    rows = []
    for archive in heldout:
        for mask_index in range(10):
            edges = mask_edges(archive, "deleted_spurious", mask_index)
            belief = branch_belief(archive, edges, evidence, 0.5, 0.5)
            branch_run = run_belief_policy(belief, 0, 3, horizon=1)
            candidates = [node for branch in archive.branch_ids for node in branch]
            likelihood_ranking = sorted(
                candidates,
                key=lambda node: -(
                    normal_logpdf(
                        logit_similarity(similarity(archive, node)),
                        evidence.affected_mean, evidence.affected_variance,
                    )
                    - normal_logpdf(
                        logit_similarity(similarity(archive, node)),
                        evidence.clean_mean, evidence.clean_variance,
                    )
                ),
            )[:3]
            scacd = scacd_rows[(archive.archive_id, mask_index)]
            rows.append({
                "archive_id": archive.archive_id, "mask_index": mask_index,
                "content_likelihood_recall": len(set(likelihood_ranking) & archive.affected_ids) / 3,
                "content_branch_recall": branch_run.discoveries / 3,
                "scacd_recall": scacd["recall"],
                "content_branch_same_sequence_as_scacd": (
                    list(branch_run.replayed_ids) == scacd["replayed_ids"]
                ),
            })
    payload = {
        "protocol": "memory-libero/hard-evidence-heldout-v0.3.3/posthoc-attribution-v0.1",
        "complete": True,
        "status": "post-hoc-attribution-diagnostic",
        "units": len(rows),
        "mean_recall": {
            "individual_content_likelihood": statistics.fmean(row["content_likelihood_recall"] for row in rows),
            "content_only_branch_posterior": statistics.fmean(row["content_branch_recall"] for row in rows),
            "scacd_up_continuous": statistics.fmean(row["scacd_recall"] for row in rows),
        },
        "content_branch_same_sequence_as_scacd_count": sum(
            row["content_branch_same_sequence_as_scacd"] for row in rows
        ),
        "rows": rows,
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in (
        "status", "units", "mean_recall", "content_branch_same_sequence_as_scacd_count"
    )}, indent=2))


if __name__ == "__main__":
    main()
