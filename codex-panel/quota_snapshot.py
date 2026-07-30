"""Quota snapshot parsing, live loading, fallback scanning, and state writing."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any

from codex_app_server import (
    CodexAppServerError,
    query_codex_app_server,
    resolve_codex_bin,
)


CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
SESSIONS_DIR = CODEX_HOME / "sessions"
CODEX_BIN = resolve_codex_bin()
RUNTIME_DIR = Path(
    os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
)
STATE_FILE = RUNTIME_DIR / "codex-quota.json"

MIN_RECENT_FILES = 40
MAX_TAIL_BYTES = 2 * 1024 * 1024
MAX_FILE_SCAN_BYTES = 8 * 1024 * 1024
MAX_PROTOCOL_LINE_BYTES = 1024 * 1024
FALLBACK_SCAN_BUDGET_SECONDS = 0.5
LIVE_QUERY_TIMEOUT_SECONDS = 10.0
LIVE_QUERY_INTERVAL_SECONDS = 60.0
LIVE_FAILURE_RETRY_MAX_SECONDS = 600.0
BOOTSTRAP_RETRY_INITIAL_SECONDS = 5.0
BOOTSTRAP_RETRY_MAX_SECONDS = 60.0
FORCED_LIVE_QUERY_MIN_INTERVAL_SECONDS = 2.0


def _clamp(
    value: float,
    lower: float = 0.0,
    upper: float = 100.0,
) -> float:
    return max(lower, min(upper, value))


def _timestamp_seconds(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        return None


def _window_name(minutes: int) -> tuple[str, str]:
    if minutes == 300:
        return "5h", "5-hour"
    if minutes == 10080:
        return "Week", "Weekly"
    if minutes > 0 and minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days}d", f"{days}-day"
    if minutes > 0 and minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours}h", f"{hours}-hour"
    return f"{minutes}m", f"{minutes}-minute"


def _snapshot_from_rate_limits(
    rate_limits: dict[str, Any],
    timestamp: str,
    *,
    camel_case: bool,
) -> tuple[float, dict[str, Any]] | None:
    """Normalize one main Codex rate-limit object into the panel snapshot."""
    limit_id_key = "limitId" if camel_case else "limit_id"
    limit_name_key = "limitName" if camel_case else "limit_name"
    used_percent_key = "usedPercent" if camel_case else "used_percent"
    window_minutes_key = (
        "windowDurationMins" if camel_case else "window_minutes"
    )
    resets_at_key = "resetsAt" if camel_case else "resets_at"
    plan_type_key = "planType" if camel_case else "plan_type"

    limit_id = rate_limits.get(limit_id_key)
    if limit_id not in (None, "codex"):
        return None
    limit_name = rate_limits.get(limit_name_key)
    if not isinstance(limit_name, str):
        limit_name = None

    timestamp_seconds = _timestamp_seconds(timestamp)
    if timestamp_seconds is None:
        return None

    limits: list[dict[str, Any]] = []
    for bucket_name in ("primary", "secondary"):
        bucket = rate_limits.get(bucket_name)
        if not isinstance(bucket, dict):
            continue

        try:
            used_percent = float(bucket[used_percent_key])
            window_minutes = int(bucket[window_minutes_key])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(used_percent) or window_minutes <= 0:
            continue

        short_name, long_name = _window_name(window_minutes)
        resets_at = bucket.get(resets_at_key)
        if not isinstance(resets_at, (int, float)) or not math.isfinite(
            float(resets_at)
        ):
            resets_at = None

        limits.append(
            {
                "window_minutes": window_minutes,
                "short_name": short_name,
                "long_name": long_name,
                "used_percent": _clamp(used_percent),
                "remaining_percent": _clamp(100.0 - used_percent),
                "resets_at": (
                    int(resets_at) if resets_at is not None else None
                ),
            }
        )

    if not limits:
        return None

    limits.sort(key=lambda item: item["window_minutes"])
    snapshot = {
        "updated_at": timestamp,
        "updated_at_seconds": timestamp_seconds,
        "limit_id": limit_id,
        "limit_name": limit_name,
        "plan_type": rate_limits.get(plan_type_key),
        "limits": limits,
    }
    return timestamp_seconds, snapshot


def snapshot_from_record(
    record: dict[str, Any],
) -> tuple[float, dict[str, Any]] | None:
    """Return a compact quota snapshot from one Codex JSONL record."""
    if record.get("type") != "event_msg":
        return None

    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None

    rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, dict):
        return None

    timestamp = record.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    return _snapshot_from_rate_limits(
        rate_limits,
        timestamp,
        camel_case=False,
    )


def snapshot_from_account_result(
    result: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> dict[str, Any] | None:
    """Return the account's main Codex quota, ignoring model buckets."""
    rate_limits = result.get("rateLimits")
    if not isinstance(rate_limits, dict) or rate_limits.get("limitId") != "codex":
        rate_limits_by_id = result.get("rateLimitsByLimitId")
        if not isinstance(rate_limits_by_id, dict):
            return None
        rate_limits = rate_limits_by_id.get("codex")
    if not isinstance(rate_limits, dict):
        return None

    if timestamp is None:
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    parsed = _snapshot_from_rate_limits(
        rate_limits,
        timestamp,
        camel_case=True,
    )
    return parsed[1] if parsed is not None else None


