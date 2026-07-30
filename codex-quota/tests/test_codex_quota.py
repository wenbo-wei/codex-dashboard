#!/usr/bin/python3

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
PANEL_LIB_DIR = REPO_ROOT / "codex-panel"
if str(PANEL_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(PANEL_LIB_DIR))

import codex_app_server
import quota_snapshot as quota_snapshot_module
import quota_sni as quota_sni_module


QUOTA_SOURCE = REPO_ROOT / "codex-quota/codex-quota"
DASHBOARD_DATA_SOURCE = REPO_ROOT / "codex-quota/codex-dashboard-data"
QUOTA = runpy.run_path(str(QUOTA_SOURCE))
QUERY_CODEX_APP_SERVER = codex_app_server.query_codex_app_server
APP_SERVER_CANCELLED = codex_app_server.CodexAppServerCancelled
APP_SERVER_TIMEOUT = codex_app_server.CodexAppServerTimeout
APP_SERVER_RESPONSE_TOO_LARGE = (
    codex_app_server.CodexAppServerResponseTooLarge
)
DASHBOARD_DATA = runpy.run_path(str(DASHBOARD_DATA_SOURCE))
QUOTA_AVAILABILITY = DASHBOARD_DATA["quota_availability"]
SNAPSHOT_FROM_RECORD = quota_snapshot_module.snapshot_from_record
SNAPSHOT_FROM_ACCOUNT_RESULT = (
    quota_snapshot_module.snapshot_from_account_result
)
SNAPSHOT_LOADER = quota_snapshot_module.SnapshotLoader
READ_LIVE_SNAPSHOT = quota_snapshot_module.read_live_snapshot
FIND_LATEST_SNAPSHOT = quota_snapshot_module.find_latest_snapshot
WRITE_STATE_FILE = quota_snapshot_module.write_state_file
MAX_TAIL_BYTES = quota_snapshot_module.MAX_TAIL_BYTES
LIVE_SNAPSHOT_READER = quota_snapshot_module.LiveSnapshotReader
SNAPSHOT_LOAD_RESULT = quota_snapshot_module.SnapshotLoadResult
FORMAT_PANEL_LABEL = quota_sni_module.format_panel_label
BUILD_MENU_ITEMS = quota_sni_module.build_menu_items
FORMAT_REFRESH_LABEL = quota_sni_module.format_refresh_label
FORMAT_RESET_TIME = quota_sni_module.format_reset_time
HEADLESS_MENU = quota_sni_module.HeadlessMenu
HEADLESS_STATUS_ITEM = quota_sni_module.HeadlessStatusItem
CODEX_QUOTA_APPLICATION = QUOTA["CodexQuotaApplication"]
SPINNER_FRAMES = QUOTA["SPINNER_FRAMES"]
FAILURE_NOTIFICATION_THRESHOLD = QUOTA[
    "FAILURE_NOTIFICATION_THRESHOLD"
]
FRESHNESS_DEADLINE_SECONDS = QUOTA["FRESHNESS_DEADLINE_SECONDS"]
QUOTA_EXTENSION = (
    REPO_ROOT / "extensions/codex-quota-centre@local"
)
SERVICE_UNIT = REPO_ROOT / "systemd/codex-quota.service"


def load_quota_snapshot_for_resolution_test():
    module_name = "quota_snapshot_resolution_test"
    source = PANEL_LIB_DIR / "quota_snapshot.py"
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load quota_snapshot test module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def quota_record(limit_id):
    return {
        "timestamp": "2026-07-24T03:10:05.234Z",
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "limit_id": limit_id,
                "limit_name": "Test limit",
                "primary": {
                    "used_percent": 12.0,
                    "window_minutes": 10080,
                    "resets_at": 1785467388,
                },
                "secondary": None,
                "plan_type": None,
            },
        },
    }


def quota_snapshot(remaining_percent, updated_at="2026-07-24T03:20:00Z"):
    used_percent = 100.0 - remaining_percent
    return {
        "updated_at": updated_at,
        "updated_at_seconds": 1784863200.0,
        "limit_id": "codex",
        "limit_name": None,
        "plan_type": "pro",
        "limits": [
            {
                "window_minutes": 10080,
                "short_name": "Week",
                "long_name": "Weekly",
                "used_percent": used_percent,
                "remaining_percent": remaining_percent,
                "resets_at": 1785467388,
            }
        ],
    }


@contextlib.contextmanager
def temporary_timezone(name):
    original = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def write_fake_codex(directory, body):
    executable = Path(directory) / "fake-codex"
    executable.write_text(
        "#!/usr/bin/python3\n" + textwrap.dedent(body),
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


class ModuleSeamTest(unittest.TestCase):
    def test_snapshot_tests_bind_directly_to_snapshot_module(self):
        self.assertIs(
            SNAPSHOT_FROM_RECORD,
            quota_snapshot_module.snapshot_from_record,
        )
        self.assertIs(
            SNAPSHOT_LOADER,
            quota_snapshot_module.SnapshotLoader,
        )
        self.assertIs(
            WRITE_STATE_FILE,
            quota_snapshot_module.write_state_file,
        )
        self.assertEqual(
            SNAPSHOT_FROM_RECORD.__module__,
            "quota_snapshot",
        )
        self.assertEqual(
            SNAPSHOT_LOADER.__module__,
            "quota_snapshot",
        )
        self.assertEqual(
            WRITE_STATE_FILE.__module__,
            "quota_snapshot",
        )

    def test_sni_tests_bind_directly_to_sni_module(self):
        self.assertIs(HEADLESS_MENU, quota_sni_module.HeadlessMenu)
        self.assertIs(
            HEADLESS_STATUS_ITEM,
            quota_sni_module.HeadlessStatusItem,
        )
        self.assertIs(
            BUILD_MENU_ITEMS,
            quota_sni_module.build_menu_items,
        )
        self.assertIs(
            FORMAT_PANEL_LABEL,
            quota_sni_module.format_panel_label,
        )
        self.assertEqual(HEADLESS_MENU.__module__, "quota_sni")
        self.assertEqual(HEADLESS_STATUS_ITEM.__module__, "quota_sni")
        self.assertEqual(BUILD_MENU_ITEMS.__module__, "quota_sni")
        self.assertEqual(FORMAT_PANEL_LABEL.__module__, "quota_sni")

        item = HEADLESS_STATUS_ITEM()
        self.assertEqual(item.get_label(), "Codex --%")
        item.set_label("Codex 75%")
        self.assertEqual(item.get_label(), "Codex 75%")
        self.assertIsNone(HEADLESS_MENU().set_snapshot(quota_snapshot(75.0)))


class CodexBinaryResolutionTest(unittest.TestCase):
    def resolve(self, environment, discovered, home="/users/example"):
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(
                codex_app_server.shutil,
                "which",
                return_value=discovered,
            ) as which,
            mock.patch.object(
                codex_app_server.Path,
                "home",
                return_value=Path(home),
            ),
        ):
            direct = codex_app_server.resolve_codex_bin()
            snapshot_module = load_quota_snapshot_for_resolution_test()
        return direct, snapshot_module.CODEX_BIN, which

    def test_explicit_binary_overrides_path_and_home(self):
        direct, snapshot, which = self.resolve(
            {"CODEX_BIN": "/opt/codex/bin/codex"},
            "/usr/bin/codex",
        )

        self.assertEqual(direct, Path("/opt/codex/bin/codex"))
        self.assertEqual(snapshot, direct)
        which.assert_not_called()

    def test_path_binary_is_shared_with_quota_snapshot(self):
        direct, snapshot, _which = self.resolve({}, "/usr/bin/codex")

        self.assertEqual(direct, Path("/usr/bin/codex"))
        self.assertEqual(snapshot, direct)

    def test_home_binary_is_the_final_fallback(self):
        direct, snapshot, _which = self.resolve({}, None)

        self.assertEqual(direct, Path("/users/example/.local/bin/codex"))
        self.assertEqual(snapshot, direct)


