"""Fail on common publication-repository hygiene and disclosure errors."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Directories and files that .gitignore already excludes can never reach a
# release, so scanning them only produces false alarms on a working checkout
# that has benchmark downloads in place.
IGNORED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                 "data", "datasets", "checkpoints", ".cache"}
IGNORED_NAMES = {".DS_Store", "Thumbs.db"}
FORBIDDEN_SUFFIXES = {".pdf", ".pt", ".pth", ".bin", ".sqlite", ".db", ".hdf5", ".h5"}
ABSOLUTE = re.compile(r"(?:[A-Za-z]:[\\/](?:Users|home)[\\/]|/home/|/Users/)")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*['\"][^'\"]+['\"]"
)


def included_files() -> list[Path]:
    return [path for path in ROOT.rglob("*") if path.is_file()
            and path.name not in IGNORED_NAMES
            and not any(part in IGNORED_PARTS for part in path.parts)]


def main() -> int:
    failures: list[dict[str, object]] = []
    files = included_files()
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if re.search(r"(?i)(cupcase|medagentbench|medmcqa|wofost)", path.name):
            failures.append({"path": relative, "error": "out-of-scope research artifact"})
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append({"path": relative, "error": "forbidden binary/data suffix"})
        if path.stat().st_size > 5 * 1024 * 1024:
            failures.append({"path": relative, "error": "file exceeds 5 MiB"})
        if path.suffix.lower() not in {".py", ".json", ".toml", ".md", ".txt", ".yml",
                                      ".yaml", ".cff", ".template", ".sh", ""}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append({"path": relative, "error": "unexpected non-UTF-8 file"})
            continue
        if path.name != "audit_release.py" and ABSOLUTE.search(text):
            failures.append({"path": relative, "error": "machine-specific absolute path"})
        if SECRET_ASSIGNMENT.search(text):
            failures.append({"path": relative, "error": "possible embedded credential"})

    required = [
        "README.md", "MANIFEST.md", "RELEASE_CHECKLIST.md", "pyproject.toml",
        "artifacts/manifest.json", "expected/paper_metrics_v1.json",
        "docs/REPRODUCIBILITY.md", "docs/BASELINE_PROVENANCE.md",
        "src/mcx/terminal_recovery_dcta.py",
        "src/mcx/metaworld_terminal_recovery_dcta.py",
        "scripts/run_metaworld_tr_dcta_full49_v1.py",
        "scripts/verify_metaworld_tr_dcta_full49_v1.py",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            failures.append({"path": relative, "error": "required release file missing"})
    status = {"passed": not failures, "file_count": len(files),
              "total_bytes": sum(path.stat().st_size for path in files),
              "failures": failures}
    print(json.dumps(status, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
