"""A tiny "store generation" marker: changes whenever stored observations change.

Imports (``ObservationStore.commit_run``) and compaction bump it; readers compare it to
decide whether derived data (cell-day aggregates, cached area results) may be reused.
It is a file, so a separate process (the import CLI) invalidates the API's caches.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

MARKER = ".store_generation"


def bump(processed_dir: Path) -> str:
    """Write a new generation token atomically and return it."""
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    tmp = processed_dir / f"{MARKER}.{token}.partial"
    tmp.write_text(token, encoding="ascii")
    os.replace(tmp, processed_dir / MARKER)
    return token


def current(processed_dir: Path) -> str:
    """The current token; "initial" before anything was ever stored."""
    try:
        return (Path(processed_dir) / MARKER).read_text(encoding="ascii").strip() or "initial"
    except FileNotFoundError:
        return "initial"