class ResetTimeFormattingTest(unittest.TestCase):
    def test_reset_time_uses_the_desktop_timezone(self):
        with temporary_timezone("UTC"):
            self.assertEqual(
                FORMAT_RESET_TIME(1785258149),
                "Jul 28, 17:02",
            )
        with temporary_timezone("Asia/Shanghai"):
            self.assertEqual(
                FORMAT_RESET_TIME(1785258149),
                "Jul 29, 01:02",
            )


class SnapshotFromRecordTest(unittest.TestCase):
    def test_accepts_legacy_codex_limit(self):
        self.assertIsNotNone(SNAPSHOT_FROM_RECORD(quota_record("codex")))

    def test_rejects_model_specific_limit_as_main_codex_quota(self):
        self.assertIsNone(SNAPSHOT_FROM_RECORD(quota_record("codex_bengalfox")))

    def test_accepts_missing_limit_id_for_older_records(self):
        self.assertIsNotNone(SNAPSHOT_FROM_RECORD(quota_record(None)))

    def test_rejects_non_codex_limit(self):
        self.assertIsNone(SNAPSHOT_FROM_RECORD(quota_record("premium")))

    def test_maps_live_account_main_codex_limit(self):
        self.assertIsNotNone(SNAPSHOT_FROM_ACCOUNT_RESULT)
        parsed = SNAPSHOT_FROM_ACCOUNT_RESULT(
            {
                "rateLimits": {
                    "limitId": "codex",
                    "limitName": None,
                    "primary": {
                        "usedPercent": 24,
                        "windowDurationMins": 10080,
                        "resetsAt": 1785258149,
                    },
                    "secondary": None,
                    "planType": "pro",
                },
                "rateLimitsByLimitId": {
                    "codex_bengalfox": {
                        "limitId": "codex_bengalfox",
                        "limitName": "GPT-5.3-Codex-Spark",
                        "primary": {
                            "usedPercent": 0,
                            "windowDurationMins": 10080,
                            "resetsAt": 1785467803,
                        },
                    }
                },
            },
            timestamp="2026-07-24T03:20:00Z",
        )

        self.assertEqual(parsed["limit_id"], "codex")
        self.assertEqual(parsed["limits"][0]["used_percent"], 24.0)
        self.assertEqual(parsed["limits"][0]["remaining_percent"], 76.0)

    def test_panel_label_has_no_competing_reset_date(self):
        snapshot = {
            "limits": [
                {
                    "remaining_percent": 76.0,
                    "window_minutes": 10080,
                    "resets_at": 1785258149,
                }
            ]
        }

        self.assertEqual(FORMAT_PANEL_LABEL(snapshot), "Codex 76%")

    def test_reset_date_moves_into_codex_menu(self):
        self.assertIsNotNone(BUILD_MENU_ITEMS)
        snapshot = {
            "limits": [
                {
                    "remaining_percent": 76.0,
                    "window_minutes": 10080,
                    "resets_at": 1785258149,
                }
            ]
        }

        with temporary_timezone("Asia/Shanghai"):
            items = BUILD_MENU_ITEMS(snapshot)
        self.assertEqual(
            items,
            [
                (2, "Refreshes: Jul 29, 01:02", True),
                (11, "ChatGPT", True),
            ],
        )
        self.assertFalse(
            any("remaining" in label.lower() for _, label, _ in items)
        )
        self.assertFalse(any(label == "Settings" for _, label, _ in items))

    def test_stale_snapshot_never_adds_a_cached_menu_row(self):
        snapshot = quota_snapshot(76.0)
        snapshot["_source"] = "session"
        snapshot["_stale"] = True

        with temporary_timezone("Asia/Shanghai"):
            items = BUILD_MENU_ITEMS(snapshot)

        self.assertEqual(
            items,
            [
                (2, "Refreshes: Jul 31, 11:09", True),
                (11, "ChatGPT", True),
            ],
        )
        self.assertFalse(
            any(
                "cache" in label.lower() or "retry" in label.lower()
                for _, label, _ in items
            )
        )