def read_live_snapshot(
    codex_bin: Path = CODEX_BIN,
    timeout_seconds: float = LIVE_QUERY_TIMEOUT_SECONDS,
    *,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any] | None:
    """Query the shared app-server transport for the live quota snapshot."""
    try:
        result = query_codex_app_server(
            codex_bin,
            "account/rateLimits/read",
            None,
            timeout_seconds=timeout_seconds,
            max_line_bytes=MAX_PROTOCOL_LINE_BYTES,
            cancel_event=cancel_event,
        )
    except CodexAppServerError:
        return None
    return snapshot_from_account_result(result)


class LiveSnapshotReader:
    """Cancelable live reader used by the service's worker thread."""

    def __init__(
        self,
        codex_bin: Path = CODEX_BIN,
        timeout_seconds: float = LIVE_QUERY_TIMEOUT_SECONDS,
    ) -> None:
        self._codex_bin = codex_bin
        self._timeout_seconds = timeout_seconds
        self._cancel_event = threading.Event()

    def __call__(self) -> dict[str, Any] | None:
        return read_live_snapshot(
            self._codex_bin,
            self._timeout_seconds,
            cancel_event=self._cancel_event,
        )

    def cancel(self) -> None:
        self._cancel_event.set()

    def cancelled(self) -> bool:
        return self._cancel_event.is_set()


def _iter_file_lines_reverse(
    handle,
    *,
    max_scan_bytes: int = MAX_FILE_SCAN_BYTES,
    cancel_check=None,
):
    """Yield recent lines newest-first with bounded memory and total I/O."""
    handle.seek(0, os.SEEK_END)
    position = handle.tell()
    scanned = 0
    partial = b""
    discarding_oversized_line = False

    while position > 0 and scanned < max_scan_bytes:
        if cancel_check is not None and cancel_check():
            return
        read_size = min(
            64 * 1024,
            position,
            max_scan_bytes - scanned,
        )
        position -= read_size
        chunk = os.pread(handle.fileno(), read_size, position)
        if not chunk:
            break
        scanned += len(chunk)

        if discarding_oversized_line:
            boundary = chunk.rfind(b"\n")
            if boundary < 0:
                continue
            chunk = chunk[:boundary] + b"\n"
            discarding_oversized_line = False
            partial = b""

        data = chunk + partial
        parts = data.split(b"\n")
        partial = parts[0]
        for raw_line in reversed(parts[1:]):
            if raw_line:
                yield raw_line

        if len(partial) > MAX_TAIL_BYTES:
            partial = b""
            discarding_oversized_line = True

    if position == 0 and partial and not discarding_oversized_line:
        yield partial


def _latest_snapshot_in_file(
    path: Path,
    *,
    cancel_check=None,
) -> tuple[float, dict[str, Any]] | None:
    try:
        with path.open("rb") as handle:
            for raw_line in _iter_file_lines_reverse(
                handle,
                cancel_check=cancel_check,
            ):
                if b'"rate_limits"' not in raw_line:
                    continue
                try:
                    record = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(record, dict):
                    continue
                snapshot = snapshot_from_record(record)
                if snapshot is not None:
                    return snapshot
    except OSError:
        return None
    return None


