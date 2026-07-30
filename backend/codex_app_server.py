"""Bounded one-shot transport for the Codex app-server JSONL protocol."""

from __future__ import annotations

import json
import os
from pathlib import Path
import select
import signal
import shutil
import subprocess
import threading
import time
from typing import Any


PROCESS_STOP_GRACE_SECONDS = 0.2
READ_CHUNK_BYTES = 64 * 1024


def resolve_codex_bin() -> Path:
    """Resolve the configured Codex CLI without assuming one user home."""

    configured = os.environ.get("CODEX_BIN")
    if configured:
        return Path(configured)
    discovered = shutil.which("codex")
    if discovered:
        return Path(discovered)
    return Path.home() / ".local/bin/codex"


class CodexAppServerError(RuntimeError):
    """Base class for expected one-shot app-server failures."""


class CodexAppServerCancelled(CodexAppServerError):
    """Raised when the caller cancels an app-server request."""


class CodexAppServerTimeout(CodexAppServerError):
    """Raised when an app-server request exceeds its total deadline."""


class CodexAppServerProtocolError(CodexAppServerError):
    """Raised when the app-server does not return a usable result."""


class CodexAppServerResponseTooLarge(CodexAppServerProtocolError):
    """Raised when one app-server JSONL response exceeds the size limit."""


class CodexAppServerLaunchError(CodexAppServerError):
    """Raised when the app-server process or its pipes cannot be started."""


def _signal_process_group(
    process: subprocess.Popen[bytes],
    sig: signal.Signals,
) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.send_signal(sig)
        except ProcessLookupError:
            pass


def _terminate_process(
    process: subprocess.Popen[bytes],
    grace_seconds: float = PROCESS_STOP_GRACE_SECONDS,
) -> None:
    """Stop an app-server process group without a multi-second wait."""
    if process.poll() is not None:
        try:
            process.wait(timeout=0)
        except (ChildProcessError, subprocess.TimeoutExpired):
            pass
        return

    _signal_process_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass

    _signal_process_group(process, signal.SIGKILL)
    try:
        process.wait(timeout=grace_seconds)
    except (ChildProcessError, subprocess.TimeoutExpired):
        pass


def _request_wire(method: str, params: Any) -> bytes:
    requests = (
        {
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "codex-dashboard",
                    "version": "1.0",
                }
            },
        },
        {"method": "initialized"},
        {"id": 2, "method": method, "params": params},
    )
    return b"".join(
        json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
        for request in requests
    )


def _cancelled(cancel_event: threading.Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def query_codex_app_server(
    codex_bin: str | Path,
    method: str,
    params: Any = None,
    *,
    timeout_seconds: float,
    max_line_bytes: int,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run one initialized app-server request and return response ``result``.

    The timeout covers process startup, writes, and reads. The child owns a new
    process group, which is always terminated on return or failure.
    """
    if not isinstance(method, str) or not method:
        raise ValueError("method must be a non-empty string")
    if max_line_bytes <= 0:
        raise ValueError("max_line_bytes must be positive")
    if _cancelled(cancel_event):
        raise CodexAppServerCancelled("Codex app-server request was cancelled")

    process: subprocess.Popen[bytes] | None = None
    stdout_buffer = bytearray()
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    try:
        try:
            process = subprocess.Popen(
                [str(codex_bin), "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
                start_new_session=True,
            )
        except OSError as error:
            raise CodexAppServerLaunchError(
                f"Cannot start Codex app-server: {error}"
            ) from error

        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise CodexAppServerLaunchError(
                "Codex app-server pipes are unavailable"
            )
        if _cancelled(cancel_event):
            raise CodexAppServerCancelled(
                "Codex app-server request was cancelled"
            )

        try:
            process.stdin.write(_request_wire(method, params))
            process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise CodexAppServerProtocolError(
                "Codex app-server closed its request pipe"
            ) from error

        stdout_fd = process.stdout.fileno()
        stderr_fd = process.stderr.fileno()
        os.set_blocking(stdout_fd, False)
        os.set_blocking(stderr_fd, False)
        open_fds = {stdout_fd, stderr_fd}

        while True:
            while True:
                newline = stdout_buffer.find(b"\n")
                if newline < 0:
                    break
                if newline > max_line_bytes:
                    raise CodexAppServerResponseTooLarge(
                        "Codex app-server response exceeded the line limit"
                    )
                raw_line = bytes(stdout_buffer[:newline])
                del stdout_buffer[: newline + 1]
                if not raw_line:
                    continue
                try:
                    response = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(response, dict) or response.get("id") != 2:
                    continue
                if "error" in response:
                    raise CodexAppServerProtocolError(
                        "Codex app-server returned an error response"
                    )
                result = response.get("result")
                if not isinstance(result, dict):
                    raise CodexAppServerProtocolError(
                        "Codex app-server response has no object result"
                    )
                return result

            if len(stdout_buffer) > max_line_bytes:
                raise CodexAppServerResponseTooLarge(
                    "Codex app-server response exceeded the line limit"
                )
            if _cancelled(cancel_event):
                raise CodexAppServerCancelled(
                    "Codex app-server request was cancelled"
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexAppServerTimeout(
                    "Codex app-server request timed out"
                )
            if not open_fds:
                raise CodexAppServerProtocolError(
                    "Codex app-server ended before responding"
                )

            try:
                readable, _, _ = select.select(
                    list(open_fds),
                    [],
                    [],
                    min(remaining, 0.1),
                )
            except InterruptedError:
                continue

            for file_descriptor in readable:
                try:
                    chunk = os.read(file_descriptor, READ_CHUNK_BYTES)
                except BlockingIOError:
                    continue
                if not chunk:
                    open_fds.discard(file_descriptor)
                    continue
                if file_descriptor == stdout_fd:
                    stdout_buffer.extend(chunk)
    finally:
        if process is not None:
            if process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            _terminate_process(process)
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    try:
                        stream.close()
                    except OSError:
                        pass
