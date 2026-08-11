"""Analyze the frozen Meta-World adapted validation run without model changes."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

import _bootstrap

from mcx.publication_v2_oracle import hindsight_selection


ADAPTED = Path("results/prob_dcta_metaworld_adapted_validation_evaluation.json")
EXTERNAL = Path("results/prob_dcta_metaworld_external_source_validation_evaluation.json")
PUBLIC = Path("results/prob_dcta_metaworld_validation_public_mask_consistent.json")
PRIVATE = Path("results/prob_dcta_metaworld_validation_private_mask_consistent.json")
FREEZE = Path("configs/prob_dcta_metaworld_adapted_validation_freeze.json")
OUTPUT = Path("results/prob_dcta_metaworld_adapted_validation_analysis.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def harm_weights(archive):
    candidates = list(map(str, archive["candidate_ids"])); created = archive["created_at"]
    edges = [tuple(map(str, edge)) for edge in archive["observed_formation_edges"]]
    children = {node: [] for node in candidates}
    for left, right in edges:
        if left in children:
            children[left].append(right)
    reach = {}
    for node in candidates:
        found, frontier = set(), list(children[node])
        while frontier:
            child = frontier.pop()
            if child not in found:
                found.add(child); frontier.extend(children.get(child, ()))
        reach[node] = len(found)
    times = [int(created[node]) for node in candidates]; minimum, maximum = min(times), max(times)
    max_reach = max(reach.values()) or 1
    return {node: 1.0 + .25 * (int(created[node]) - minimum) / max(maximum - minimum, 1)
            + .25 * reach[node] / max_reach for node in candidates}


def clustered_difference(left_rows, right_rows, draws, seed):
    left = {}; right = {}
    for row in left_rows:
        left.setdefault(row["task_key"], []).append(row["weighted_recall"])
    for row in right_rows:
        right.setdefault(row["task_key"], []).append(row["weighted_recall"])
    tasks = sorted(set(left) & set(right))
    differences = [statistics.fmean(left[key]) - statistics.fmean(right[key]) for key in tasks]
    rng = random.Random(seed)
    samples = sorted(statistics.fmean(differences[rng.randrange(len(differences))]
                                     for _ in differences) for _ in range(draws))
    return {"estimate": statistics.fmean(differences),
            "lower_95": samples[int(.025 * draws)], "upper_95": samples[int(.975 * draws)],
            "task_count": len(tasks), "wins": sum(value > 0 for value in differences),
            "ties": sum(value == 0 for value in differences),
            "losses": sum(value < 0 for value in differences)}


def select(rows, method, budget=4, mask=.25):
    return [row for row in rows if row["method"] == method and row["budget"] == budget
            and float(row["provenance_missing_rate"]) == mask]


def main():
    adapted = json.loads(ADAPTED.read_text(encoding="utf-8"))
    external = json.loads(EXTERNAL.read_text(encoding="utf-8"))
    public = json.loads(PUBLIC.read_text(encoding="utf-8"))
    private = json.loads(PRIVATE.read_text(encoding="utf-8"))
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if adapted["hashes"]["source_config"] != freeze["artifact_hashes"]["source_config"]:
        raise ValueError("adapted source does not match pre-validation freeze")
    if adapted["hashes"]["cascade_config"] != freeze["artifact_hashes"]["cascade_config"]:
        raise ValueError("adapted cascade does not match pre-validation freeze")
    if adapted["hashes"]["evaluator"] != freeze["artifact_hashes"]["evaluator"]:
        raise ValueError("evaluator does not match pre-validation freeze")
    labels = {row["archive_id"]: row for row in private["archives"]}
    archives = {row["archive_id"]: row for row in public["archives"]}
    primary_archives = [row for row in public["archives"]
                        if float(row["provenance_missing_rate"]) == .25]
    ceiling_rows = []
    for archive in primary_archives:
        affected = frozenset(map(str, labels[archive["archive_id"]]["affected_ids"]))
        weights = harm_weights(archive)
        replayed = hindsight_selection(archive["candidate_ids"], affected, 4, weights)
        hits = set(replayed) & affected
        ceiling_rows.append({"task_key": archive["task_key"],
                             "weighted_recall": sum(weights[node] for node in hits)
                                                / sum(weights[node] for node in affected)})
    ceiling = statistics.fmean(row["weighted_recall"] for row in ceiling_rows)
    adapted_prob = select(adapted["rows"], "prob_dcta")
    external_prob = select(external["rows"], "prob_dcta")
    adapted_ens = select(adapted["rows"], "ens")
    adapted_top1 = select(adapted["rows"], "top1_dcta")
    adapted_known = select(adapted["rows"], "known_source_dcta")
    draws = 10000; seed = 260905
    comparisons = {
        "adapted_prob_minus_external_prob": clustered_difference(adapted_prob, external_prob, draws, seed),
        "adapted_prob_minus_adapted_ens": clustered_difference(adapted_prob, adapted_ens, draws, seed + 1),
        "adapted_prob_minus_adapted_top1": clustered_difference(adapted_prob, adapted_top1, draws, seed + 2),
    }
    scores = {
        "full_information_ceiling": ceiling,
        "adapted_prob_dcta": statistics.fmean(row["weighted_recall"] for row in adapted_prob),
        "external_source_prob_dcta": statistics.fmean(row["weighted_recall"] for row in external_prob),
        "adapted_ens": statistics.fmean(row["weighted_recall"] for row in adapted_ens),
        "adapted_top1_dcta": statistics.fmean(row["weighted_recall"] for row in adapted_top1),
        "adapted_known_source_dcta": statistics.fmean(row["weighted_recall"] for row in adapted_known),
    }
    adapted_initial_brier = statistics.fmean(row["initial_source_brier"] for row in adapted["rows"]
                                             if row["budget"] == 4 and row["method"] == "prob_dcta"
                                             and float(row["provenance_missing_rate"]) == .25)
    external_initial_brier = statistics.fmean(row["initial_source_brier"] for row in external["rows"]
                                              if row["budget"] == 4 and row["method"] == "prob_dcta"
                                              and float(row["provenance_missing_rate"]) == .25)
    source_top1 = []
    for diagnostic in adapted["diagnostics"]:
        archive = archives[diagnostic["archive_id"]]
        if float(archive["provenance_missing_rate"]) != .25:
            continue
        prior = diagnostic["source_prior"]
        predicted = min(prior, key=lambda source: (-prior[source], source))
        source_top1.append(int(predicted == labels[archive["archive_id"]]["active_source_id"]))
    gates = {
        "adapted_beats_external_source_prob_dcta": scores["adapted_prob_dcta"] > scores["external_source_prob_dcta"],
        "adapted_within_003_of_same_posterior_ens": scores["adapted_prob_dcta"] >= scores["adapted_ens"] - .03,
        "adapted_retains_085_known_source": scores["adapted_prob_dcta"] >= .85 * scores["adapted_known_source_dcta"],
        "adapted_improves_source_brier_over_external": adapted_initial_brier < external_initial_brier,
    }
    sensitivity = {}
    for budget in (2, 4, 8):
        for mask in (0.0, .25, .5):
            key = f"budget_{budget}_mask_{mask:.2f}"
            ap = select(adapted["rows"], "prob_dcta", budget, mask)
            ep = select(external["rows"], "prob_dcta", budget, mask)
            ae = select(adapted["rows"], "ens", budget, mask)
            sensitivity[key] = {
                "adapted_prob_dcta": statistics.fmean(row["weighted_recall"] for row in ap),
                "external_prob_dcta": statistics.fmean(row["weighted_recall"] for row in ep),
                "adapted_ens": statistics.fmean(row["weighted_recall"] for row in ae),
            }
    payload = {
        "protocol": "memory-corruption/multi-origin-publication-v2/metaworld-adapted-validation-analysis-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "validation_gate_passed": all(gates.values()), "validation_gates": gates,
        "task_count": 10, "archive_count": 90, "primary_scores": scores,
        "primary_comparisons": comparisons,
        "known_source_retention": scores["adapted_prob_dcta"] / scores["adapted_known_source_dcta"],
        "ceiling_retention": scores["adapted_prob_dcta"] / ceiling,
        "initial_source_brier": {"adapted": adapted_initial_brier, "external": external_initial_brier},
        "adapted_initial_source_top1": statistics.fmean(source_top1),
        "sensitivity": sensitivity,
        "citation_redactions": public["citation_redactions"],
        "hashes": {"adapted": sha256(ADAPTED), "external": sha256(EXTERNAL),
                   "public": sha256(PUBLIC), "private": sha256(PRIVATE), "freeze": sha256(FREEZE)},
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