def find_latest_snapshot(
    sessions_dir: Path = SESSIONS_DIR,
    *,
    cancel_check=None,
) -> dict[str, Any] | None:
    """Return the newest fallback snapshot within a bounded scan window."""
    files: list[tuple[float, Path]] = []
    try:
        for current_root, directories, filenames in os.walk(
            sessions_dir,
            followlinks=False,
        ):
            if cancel_check is not None and cancel_check():
                return None
            current_path = Path(current_root)
            directories[:] = [
                directory
                for directory in directories
                if not (current_path / directory).is_symlink()
            ]
            for filename in filenames:
                if not filename.endswith(".jsonl"):
                    continue
                if cancel_check is not None and cancel_check():
                    return None
                path = current_path / filename
                try:
                    modified_at = path.stat().st_mtime
                except OSError:
                    modified_at = -1.0
                files.append((modified_at, path))
    except OSError:
        return None

    if cancel_check is not None and cancel_check():
        return None
    files.sort(key=lambda item: item[0], reverse=True)
    newest: tuple[float, dict[str, Any]] | None = None
    started = time.monotonic()
    for index, (_modified_at, path) in enumerate(files):
        if cancel_check is not None and cancel_check():
            return None
        candidate = _latest_snapshot_in_file(
            path,
            cancel_check=cancel_check,
        )
        if candidate is not None and (
            newest is None or candidate[0] > newest[0]
        ):
            newest = candidate
        if (
            newest is not None
            and index + 1 >= MIN_RECENT_FILES
            and time.monotonic() - started >= FALLBACK_SCAN_BUDGET_SECONDS
        ):
            break
    return newest[1] if newest is not None else None


@dataclass(frozen=True)
class SnapshotLoadResult:
    snapshot: dict[str, Any] | None
    live_attempted: bool
    live_succeeded: bool
    retry_after_seconds: float


