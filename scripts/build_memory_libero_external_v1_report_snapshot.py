"""Materialize the reviewed report snapshot as a queryable SQLite table."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "memory_libero_external_v1"


def main() -> None:
    artifact = json.loads((REPORT_DIR / "artifact.json").read_text(encoding="utf-8"))
    rows = []
    for dataset, records in artifact["snapshot"]["datasets"].items():
        for index, record in enumerate(records):
            rows.append((dataset, index, json.dumps(record, sort_keys=True)))
    target = REPORT_DIR / "report_snapshot.sqlite"
    with sqlite3.connect(target) as connection:
        connection.execute("DROP TABLE IF EXISTS report_snapshot")
        connection.execute(
            "CREATE TABLE report_snapshot (dataset TEXT NOT NULL, row_index INTEGER NOT NULL, row_json TEXT NOT NULL, PRIMARY KEY (dataset, row_index))"
        )
        connection.executemany("INSERT INTO report_snapshot VALUES (?, ?, ?)", rows)
        connection.commit()
        count = connection.execute("SELECT COUNT(*) FROM report_snapshot").fetchone()[0]
    print(f"materialized {count} reviewed rows to {target}")


if __name__ == "__main__":
    main()
