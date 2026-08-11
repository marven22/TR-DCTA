"""Per-run output folders.

Each run writes into its own timestamped folder inside the results directory:

    results/
    ├── 20260731-105233/     # one run
    └── 20260731-110417/     # another run

Nothing is ever overwritten. The chained scripts (counterfactual, evaluation)
default to the most recent folder.
"""
from __future__ import annotations

import datetime
import os
from typing import Optional


def new_run_dir(base: str) -> str:
    """Create and return results/<timestamp>/ for a fresh run.

    The timestamp includes milliseconds so two runs in the same second don't
    collide (the fast scripted backend can finish several per second).
    """
    now = datetime.datetime.now()
    ts = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}"
    directory = os.path.join(base, ts)
    os.makedirs(directory, exist_ok=True)
    return directory


def latest_run_dir(base: str) -> Optional[str]:
    """Return the most recent run folder under ``base`` (or None if there are none)."""
    if not os.path.isdir(base):
        return None
    subdirs = [
        os.path.join(base, name)
        for name in os.listdir(base)
        if os.path.isdir(os.path.join(base, name))
    ]
    return max(subdirs, key=os.path.getmtime) if subdirs else None