class RefreshFeedbackTest(unittest.TestCase):
    def test_spinner_replaces_the_percentage_while_reconnecting(self):
        self.assertEqual(
            SPINNER_FRAMES,
            ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"),
        )
        self.assertEqual(
            FORMAT_REFRESH_LABEL("Codex --%", SPINNER_FRAMES[0]),
            "Codex ⠋",
        )
        self.assertEqual(
            FORMAT_REFRESH_LABEL("Codex 50%", SPINNER_FRAMES[1]),
            "Codex ⠙",
        )

    def test_fallback_value_is_restored_after_reconnect_animation(self):
        class Item:
            def __init__(self):
                self.label = "Codex --%"

            def get_label(self):
                return self.label

            def set_label(self, label):
                self.label = label

        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._spinner_source = 0
        application._spinner_index = 0
        application._spinner_base_label = None
        application._item = Item()

        application._start_refresh_animation()
        source = application._spinner_source
        try:
            self.assertNotEqual(source, 0)
            self.assertEqual(application._item.label, "Codex ⠋")

            application._update_refresh_animation_base("Codex 50%")
            application._start_refresh_animation()

            self.assertEqual(application._spinner_source, source)
            self.assertEqual(
                application._spinner_base_label,
                "Codex 50%",
            )
            self.assertEqual(application._item.label, "Codex ⠋")
        finally:
            application._stop_refresh_animation()

        self.assertEqual(application._spinner_source, 0)
        self.assertIsNone(application._spinner_base_label)
        self.assertEqual(application._item.label, "Codex 50%")

    def test_failed_refresh_spins_until_live_quota_recovers(self):
        class Item:
            def __init__(self):
                self.label = "Codex --%"

            def get_label(self):
                return self.label

            def set_label(self, label):
                self.label = label

        class Menu:
            def set_snapshot(self, _snapshot):
                pass

        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._dirty_generation = 1
        application._quota_dirty = True
        application._refresh_running = True
        application._refresh_queued = False
        application._queued_force = False
        application._live_due_source = 0
        application._live_due_at = None
        application._spinner_source = 0
        application._spinner_index = 0
        application._spinner_base_label = None
        application._item = Item()
        application._menu = Menu()
        scheduled = []
        cancelled = []
        freshness_deadlines = []
        outcomes = []
        application._schedule_live_due = scheduled.append
        application._cancel_live_due = lambda: cancelled.append(True)
        application._schedule_freshness_deadline = (
            freshness_deadlines.append
        )
        application._record_live_outcome = outcomes.append

        failure = SNAPSHOT_LOAD_RESULT(
            quota_snapshot(50.0),
            live_attempted=True,
            live_succeeded=False,
            retry_after_seconds=5.0,
        )
        success = SNAPSHOT_LOAD_RESULT(
            quota_snapshot(49.0),
            live_attempted=True,
            live_succeeded=True,
            retry_after_seconds=60.0,
        )

        class Future:
            def __init__(self, result):
                self._result = result

            def result(self):
                return self._result

        method_globals = CODEX_QUOTA_APPLICATION._finish_refresh.__globals__
        original_write_state_file = method_globals["write_state_file"]
        method_globals["write_state_file"] = lambda _snapshot: None
        application._start_refresh_animation()
        try:
            application._finish_refresh(Future(failure), 1)

            self.assertNotEqual(application._spinner_source, 0)
            self.assertEqual(
                application._spinner_base_label,
                "Codex 50%",
            )
            self.assertEqual(application._item.label, "Codex ⠋")
            self.assertEqual(scheduled, [5.0])
            self.assertEqual(cancelled, [])

            application._refresh_running = True
            application._finish_refresh(Future(success), 1)

            self.assertEqual(application._spinner_source, 0)
            self.assertIsNone(application._spinner_base_label)
            self.assertEqual(application._item.label, "Codex 49%")
            self.assertEqual(cancelled, [])
            self.assertEqual(
                freshness_deadlines,
                [FRESHNESS_DEADLINE_SECONDS],
            )
            self.assertEqual(outcomes, [failure, success])
        finally:
            method_globals["write_state_file"] = original_write_state_file
            application._stop_refresh_animation(restore_label=False)

    def test_network_loss_spins_and_recovery_forces_a_live_refresh(self):
        class Item:
            def __init__(self):
                self.label = "Codex 50%"

            def get_label(self):
                return self.label

            def set_label(self, label):
                self.label = label

        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._network_available = True
        application._quota_dirty = False
        application._dirty_generation = 1
        application._spinner_source = 0
        application._spinner_index = 0
        application._spinner_base_label = None
        application._item = Item()
        cancelled = []
        refreshes = []
        application._cancel_live_due = lambda: cancelled.append(True)
        application.refresh_now = lambda *, force_live=False: (
            refreshes.append(force_live)
        )

        application._network_changed(None, False)
        source = application._spinner_source
        try:
            self.assertFalse(application._network_available)
            self.assertTrue(application._quota_dirty)
            self.assertNotEqual(source, 0)
            self.assertEqual(
                application._spinner_base_label,
                "Codex 50%",
            )
            self.assertEqual(application._item.label, "Codex ⠋")
            self.assertEqual(refreshes, [])

            application._network_changed(None, True)

            self.assertTrue(application._network_available)
            self.assertEqual(application._spinner_source, source)
            self.assertEqual(application._item.label, "Codex ⠋")
            self.assertEqual(refreshes, [True])
            self.assertEqual(cancelled, [True, True])
        finally:
            application._stop_refresh_animation(restore_label=False)

    def test_refresh_waits_for_network_without_starting_a_reader(self):
        class Item:
            def __init__(self):
                self.label = "Codex 50%"

            def get_label(self):
                return self.label

            def set_label(self, label):
                self.label = label

        class Executor:
            def __init__(self):
                self.called = False

            def submit(self, *_args, **_kwargs):
                self.called = True
                raise AssertionError("offline refresh started a reader")

        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._network_available = False
        application._quota_dirty = False
        application._refresh_running = False
        application._spinner_source = 0
        application._spinner_index = 0
        application._spinner_base_label = None
        application._item = Item()
        application._executor = Executor()

        application.refresh_now(force_live=True)
        try:
            self.assertFalse(application._executor.called)
            self.assertFalse(application._refresh_running)
            self.assertTrue(application._quota_dirty)
            self.assertNotEqual(application._spinner_source, 0)
            self.assertEqual(application._item.label, "Codex ⠋")
        finally:
            application._stop_refresh_animation(restore_label=False)

    def test_inflight_success_stays_hidden_until_network_returns(self):
        class Item:
            def __init__(self):
                self.label = "Codex 50%"

            def get_label(self):
                return self.label

            def set_label(self, label):
                self.label = label

        class Menu:
            def set_snapshot(self, _snapshot):
                pass

        class Future:
            @staticmethod
            def result():
                return SNAPSHOT_LOAD_RESULT(
                    quota_snapshot(49.0),
                    live_attempted=True,
                    live_succeeded=True,
                    retry_after_seconds=60.0,
                )

        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._network_available = False
        application._dirty_generation = 2
        application._quota_dirty = True
        application._refresh_running = True
        application._refresh_queued = False
        application._queued_force = False
        application._spinner_source = 0
        application._spinner_index = 0
        application._spinner_base_label = None
        application._item = Item()
        application._menu = Menu()
        scheduled = []
        cancelled = []
        application._schedule_live_due = scheduled.append
        application._cancel_live_due = lambda: cancelled.append(True)
        application._record_live_outcome = lambda _outcome: None

        method_globals = CODEX_QUOTA_APPLICATION._finish_refresh.__globals__
        original_write_state_file = method_globals["write_state_file"]
        method_globals["write_state_file"] = lambda _snapshot: None
        application._update_refresh_animation_base("Codex 50%")
        source = application._spinner_source
        try:
            application._finish_refresh(Future(), 1)

            self.assertEqual(application._spinner_source, source)
            self.assertEqual(
                application._spinner_base_label,
                "Codex 49%",
            )
            self.assertEqual(application._item.label, "Codex ⠋")
            self.assertTrue(application._quota_dirty)
            self.assertEqual(scheduled, [])
            self.assertEqual(cancelled, [True])
        finally:
            method_globals["write_state_file"] = original_write_state_file
            application._stop_refresh_animation(restore_label=False)

    def test_unexpected_refresh_error_keeps_known_value_without_animation(self):
        class Item:
            def __init__(self):
                self.label = "Codex 50%"

            def get_label(self):
                return self.label

            def set_label(self, label):
                self.label = label

        class Future:
            @staticmethod
            def result():
                raise RuntimeError("test refresh failure")

        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._dirty_generation = 1
        application._quota_dirty = True
        application._refresh_running = True
        application._refresh_queued = False
        application._queued_force = False
        application._spinner_source = 0
        application._spinner_index = 0
        application._spinner_base_label = None
        application._item = Item()
        scheduled = []
        application._schedule_live_due = scheduled.append

        application._start_refresh_animation()
        try:
            self.assertEqual(application._spinner_source, 0)
            self.assertEqual(application._item.label, "Codex 50%")

            with contextlib.redirect_stderr(io.StringIO()):
                application._finish_refresh(Future(), 1)
            self.assertEqual(application._spinner_source, 0)
            self.assertEqual(application._item.label, "Codex 50%")
            self.assertEqual(scheduled, [60.0])
        finally:
            application._stop_refresh_animation(restore_label=False)

    def test_unexpected_initial_refresh_error_keeps_startup_animation(self):
        class Item:
            def __init__(self):
                self.label = "Codex --%"

            def get_label(self):
                return self.label

            def set_label(self, label):
                self.label = label

        class Future:
            @staticmethod
            def result():
                raise RuntimeError("test refresh failure")

        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._dirty_generation = 1
        application._quota_dirty = True
        application._refresh_running = True
        application._refresh_queued = False
        application._queued_force = False
        application._spinner_source = 0
        application._spinner_index = 0
        application._spinner_base_label = None
        application._item = Item()
        scheduled = []
        application._schedule_live_due = scheduled.append

        application._start_refresh_animation()
        source = application._spinner_source
        try:
            self.assertNotEqual(source, 0)
            self.assertEqual(application._item.label, "Codex ⠋")

            with contextlib.redirect_stderr(io.StringIO()):
                application._finish_refresh(Future(), 1)
            self.assertEqual(application._spinner_source, source)
            self.assertEqual(application._item.label, "Codex ⠋")
            self.assertEqual(scheduled, [60.0])
        finally:
            application._stop_refresh_animation(restore_label=False)

    def test_three_live_failures_notify_once_until_recovery(self):
        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        notifications = []
        application._consecutive_live_failures = 0
        application._failure_notification_sent = False
        application._send_refresh_failure_notification = (
            notifications.append
        )
        failure = SNAPSHOT_LOAD_RESULT(
            quota_snapshot(50.0),
            live_attempted=True,
            live_succeeded=False,
            retry_after_seconds=5.0,
        )
        success = SNAPSHOT_LOAD_RESULT(
            quota_snapshot(49.0),
            live_attempted=True,
            live_succeeded=True,
            retry_after_seconds=60.0,
        )

        for _ in range(4):
            application._record_live_outcome(failure)
        self.assertEqual(
            notifications,
            [FAILURE_NOTIFICATION_THRESHOLD],
        )

        application._record_live_outcome(success)
        for _ in range(3):
            application._record_live_outcome(failure)
        self.assertEqual(
            notifications,
            [
                FAILURE_NOTIFICATION_THRESHOLD,
                FAILURE_NOTIFICATION_THRESHOLD,
            ],
        )

    def test_failure_notification_uses_async_desktop_notifications(self):
        calls = []

        class Notifications:
            def Notify(self, *args, **kwargs):
                calls.append((args, kwargs))

        class Bus:
            options = None

            @classmethod
            def get_object(cls, _name, _path, **kwargs):
                cls.options = kwargs
                return Notifications()

        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._bus = Bus()
        application._send_refresh_failure_notification(3)

        self.assertEqual(
            Bus.options,
            {
                "introspect": False,
                "follow_name_owner_changes": True,
            },
        )
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(str(args[0]), "Codex Dashboard")
        self.assertEqual(str(args[3]), "Codex Dashboard update failed")
        self.assertEqual(
            str(args[4]),
            (
                "Unable to update the quota after 3 attempts. "
                "Retrying in the background."
            ),
        )
        self.assertIn("reply_handler", kwargs)
        self.assertIn("error_handler", kwargs)


