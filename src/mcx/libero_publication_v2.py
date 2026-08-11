"""Pure helpers for the frozen LIBERO v2 publication screen."""
from __future__ import annotations

import hashlib
from typing import Mapping, Sequence, Tuple


PROTOCOL = "memory-libero/multi-origin-publication-v2"
EXPECTED_HELDOUT = {
    "libero_90": frozenset((21, 23, 24, 32, 38, 39, 40, 47, 49, 50, 51, 63,
                            65, 66, 72, 73, 74, 75, 78, 81, 83, 86, 87)),
    "libero_spatial": frozenset((3, 4, 5, 7)),
    "libero_object": frozenset((2, 4, 6)),
    "libero_goal": frozenset((3, 4, 5, 8)),
    "libero_10": frozenset((2, 3, 5, 6, 7, 8)),
}


def validate_manifest(manifest: Mapping[str, object]) -> None:
    if manifest.get("protocol") != f"{PROTOCOL}/heldout-manifest":
        raise ValueError("frozen v2 held-out manifest required")
    suites = manifest.get("suites")
    if not isinstance(suites, Mapping) or set(suites) != set(EXPECTED_HELDOUT):
        raise ValueError("manifest suite set changed")
    for suite, expected in EXPECTED_HELDOUT.items():
        entry = suites[suite]
        actual = frozenset(int(value) for value in entry["task_indices"])
        if actual != expected:
            raise ValueError(f"held-out task set changed for {suite}")
        demos = tuple(int(value) for value in entry["demo_indices"])
        expected_demos = (2, 3) if suite == "libero_90" else (0, 1)
        if demos != expected_demos:
            raise ValueError(f"demonstration boundary changed for {suite}")
    if sum(len(values) for values in EXPECTED_HELDOUT.values()) != 40:
        raise AssertionError("frozen held-out population must contain 40 tasks")


def donor_order(suite: str, target: int, task_count: int) -> Tuple[int, ...]:
    return tuple(sorted(
        (donor for donor in range(task_count) if donor != target),
        key=lambda donor: (
            hashlib.sha256(f"{PROTOCOL}|screen|{suite}|{target}|{donor}".encode()).digest(),
            donor,
        ),
    ))


def feasibility_gate(
    eligible: Sequence[Mapping[str, object]], manifest: Mapping[str, object],
) -> Mapping[str, object]:
    total = len(eligible)
    by_suite = {
        suite: sum(str(row["suite"]) == suite for row in eligible)
        for suite in EXPECTED_HELDOUT
    }
    contributing = sum(value > 0 for value in by_suite.values())
    maximum_fraction = max(by_suite.values(), default=0) / total if total else 1.0
    checks = {
        "minimum_eligible_targets": total >= int(manifest["minimum_eligible_targets"]),
        "minimum_contributing_suites": contributing >= int(manifest["minimum_contributing_suites"]),
        "maximum_single_suite_fraction": maximum_fraction <= float(
            manifest["maximum_single_suite_fraction"]
        ),
    }
    return {
        "passed": all(checks.values()), "checks": checks,
        "eligible_target_count": total, "eligible_by_suite": by_suite,
        "contributing_suite_count": contributing,
        "maximum_single_suite_fraction": maximum_fraction,
    }

