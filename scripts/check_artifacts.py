"""Verify external reproduction artifacts without reading private labels into methods."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path,
                        default=Path("artifacts/manifest.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--group", action="append",
                        help="Verify only this group; may be repeated")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    groups = set(args.group or [])
    rows = [row for row in manifest["files"]
            if not groups or row["group"] in groups]
    # A path may serve multiple groups; verify it once.
    unique = {row["path"]: row for row in rows}
    failures = []
    for relative, expected in sorted(unique.items()):
        path = args.root / relative
        if not path.is_file():
            failures.append({"path": relative, "error": "missing"})
            continue
        size = path.stat().st_size
        actual = sha256(path)
        if size != int(expected["bytes"]) or actual != expected["sha256"]:
            failures.append({"path": relative, "error": "mismatch",
                             "expected_bytes": expected["bytes"],
                             "actual_bytes": size,
                             "expected_sha256": expected["sha256"],
                             "actual_sha256": actual})
    status = {"verified": not failures, "files_checked": len(unique),
              "groups": sorted(groups) if groups else "all", "failures": failures}
    print(json.dumps(status, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())