class SnapshotLoaderTest(unittest.TestCase):
    def loader(self, sessions_dir, live_reader, clock):
        self.assertIsNotNone(
            SNAPSHOT_LOADER,
            "codex-quota must expose SnapshotLoader",
        )
        return SNAPSHOT_LOADER(
            sessions_dir,
            live_reader,
            clock,
            live_query_interval_seconds=60,
        )

    def test_reuses_cached_live_snapshot_until_60_second_ttl_expires(self):
        now = [100.0]
        calls = []
        snapshots = iter([quota_snapshot(70.0), quota_snapshot(55.0)])

        def live_reader():
            calls.append(now[0])
            return next(snapshots)

        with tempfile.TemporaryDirectory() as directory:
            loader = self.loader(Path(directory), live_reader, lambda: now[0])

            first = loader.load()
            now[0] = 159.999
            cached = loader.load()
            now[0] = 160.0
            refreshed = loader.load()

        self.assertEqual(calls, [100.0, 160.0])
        self.assertEqual(first["limits"][0]["remaining_percent"], 70.0)
        self.assertFalse(first["_stale"])
        self.assertEqual(cached, first)
        self.assertEqual(refreshed["limits"][0]["remaining_percent"], 55.0)
        self.assertFalse(refreshed["_stale"])

    def test_force_refresh_bypasses_live_query_ttl_and_resets_it(self):
        now = [200.0]
        calls = []
        snapshots = iter([quota_snapshot(70.0), quota_snapshot(45.0)])

        def live_reader():
            calls.append(now[0])
            return next(snapshots)

        with tempfile.TemporaryDirectory() as directory:
            loader = self.loader(Path(directory), live_reader, lambda: now[0])

            loader.load()
            now[0] = 205.0
            forced = loader.load(force_live=True)
            now[0] = 250.0
            cached = loader.load()

        self.assertEqual(calls, [200.0, 205.0])
        self.assertEqual(forced["limits"][0]["remaining_percent"], 45.0)
        self.assertEqual(cached, forced)

    def test_live_failure_keeps_a_stale_copy_of_last_good_snapshot(self):
        now = [300.0]
        good = quota_snapshot(68.0)
        results = iter([good, None])

        with tempfile.TemporaryDirectory() as directory:
            sessions_dir = Path(directory)
            local_file = sessions_dir / "older.jsonl"
            local_file.write_text(
                json.dumps(quota_record("codex")) + "\n",
                encoding="utf-8",
            )
            loader = self.loader(
                sessions_dir,
                lambda: next(results),
                lambda: now[0],
            )

            fresh = loader.load()
            now[0] = 360.0
            stale = loader.load()

        self.assertFalse(fresh["_stale"])
        self.assertTrue(stale["_stale"])
        self.assertIsNot(stale, fresh)
        self.assertEqual(stale["limits"], fresh["limits"])
        self.assertEqual(
            stale["limits"][0]["remaining_percent"],
            68.0,
            "a failed live query must not replace last-good with an old log",
        )
        self.assertFalse(fresh["_stale"], "marking stale must not mutate last-good")

    def test_failed_empty_lookup_is_negative_cached_until_bootstrap_retry(self):
        now = [400.0]
        calls = []

        def live_reader():
            calls.append(now[0])
            return None

        with tempfile.TemporaryDirectory() as directory:
            loader = self.loader(Path(directory), live_reader, lambda: now[0])

            self.assertIsNone(loader.load())
            now[0] = 401.0
            cached_result = loader.load_result()
            now[0] = 405.0
            self.assertIsNone(loader.load())

        self.assertEqual(calls, [400.0, 405.0])
        self.assertFalse(cached_result.live_attempted)
        self.assertAlmostEqual(cached_result.retry_after_seconds, 4.0)

    def test_bootstrap_retries_quickly_then_steady_failures_back_off(self):
        now = [0.0]
        calls = []
        results = iter(
            [
                None,
                None,
                quota_snapshot(61.0),
                None,
                None,
            ]
        )

        def live_reader():
            calls.append(now[0])
            return next(results)

        with tempfile.TemporaryDirectory() as directory:
            loader = SNAPSHOT_LOADER(
                Path(directory),
                live_reader,
                lambda: now[0],
                live_query_interval_seconds=60,
                live_failure_retry_max_seconds=600,
                bootstrap_retry_initial_seconds=5,
                bootstrap_retry_max_seconds=60,
            )

            first_failure = loader.load_result()
            now[0] = 4.0
            first_cached = loader.load_result()
            now[0] = 5.0
            second_failure = loader.load_result()
            now[0] = 15.0
            recovered = loader.load_result()
            now[0] = 75.0
            steady_failure = loader.load_result()
            now[0] = 135.0
            second_steady_failure = loader.load_result()

        self.assertEqual(calls, [0.0, 5.0, 15.0, 75.0, 135.0])
        self.assertEqual(first_failure.retry_after_seconds, 5.0)
        self.assertFalse(first_cached.live_attempted)
        self.assertAlmostEqual(first_cached.retry_after_seconds, 1.0)
        self.assertEqual(second_failure.retry_after_seconds, 10.0)
        self.assertTrue(recovered.live_succeeded)
        self.assertEqual(recovered.retry_after_seconds, 60.0)
        self.assertEqual(steady_failure.retry_after_seconds, 60.0)
        self.assertEqual(second_steady_failure.retry_after_seconds, 120.0)

    def test_bootstrap_retry_caps_at_60_seconds(self):
        now = [0.0]

        with tempfile.TemporaryDirectory() as directory:
            loader = SNAPSHOT_LOADER(
                Path(directory),
                lambda: None,
                lambda: now[0],
                live_query_interval_seconds=60,
                bootstrap_retry_initial_seconds=5,
                bootstrap_retry_max_seconds=60,
            )
            retries = []
            for delay in (0.0, 5.0, 10.0, 20.0, 40.0, 60.0):
                now[0] += delay
                retries.append(loader.load_result().retry_after_seconds)

        self.assertEqual(retries, [5.0, 10.0, 20.0, 40.0, 60.0, 60.0])


