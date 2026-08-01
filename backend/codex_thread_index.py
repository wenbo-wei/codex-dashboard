"""Open the newest valid Codex thread index in strict read-only mode."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import stat
from typing import Iterator


@contextmanager
def open_thread_index(
    codex_home: Path,
) -> Iterator[sqlite3.Connection]:
    """Yield the newest regular state database through a read-only connection."""

    candidates: list[tuple[int, Path]] = []
    for path in codex_home.glob("state_*.sqlite"):
        try:
            metadata = path.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(
            metadata.st_mode
        ):
            continue
        candidates.append((metadata.st_mtime_ns, path))

    if not candidates:
        raise FileNotFoundError("Codex thread index is unavailable")
    state_db = max(candidates)[1]
    connection = sqlite3.connect(
        f"file:{state_db}?mode=ro",
        uri=True,
        timeout=0.5,
    )
    try:
        yield connection
    finally:
        connection.close()
