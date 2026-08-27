"""Render the README headline-evaluation table across all domains.

MetaWorld and BabyAI numbers come from the frozen expected-metrics file so the
published rows cannot drift.  DDXPlus rows are read from whichever evaluation
reports are passed in, which makes the template-written and model-written
archives directly comparable in one table.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HEADER = ("| Domain | Evaluation unit | TR-DCTA | SC-DCTA | ENS–SharedPosterior "
          "| Full-information reference |\n|---|---:|---:|---:|---:|---:|")


def metaworld_row(expected: dict[str, Any]) -> str:
    value = expected["metaworld"]
    counts = value["recovery_counts"]
    return (f"| MetaWorld test | {value['episodes']} forced-exposure episodes across "
            f"{value['tasks']} tasks | **{counts['tr_dcta']}** | {counts['sc_dcta']} "
            f"| {counts['sc_ens']} | {counts['full_information_oracle']} |")


def babyai_row(expected: dict[str, Any]) -> str:
    value = expected["babyai_unlockpickup"]
    rates = value["recovery_rates"]
    return (f"| BabyAI UnlockPickup | {value['contexts']} held-out contexts, partial "
            f"provenance, budget {value['primary_budget']} | **{rates['tr_dcta']:.4f}** "
            f"| {rates['sc_dcta']:.4f} | {rates['ens']:.4f} "
            f"| {rates['full_information_hindsight']:.4f} |")


def ddxplus_row(label: str, report: dict[str, Any]) -> str:
    summary = report["summaries"]["test"]
    tasks = len({row["task_key"] for row in report["episode_rows"]
                 if row["split"] == "test"})
    episodes = summary["tr_dcta"]["episodes"]

    def count(method: str) -> int:
        return summary[method]["behavioral_recovery_count"]

    return (f"| {label} | {episodes} forced-exposure episodes across {tasks} tasks "
            f"| **{count('tr_dcta')}** | {count('sc_dcta')} | {count('ens')} "
            f"| {count('full_information_oracle')} |")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path,
                        default=ROOT / "expected" / "paper_metrics_v1.json")
    parser.add_argument("--ddxplus", action="append", default=[], metavar="LABEL=PATH",
                        help="a DDXPlus evaluation report, repeatable")
    args = parser.parse_args()

    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    rows = [metaworld_row(expected), babyai_row(expected)]
    for item in args.ddxplus:
        if "=" not in item:
            parser.error(f"expected LABEL=PATH, got {item!r}")
        label, _, path = item.partition("=")
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        if report.get("status") != "EXECUTABLE":
            parser.error(f"{path} did not complete: status={report.get('status')}")
        rows.append(ddxplus_row(label.strip(), report))

    print(HEADER)
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