class SnapshotLoader:
    """Single-flight quota cache with a minimum live-query interval."""

    def __init__(
        self,
        sessions_dir: Path = SESSIONS_DIR,
        live_reader=read_live_snapshot,
        clock=time.monotonic,
        *,
        live_query_interval_seconds: float = LIVE_QUERY_INTERVAL_SECONDS,
        live_failure_retry_max_seconds: float = (
            LIVE_FAILURE_RETRY_MAX_SECONDS
        ),
        bootstrap_retry_initial_seconds: float = (
            BOOTSTRAP_RETRY_INITIAL_SECONDS
        ),
        bootstrap_retry_max_seconds: float = (
            BOOTSTRAP_RETRY_MAX_SECONDS
        ),
        forced_query_min_interval_seconds: float = (
            FORCED_LIVE_QUERY_MIN_INTERVAL_SECONDS
        ),
    ) -> None:
        self._sessions_dir = sessions_dir
        self._live_reader = live_reader
        self._clock = clock
        self._live_query_interval_seconds = max(
            0.0,
            live_query_interval_seconds,
        )
        self._live_failure_retry_max_seconds = max(
            self._live_query_interval_seconds,
            live_failure_retry_max_seconds,
        )
        self._bootstrap_retry_initial_seconds = max(
            1.0,
            bootstrap_retry_initial_seconds,
        )
        self._bootstrap_retry_max_seconds = max(
            self._bootstrap_retry_initial_seconds,
            bootstrap_retry_max_seconds,
        )
        self._forced_query_min_interval_seconds = max(
            0.0,
            forced_query_min_interval_seconds,
        )
        self._current_live_query_interval_seconds = (
            self._live_query_interval_seconds
        )
        self._next_failure_retry_seconds = (
            self._live_query_interval_seconds
        )
        self._next_bootstrap_retry_seconds = (
            self._bootstrap_retry_initial_seconds
        )
        self._has_live_succeeded = False
        self._last_live_attempt_at: float | None = None
        self._last_good_snapshot: dict[str, Any] | None = None
        self._current_snapshot: dict[str, Any] | None = None

    @staticmethod
    def _with_status(
        snapshot: dict[str, Any],
        *,
        source: str,
        stale: bool,
    ) -> dict[str, Any]:
        decorated = dict(snapshot)
        decorated["_source"] = source
        decorated["_stale"] = stale
        return decorated

    def seconds_until_live_query(
        self,
        *,
        force_live: bool = False,
    ) -> float:
        if self._last_live_attempt_at is None:
            return 0.0
        interval = (
            self._forced_query_min_interval_seconds
            if force_live
            else self._current_live_query_interval_seconds
        )
        elapsed = self._clock() - self._last_live_attempt_at
        return max(0.0, interval - elapsed)

    def load_result(
        self,
        *,
        force_live: bool = False,
    ) -> SnapshotLoadResult:
        retry_after = self.seconds_until_live_query(force_live=force_live)
        if retry_after > 0:
            return SnapshotLoadResult(
                self._current_snapshot,
                live_attempted=False,
                live_succeeded=False,
                retry_after_seconds=retry_after,
            )

        self._last_live_attempt_at = self._clock()
        try:
            live_snapshot = self._live_reader()
        except Exception:
            live_snapshot = None

        if live_snapshot is not None:
            self._has_live_succeeded = True
            self._current_live_query_interval_seconds = (
                self._live_query_interval_seconds
            )
            self._next_failure_retry_seconds = (
                self._live_query_interval_seconds
            )
            self._next_bootstrap_retry_seconds = (
                self._bootstrap_retry_initial_seconds
            )
            fresh = self._with_status(
                live_snapshot,
                source="live",
                stale=False,
            )
            self._last_good_snapshot = fresh
            self._current_snapshot = fresh
            return SnapshotLoadResult(
                fresh,
                live_attempted=True,
                live_succeeded=True,
                retry_after_seconds=self._live_query_interval_seconds,
            )

        if self._has_live_succeeded:
            retry_after_seconds = min(
                self._live_failure_retry_max_seconds,
                max(
                    self._live_query_interval_seconds,
                    self._next_failure_retry_seconds,
                ),
            )
            self._next_failure_retry_seconds = min(
                self._live_failure_retry_max_seconds,
                max(
                    self._live_query_interval_seconds,
                    retry_after_seconds * 2,
                ),
            )
        else:
            retry_after_seconds = self._next_bootstrap_retry_seconds
            self._next_bootstrap_retry_seconds = min(
                self._bootstrap_retry_max_seconds,
                max(
                    self._bootstrap_retry_initial_seconds,
                    retry_after_seconds * 2,
                ),
            )
        self._current_live_query_interval_seconds = retry_after_seconds

        if self._last_good_snapshot is not None:
            stale = dict(self._last_good_snapshot)
            stale["_source"] = "cache"
            stale["_stale"] = True
            self._current_snapshot = stale
        else:
            cancel_check = getattr(self._live_reader, "cancelled", None)
            local_snapshot = find_latest_snapshot(
                self._sessions_dir,
                cancel_check=cancel_check,
            )
            if local_snapshot is not None:
                stale = self._with_status(
                    local_snapshot,
                    source="session",
                    stale=True,
                )
                self._last_good_snapshot = stale
                self._current_snapshot = stale
            else:
                self._current_snapshot = None

        return SnapshotLoadResult(
            self._current_snapshot,
            live_attempted=True,
            live_succeeded=False,
            retry_after_seconds=retry_after_seconds,
        )

    def load(
        self,
        *,
        force_live: bool = False,
    ) -> dict[str, Any] | None:
        return self.load_result(force_live=force_live).snapshot

    def mark_current_stale(
        self,
        *,
        source: str = "offline",
    ) -> dict[str, Any] | None:
        """Return and retain a stale copy when freshness is externally lost."""
        if self._current_snapshot is None:
            return None
        stale = dict(self._current_snapshot)
        stale["_source"] = source
        stale["_stale"] = True
        self._current_snapshot = stale
        return stale


def load_snapshot(
    sessions_dir: Path = SESSIONS_DIR,
) -> dict[str, Any] | None:
    """Compatibility helper for one immediate live-or-session lookup."""
    return SnapshotLoader(sessions_dir).load(force_live=True)


def _state_semantics(payload: dict[str, Any]) -> dict[str, Any]:
    """Ignore timestamp formatting, but retain the freshness verification."""
    return {
        key: value
        for key, value in payload.items()
        if key != "updated_at"
    }


def write_state_file(
    snapshot: dict[str, Any] | None,
    path: Path = STATE_FILE,
) -> bool:
    """Atomically publish state only when its user-visible meaning changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot if snapshot is not None else {"limits": []}

    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        existing = None
    if (
        isinstance(existing, dict)
        and _state_semantics(existing) == _state_semantics(payload)
    ):
        try:
            if path.stat().st_mode & 0o777 != 0o600:
                os.chmod(path, 0o600)
            return False
        except OSError:
            pass

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            os.fchmod(temporary.fileno(), 0o600)
            json.dump(
                payload,
                temporary,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        return True
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