class LiveQueryProtocolTest(unittest.TestCase):
    def test_shared_transport_reports_prelaunch_cancellation(self):
        cancelled = threading.Event()
        cancelled.set()

        with self.assertRaises(APP_SERVER_CANCELLED):
            QUERY_CODEX_APP_SERVER(
                Path("/does/not/exist"),
                "account/rateLimits/read",
                timeout_seconds=1.0,
                max_line_bytes=1024,
                cancel_event=cancelled,
            )

    def test_shared_transport_enforces_total_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = write_fake_codex(
                directory,
                """
                import sys
                import time

                for _ in range(3):
                    sys.stdin.buffer.readline()
                time.sleep(1)
                """,
            )

            started = time.monotonic()
            with self.assertRaises(APP_SERVER_TIMEOUT):
                QUERY_CODEX_APP_SERVER(
                    executable,
                    "account/rateLimits/read",
                    timeout_seconds=0.05,
                    max_line_bytes=1024,
                )
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.5)

    def test_shared_transport_rejects_oversized_response_line(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = write_fake_codex(
                directory,
                """
                import os
                import sys
                import time

                for _ in range(3):
                    sys.stdin.buffer.readline()
                os.write(sys.stdout.fileno(), b"x" * 2048 + b"\\n")
                time.sleep(0.25)
                """,
            )

            with self.assertRaises(APP_SERVER_RESPONSE_TOO_LARGE):
                QUERY_CODEX_APP_SERVER(
                    executable,
                    "account/rateLimits/read",
                    timeout_seconds=0.2,
                    max_line_bytes=1024,
                )

    def test_shared_transport_cancels_an_active_request(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = write_fake_codex(
                directory,
                """
                import sys
                import time

                for _ in range(3):
                    sys.stdin.buffer.readline()
                time.sleep(10)
                """,
            )
            cancelled = threading.Event()
            errors = []

            def query():
                try:
                    QUERY_CODEX_APP_SERVER(
                        executable,
                        "account/rateLimits/read",
                        timeout_seconds=10.0,
                        max_line_bytes=1024,
                        cancel_event=cancelled,
                    )
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=query)
            started = time.monotonic()
            worker.start()
            time.sleep(0.1)
            cancelled.set()
            worker.join(timeout=0.8)
            elapsed = time.monotonic() - started

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], APP_SERVER_CANCELLED)
        self.assertLess(elapsed, 0.8)

    def test_reads_id_2_when_two_responses_arrive_in_one_write(self):
        response = {
            "id": 2,
            "result": {
                "rateLimits": {
                    "limitId": "codex",
                    "limitName": None,
                    "primary": {
                        "usedPercent": 24,
                        "windowDurationMins": 10080,
                        "resetsAt": 1785258149,
                    },
                    "secondary": None,
                    "planType": "pro",
                }
            },
        }
        wire = (
            json.dumps({"id": 1, "result": {}})
            + "\n"
            + json.dumps(response)
            + "\n"
        ).encode()

        with tempfile.TemporaryDirectory() as directory:
            executable = write_fake_codex(
                directory,
                f"""
                import os
                import sys
                import time

                for _ in range(3):
                    sys.stdin.buffer.readline()
                os.write(sys.stdout.fileno(), {wire!r})
                time.sleep(0.25)
                """,
            )
            snapshot = READ_LIVE_SNAPSHOT(executable, timeout_seconds=0.05)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["limits"][0]["remaining_percent"], 76.0)

    def test_partial_line_obeys_the_total_query_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = write_fake_codex(
                directory,
                """
                import os
                import sys
                import time

                for _ in range(3):
                    sys.stdin.buffer.readline()
                os.write(sys.stdout.fileno(), b'{"id":2,"result":')
                time.sleep(1.0)
                """,
            )

            started = time.monotonic()
            snapshot = READ_LIVE_SNAPSHOT(executable, timeout_seconds=0.08)
            elapsed = time.monotonic() - started

        self.assertIsNone(snapshot)
        self.assertLess(
            elapsed,
            0.5,
            "an unterminated line must not make readline exceed the deadline",
        )

    def test_cancel_stops_an_active_app_server_promptly(self):
        self.assertIsNotNone(LIVE_SNAPSHOT_READER)
        with tempfile.TemporaryDirectory() as directory:
            executable = write_fake_codex(
                directory,
                """
                import sys
                import time

                for _ in range(3):
                    sys.stdin.buffer.readline()
                time.sleep(10)
                """,
            )
            reader = LIVE_SNAPSHOT_READER(executable, timeout_seconds=10)
            worker = threading.Thread(target=reader)
            started = time.monotonic()
            worker.start()
            time.sleep(0.1)
            reader.cancel()
            worker.join(timeout=0.8)
            elapsed = time.monotonic() - started

        self.assertFalse(worker.is_alive())
        self.assertLess(elapsed, 0.8)


