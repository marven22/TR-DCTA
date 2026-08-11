"""Tune Graph Active Search only on the frozen 12-archive development set."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

import _bootstrap

from mcx.active_search_baselines import GraphActiveSearch, GraphActiveSearchParameters
from mcx.memory_libero_v041 import PROTOCOL, build_archive, is_strict_record


FREEZE_PROTOCOL = "active-search-baselines-v1/development-freeze"
ALPHAS = (0.0, 0.1, 0.01, 0.001, 0.0001)
PRIMARY_BUDGET = 4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--ens-reference", type=Path, required=True)
    parser.add_argument("--graph-paper", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.generation.read_text(encoding="utf-8"))
    if source.get("protocol") != PROTOCOL or not source.get("complete"):
        raise ValueError("complete v0.4.1 generation ledger required")
    archives = [build_archive(record) for record in source["archives"]
                if record["split"] == "development" and is_strict_record(record)]
    if len(archives) != 12:
        raise ValueError("exactly 12 frozen development archives required")
    prior = sum(len(a.affected_ids) for a in archives) / sum(
        len(a.candidate_ids) for a in archives
    )
    results = {}
    for alpha in ALPHAS:
        recalls, discoveries = [], []
        for archive in archives:
            model = GraphActiveSearch(
                tuple(sorted(archive.memories, key=archive.created_at.get)),
                archive.true_edges,
                {archive.source_id: 1},
                GraphActiveSearchParameters(
                    eta=0.5,
                    prior_strength=None,
                    prior_probability=prior,
                    alpha=alpha,
                ),
            )
            replayed = model.run(
                archive.candidate_ids, archive.affected_ids, PRIMARY_BUDGET
            )
            found = len(set(replayed) & archive.affected_ids)
            if archive.affected_ids:
                recalls.append(found / len(archive.affected_ids))
            discoveries.append(found)
        results[str(alpha)] = {
            "macro_recall": statistics.fmean(recalls),
            "mean_discoveries": statistics.fmean(discoveries),
        }
    selected = min(
        ALPHAS,
        key=lambda alpha: (
            -results[str(alpha)]["macro_recall"],
            -results[str(alpha)]["mean_discoveries"],
            alpha,
        ),
    )
    payload = {
        "protocol": FREEZE_PROTOCOL,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_budget": PRIMARY_BUDGET,
        "ens": {
            "posterior": "frozen DCTA finite-world posterior",
            "outcome_integration": "exact",
            "author_repository": "https://github.com/shalijiang/efficient_nonmyopic_active_search",
            "author_repository_commit": "6ac08c088dd903ef8a39381380f533889537b9ba",
        },
        "graph_active_search": {
            "eta": 0.5,
            "prior_strength": "1 / archive node count",
            "prior_probability": prior,
            "alpha_grid": list(ALPHAS),
            "development_results": results,
            "selected_alpha": selected,
            "tie_break": "highest macro recall, highest mean discoveries, then smallest alpha",
            "paper": "https://www.cse.wustl.edu/~garnett/files/papers/wang_et_al_kdd_2013.pdf",
        },
        "training": {
            "archive_count": len(archives),
            "archive_ids": sorted(a.archive_id for a in archives),
            "generation_sha256": sha256(args.generation),
        },
        "implementation": {
            "sha256": sha256(args.implementation),
            "ens_reference_sha256": sha256(args.ens_reference),
            "graph_paper_sha256": sha256(args.graph_paper),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