class LocalFallbackBoundaryTest(unittest.TestCase):
    def test_skips_an_oversized_tail_line_and_finds_the_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            valid_line = json.dumps(quota_record("codex")).encode() + b"\n"
            path.write_bytes(valid_line + b"x" * (MAX_TAIL_BYTES + 4096))

            snapshot = FIND_LATEST_SNAPSHOT(Path(directory))

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["limits"][0]["remaining_percent"], 88.0)

    def test_uses_the_41st_file_when_the_newest_40_have_no_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions_dir = Path(directory)
            valid_path = sessions_dir / "valid.jsonl"
            valid_path.write_text(
                json.dumps(quota_record("codex")) + "\n",
                encoding="utf-8",
            )
            os.utime(valid_path, (1_700_000_000, 1_700_000_000))

            for index in range(40):
                invalid_path = sessions_dir / f"invalid-{index:02d}.jsonl"
                invalid_path.write_text('{"type":"event_msg"}\n', encoding="utf-8")
                modified_at = 1_700_000_001 + index
                os.utime(invalid_path, (modified_at, modified_at))

            quota_globals = FIND_LATEST_SNAPSHOT.__globals__
            original_reader = quota_globals["_latest_snapshot_in_file"]
            files_scanned = []

            def deliberately_slow_reader(path, *, cancel_check=None):
                del cancel_check
                files_scanned.append(path)
                if path == valid_path:
                    return 1_700_000_000.0, quota_snapshot(88.0)
                time.sleep(0.013)
                return None

            try:
                quota_globals["_latest_snapshot_in_file"] = (
                    deliberately_slow_reader
                )
                snapshot = FIND_LATEST_SNAPSHOT(sessions_dir)
            finally:
                quota_globals["_latest_snapshot_in_file"] = original_reader

        self.assertIsNotNone(snapshot)
        self.assertEqual(len(files_scanned), 41)
        self.assertEqual(snapshot["limits"][0]["remaining_percent"], 88.0)


class StateFileTest(unittest.TestCase):
    def test_new_live_verification_persists_equal_quota_freshness(self):
        first = quota_snapshot(70.0, "2026-07-24T03:20:00Z")
        first["updated_at_seconds"] = 1_000.0
        first["_stale"] = False
        first["_source"] = "live"
        equivalent = quota_snapshot(70.0, "2026-07-24T03:21:00Z")
        equivalent["updated_at_seconds"] = 1_300.0
        equivalent["_stale"] = False
        equivalent["_source"] = "live"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codex-quota.json"
            first_written = WRITE_STATE_FILE(first, path)
            fixed_timestamp_ns = 1_700_000_000_123_456_789
            os.utime(path, ns=(fixed_timestamp_ns, fixed_timestamp_ns))
            before = path.stat()

            freshness_written = WRITE_STATE_FILE(equivalent, path)
            refreshed = path.stat()
            refreshed_payload = json.loads(path.read_text(encoding="utf-8"))

            path.chmod(0o644)
            duplicate_written = WRITE_STATE_FILE(equivalent, path)
            repaired = path.stat()
            repaired_mode = repaired.st_mode & 0o777

            changed = dict(equivalent)
            changed["_stale"] = True
            stale_written = WRITE_STATE_FILE(changed, path)
            after_change = path.stat()
            changed_payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(first_written)
        self.assertTrue(freshness_written)
        self.assertFalse(duplicate_written)
        self.assertTrue(stale_written)
        self.assertNotEqual(refreshed.st_ino, before.st_ino)
        self.assertNotEqual(refreshed.st_mtime_ns, fixed_timestamp_ns)
        self.assertEqual(
            refreshed_payload["updated_at"],
            equivalent["updated_at"],
        )
        self.assertEqual(refreshed_payload["updated_at_seconds"], 1_300.0)
        self.assertEqual(
            str(
                QUOTA_AVAILABILITY(
                    refreshed_payload,
                    now_seconds=1_301.0,
                )
            ),
            "ready",
        )
        self.assertEqual(repaired.st_ino, refreshed.st_ino)
        self.assertEqual(repaired_mode, 0o600)
        self.assertNotEqual(after_change.st_ino, refreshed.st_ino)
        self.assertTrue(changed_payload["_stale"])


class GnomeExtensionSourceTest(unittest.TestCase):
    def test_usage_summary_renders_ninety_and_seven_days_without_today(self):
        source = (
            QUOTA_EXTENSION / "extension.js"
        ).read_text(encoding="utf-8")

        self.assertIn("_usageRow('Last 90 days')", source)
        self.assertIn("_usageRow('Last 7 days')", source)
        self.assertIn("formatTokens(usage?.ninety_days)", source)
        self.assertIn("formatTokens(usage?.seven_days)", source)
        self.assertNotIn("_usageToday", source)
        self.assertNotIn("_usageRow('Today')", source)

    def test_quota_extension_is_named_and_managed_independently(self):
        metadata = json.loads(
            (QUOTA_EXTENSION / "metadata.json").read_text(encoding="utf-8")
        )
        source = (QUOTA_EXTENSION / "extension.js").read_text(
            encoding="utf-8"
        )
        stylesheet = (QUOTA_EXTENSION / "stylesheet.css").read_text(
            encoding="utf-8"
        )

        self.assertEqual(metadata["uuid"], "codex-quota-centre@local")
        self.assertEqual(metadata["name"], "Codex Dashboard")
        self.assertEqual(metadata["version"], 1)
        self.assertIn("'Task overview'", source)
        self.assertIn("'codex-dashboard-symbolic'", source)
        self.assertNotIn("Mosaic", metadata["description"])
        self.assertNotIn("Mosaic", source)
        self.assertNotIn("TERMINAL_COMMAND", source)
        self.assertNotIn("_terminalButton", source)
        self.assertNotIn("_openTerminalLayout", source)
        self.assertNotIn("_showTerminalWindows", source)
        self.assertNotIn("_terminalNumber", source)
        self.assertNotIn("__codexSixTerminalButton", source)
        self.assertNotIn(".mosaic-button", stylesheet)
        self.assertNotIn(".terminal-layout-button", stylesheet)

    def test_extension_has_no_appindicator_takeover_or_panel_listeners(self):
        source = (QUOTA_EXTENSION / "extension.js").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("SOURCE_INDICATOR_ID", source)
        self.assertNotIn("'child-added'", source)
        self.assertNotIn("'child-removed'", source)
        self.assertNotIn("_findSourceItem", source)
        self.assertNotIn("_adoptSource", source)
        self.assertNotIn("_releaseSource", source)
        self.assertIn("this._scheduleIntegration();", source)

    def test_service_uses_headless_state_publisher(self):
        quota_source = QUOTA_SOURCE.read_text(encoding="utf-8")
        sni_source = (PANEL_LIB_DIR / "quota_sni.py").read_text(
            encoding="utf-8"
        )
        unit = SERVICE_UNIT.read_text(encoding="utf-8")

        self.assertIn("from quota_sni import", quota_source)
        self.assertIn("class HeadlessStatusItem:", sni_source)
        self.assertIn("class HeadlessMenu:", sni_source)
        self.assertIn("headless=arguments.headless", quota_source)
        self.assertIn("codex-quota --headless", unit)
        self.assertIn("NoNewPrivileges=yes", unit)
        self.assertIn("PrivateTmp=yes", unit)
        self.assertIn("UMask=0077", unit)

    def test_clock_and_codex_have_no_extra_gap(self):
        extension_source = (
            QUOTA_EXTENSION / "extension.js"
        ).read_text(encoding="utf-8")
        stylesheet_path = QUOTA_EXTENSION / "stylesheet.css"
        stylesheet = stylesheet_path.read_text(encoding="utf-8")

        self.assertIn(
            "_applyPanelStyles(dateButton)",
            extension_source,
        )
        self.assertIn(
            "this._addStyle(this._dateButton, CLOCK_BUTTON_STYLE);",
            extension_source,
        )
        self.assertIn(
            "this._addStyle(this._button, CODEX_BUTTON_STYLE);",
            extension_source,
        )
        self.assertIn(
            "#panel .panel-button.clock-display."
            "codex-dashboard-clock-button {\n"
            "  -natural-hpadding: 0px;\n"
            "  -minimum-hpadding: 0px;",
            stylesheet,
        )
        self.assertIn(
            "#panel .panel-button.codex-dashboard-centre-button {\n"
            "  -natural-hpadding: 0.818em;\n"
            "  -minimum-hpadding: 0.818em;",
            stylesheet,
        )
        self.assertNotRegex(
            stylesheet,
            r"margin-(?:left|right):\s*-",
        )

    def test_joined_group_removes_internal_panel_button_padding(self):
        extension_source = (
            QUOTA_EXTENSION / "extension.js"
        ).read_text(encoding="utf-8")
        stylesheet = (QUOTA_EXTENSION / "stylesheet.css").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "const CLOCK_BUTTON_STYLE = "
            "'codex-dashboard-clock-button';",
            extension_source,
        )
        self.assertIn(
            "const CODEX_BUTTON_STYLE = "
            "'codex-dashboard-centre-button';",
            extension_source,
        )
        self.assertIn(
            "#panel .panel-button.clock-display."
            "codex-dashboard-clock-button",
            stylesheet,
        )
        self.assertIn(
            "#panel .panel-button.codex-dashboard-centre-button",
            stylesheet,
        )

class AppIndicatorRegistrationTest(unittest.TestCase):
    def test_watcher_change_after_stop_is_ignored(self):
        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = True
        application._registration_attempt = 5
        application._registration_pending = True

        application._watcher_owner_changed(
            "org.kde.StatusNotifierWatcher",
            "",
            ":1.42",
        )

        self.assertEqual(application._registration_attempt, 5)
        self.assertTrue(application._registration_pending)

    def test_registration_is_async_and_does_not_query_properties(self):
        self.assertIsNotNone(CODEX_QUOTA_APPLICATION)
        calls = []

        class Watcher:
            def RegisterStatusNotifierItem(self, bus_name, **kwargs):
                calls.append((bus_name, kwargs))

        class Bus:
            get_object_options = None

            @classmethod
            def get_object(cls, _name, _path, **kwargs):
                cls.get_object_options = kwargs
                return Watcher()

        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._bus = Bus()
        application._watcher_retry_source = 0
        application._registration_retry_seconds = 8
        application._registration_attempt = 0
        application._registration_pending = False
        application._registration_error_key = None
        application._last_registration_error_log_at = None
        application._clock = lambda: 100.0

        started = time.monotonic()
        application._register_indicator()
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.05)
        self.assertTrue(application._registration_pending)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            Bus.get_object_options,
            {
                "introspect": False,
                "follow_name_owner_changes": True,
            },
        )
        _bus_name, kwargs = calls[0]
        self.assertIn("reply_handler", kwargs)
        self.assertIn("error_handler", kwargs)

        kwargs["reply_handler"]()
        self.assertFalse(application._registration_pending)
        self.assertEqual(application._registration_retry_seconds, 1)

    def test_registration_logs_only_state_changes_and_slow_heartbeats(self):
        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        now = [0.0]
        retries = []
        application._stopping = False
        application._watcher_retry_source = 0
        application._registration_retry_seconds = 1
        application._registration_attempt = 1
        application._registration_pending = True
        application._registration_error_key = None
        application._last_registration_error_log_at = None
        application._clock = lambda: now[0]
        application._schedule_registration_retry = lambda: retries.append(
            now[0]
        )
        application._cancel_registration_retry = lambda: None

        class RegistrationError(Exception):
            def __init__(self, name):
                super().__init__(name)
                self._name = name

            def get_dbus_name(self):
                return self._name

        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            application._registration_failed(
                1,
                RegistrationError("org.example.HostMissing"),
            )
            now[0] = 60.0
            application._registration_attempt = 2
            application._registration_failed(
                2,
                RegistrationError("org.example.HostMissing"),
            )
            now[0] = 61.0
            application._registration_attempt = 3
            application._registration_failed(
                3,
                RegistrationError("org.example.HostHung"),
            )
            now[0] = 961.0
            application._registration_attempt = 4
            application._registration_failed(
                4,
                RegistrationError("org.example.HostHung"),
            )
            now[0] = 962.0
            application._registration_succeeded(4)

        messages = errors.getvalue().splitlines()
        self.assertEqual(len(retries), 4)
        self.assertEqual(len(messages), 4)
        self.assertIn("HostMissing", messages[0])
        self.assertIn("HostHung", messages[1])
        self.assertIn("HostHung", messages[2])
        self.assertEqual(
            messages[3],
            "codex-quota: AppIndicator host ready",
        )


class ApplicationSchedulingTest(unittest.TestCase):
    @staticmethod
    def application():
        application = CODEX_QUOTA_APPLICATION.__new__(
            CODEX_QUOTA_APPLICATION
        )
        application._stopping = False
        application._dirty_generation = 2
        application._quota_dirty = True
        application._refresh_running = True
        application._refresh_queued = False
        application._queued_force = False
        application._live_due_source = 0
        application._live_due_at = None
        application._item = type(
            "Item",
            (),
            {"set_label": lambda _self, _label: None},
        )()
        application._menu = type(
            "Menu",
            (),
            {"set_snapshot": lambda _self, _snapshot: None},
        )()
        return application

    def finish_success(self, refresh_generation):
        application = self.application()
        scheduled = []
        cancelled = []
        freshness_deadlines = []
        application._schedule_live_due = scheduled.append
        application._cancel_live_due = lambda: cancelled.append(True)
        application._schedule_freshness_deadline = (
            freshness_deadlines.append
        )
        future = type(
            "Future",
            (),
            {
                "result": lambda _self: SNAPSHOT_LOAD_RESULT(
                    quota_snapshot(60.0),
                    live_attempted=True,
                    live_succeeded=True,
                    retry_after_seconds=60.0,
                )
            },
        )()

        method_globals = CODEX_QUOTA_APPLICATION._finish_refresh.__globals__
        original_write_state_file = method_globals["write_state_file"]
        method_globals["write_state_file"] = lambda _snapshot: None
        try:
            application._finish_refresh(future, refresh_generation)
        finally:
            method_globals["write_state_file"] = original_write_state_file
        return application, scheduled, cancelled, freshness_deadlines

    def test_success_does_not_erase_a_newer_dirty_event(self):
        application, scheduled, cancelled, freshness = (
            self.finish_success(1)
        )

        self.assertTrue(application._quota_dirty)
        self.assertEqual(scheduled, [60.0])
        self.assertEqual(cancelled, [])
        self.assertEqual(freshness, [FRESHNESS_DEADLINE_SECONDS])

    def test_success_schedules_freshness_for_matching_dirty_generation(self):
        application, scheduled, cancelled, freshness = (
            self.finish_success(2)
        )

        self.assertFalse(application._quota_dirty)
        self.assertEqual(scheduled, [])
        self.assertEqual(cancelled, [])
        self.assertEqual(freshness, [FRESHNESS_DEADLINE_SECONDS])

    def test_freshness_deadline_marks_stale_without_refreshing(self):
        stale = quota_snapshot(60.0)
        stale["_source"] = "freshness-deadline"
        stale["_stale"] = True
        published = []
        menu_snapshots = []
        labels = []

        class Loader:
            calls = []

            @classmethod
            def mark_current_stale(cls, *, source):
                cls.calls.append(source)
                return stale

        application = self.application()
        application._refresh_running = False
        application._freshness_deadline_source = 42
        application._freshness_deadline_at = 123.0
        application._snapshot_loader = Loader()
        application._menu = type(
            "Menu",
            (),
            {
                "set_snapshot": (
                    lambda _self, snapshot: menu_snapshots.append(snapshot)
                )
            },
        )()
        application._item = type(
            "Item",
            (),
            {"set_label": lambda _self, label: labels.append(label)},
        )()
        application.refresh_now = lambda **_kwargs: self.fail(
            "freshness deadline must not query"
        )

        method_globals = (
            CODEX_QUOTA_APPLICATION._freshness_deadline_elapsed.__globals__
        )
        original_write_state_file = method_globals["write_state_file"]
        method_globals["write_state_file"] = published.append
        try:
            result = application._freshness_deadline_elapsed()
        finally:
            method_globals["write_state_file"] = original_write_state_file

        self.assertEqual(result, False)
        self.assertEqual(application._freshness_deadline_source, 0)
        self.assertIsNone(application._freshness_deadline_at)
        self.assertTrue(application._quota_dirty)
        self.assertEqual(application._dirty_generation, 3)
        self.assertEqual(Loader.calls, ["freshness-deadline"])
        self.assertEqual(published, [stale])
        self.assertEqual(menu_snapshots, [stale])
        self.assertEqual(labels, ["Codex 60%"])


if __name__ == "__main__":
    unittest.main()
