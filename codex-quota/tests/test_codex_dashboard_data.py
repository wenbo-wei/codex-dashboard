#!/usr/bin/python3
"""Behavior tests for the Codex dashboard data modules."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import re
import runpy
import sqlite3
import tempfile
from typing import NamedTuple
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
os.environ["CODEX_DASHBOARD_LIB_DIR"] = str(REPO_ROOT / "codex-panel")
DATA_HELPER = REPO_ROOT / "codex-quota/codex-dashboard-data"
DATA = runpy.run_path(str(DATA_HELPER))
Availability = DATA["Availability"]
OfficialTokenActivity = DATA["OfficialTokenActivity"]
RecentTaskReader = DATA["RecentTaskReader"]
availability_payload = DATA["availability_payload"]
calendar_months = DATA["_calendar_months"]
normalize_availability = DATA["normalize_availability"]
quota_availability = DATA["quota_availability"]
task_overview = DATA["_task_overview"]
display_width = DATA["_display_width"]


class ThreadRow(NamedTuple):
    thread_id: str
    rollout_path: str
    updated_at: int
    title: str
    first_user_message: str = ""
    name: str | None = None
    archived: int = 0
    thread_source: str | None = "user"
    agent_path: str | None = None


class CalendarMonthsTest(unittest.TestCase):
    def test_calendar_view_is_three_natural_months_with_partial_current(self):
        months = calendar_months(
            {
                "2025-12-31": 1,
                "2026-01-01": 2,
                "2026-02-29": 99,
            },
            dt.date(2026, 2, 3),
        )

        self.assertEqual([month["key"] for month in months], [
            "2025-12",
            "2026-01",
            "2026-02",
        ])
        self.assertEqual(len(months[0]["days"]), 31)
        self.assertEqual(len(months[1]["days"]), 31)
        self.assertEqual(len(months[2]["days"]), 3)
        self.assertEqual(months[2]["days"][-1]["day"], 3)

    def test_calendar_view_includes_leap_day(self):
        months = calendar_months({}, dt.date(2024, 3, 1))
        february = months[1]

        self.assertEqual(february["key"], "2024-02")
        self.assertEqual(len(february["days"]), 29)


class OfficialTokenActivityTest(unittest.TestCase):
    NOW = dt.datetime(2026, 7, 29, 12, tzinfo=dt.timezone.utc)

    def test_daily_buckets_drive_all_activity_totals(self):
        result = OfficialTokenActivity(self.NOW).build({
            "summary": {
                "lifetimeTokens": 900,
                "peakDailyTokens": 400,
            },
            "dailyUsageBuckets": [
                {"startDate": "2026-07-22", "tokens": 50},
                {"startDate": "2026-07-23", "tokens": 100},
                {"startDate": "2026-07-28", "tokens": 400},
                {"startDate": "2026-07-29", "tokens": 25},
            ],
        })

        self.assertEqual(result["today"], 25)
        self.assertEqual(result["seven_days"], 525)
        self.assertEqual(result["lifetime"], 900)
        self.assertEqual(result["peak_daily"], 400)
        self.assertEqual(result["source"], "official_account_usage")
        self.assertTrue(result["current_day_available"])
        self.assertFalse(result["includes_cached_input"])

    def test_missing_current_day_is_truthfully_zero(self):
        result = OfficialTokenActivity(self.NOW).build({
            "summary": {"lifetimeTokens": 400},
            "dailyUsageBuckets": [
                {"startDate": "2026-07-28", "tokens": 400},
            ],
        })

        self.assertEqual(result["today"], 0)
        self.assertEqual(result["seven_days"], 400)
        self.assertFalse(result["current_day_available"])
        self.assertEqual(result["latest_bucket_date"], "2026-07-28")
        self.assertEqual(result["days"][-1], {
            "date": "2026-07-29",
            "tokens": 0,
        })

    def test_invalid_official_response_is_rejected(self):
        with self.assertRaises(ValueError):
            OfficialTokenActivity(self.NOW).build({
                "summary": {},
                "dailyUsageBuckets": None,
            })

    def test_official_usage_uses_shared_app_server_transport(self):
        observed = {}

        def query(
            codex_bin,
            method,
            params=None,
            *,
            timeout_seconds,
            max_line_bytes,
            cancel_event=None,
        ):
            observed.update({
                "codex_bin": str(codex_bin),
                "method": method,
                "params": params,
                "timeout_seconds": timeout_seconds,
                "max_line_bytes": max_line_bytes,
                "cancel_event": cancel_event,
            })
            return {"summary": {}, "dailyUsageBuckets": []}

        result = DATA["_read_official_usage"](
            timeout_seconds=3.0,
            query=query,
        )

        self.assertEqual(
            (result, observed["method"], observed["timeout_seconds"]),
            (
                {"summary": {}, "dailyUsageBuckets": []},
                "account/usage/read",
                3.0,
            ),
        )


class AvailabilityTest(unittest.TestCase):
    def test_unknown_state_normalizes_to_unavailable(self):
        self.assertEqual(
            normalize_availability("unexpected"),
            Availability.UNAVAILABLE,
        )

    def test_ready_quota_ages_to_stale_after_five_minutes(self):
        quota = {
            "limits": [{"remaining_percent": 50}],
            "_stale": False,
            "updated_at_seconds": 1_000,
        }

        self.assertEqual(
            quota_availability(quota, now_seconds=1_300),
            Availability.STALE,
        )

    def test_json_availability_seam_normalizes_every_source(self):
        self.assertEqual(
            availability_payload(
                quota=Availability.READY,
                usage="unexpected",
                tasks=Availability.STALE,
            ),
            {
                "quota": "ready",
                "usage": "unavailable",
                "tasks": "stale",
            },
        )


class ExtensionSourceContractTest(unittest.TestCase):
    def test_helper_failure_invalidates_quota_usage_and_tasks(self):
        source = (
            REPO_ROOT
            / "extensions/codex-quota-centre@local/extension.js"
        ).read_text(encoding="utf-8")
        start = source.index(
            "    _finishLoad(generation, payload, error) {"
        )
        end = source.index("    _applyData(payload) {", start)
        finish_load = source[start:end]

        self.assertRegex(
            finish_load,
            re.compile(
                r"this\._applyQuota\(\s*"
                r"\{limits: \[\]\},\s*"
                r"Availability\.UNAVAILABLE\s*"
                r"\)"
            ),
        )
        self.assertRegex(
            finish_load,
            re.compile(
                r"this\._applyUsage\(\s*"
                r"\{\},\s*"
                r"Availability\.UNAVAILABLE\s*"
                r"\)"
            ),
        )
        self.assertRegex(
            finish_load,
            re.compile(
                r"this\._applyTasks\(\s*"
                r"\[\],\s*"
                r"\{\},\s*"
                r"Availability\.UNAVAILABLE\s*"
                r"\)"
            ),
        )


class TaskOverviewTest(unittest.TestCase):
    def test_preserves_source_language_and_uses_one_sentence(self):
        samples = {
            "检查 Codex 面板任务概述。然后部署。":
                "检查 Codex 面板任务概述。",
            "Review the dashboard titles. Then deploy it.":
                "Review the dashboard titles.",
            "파일 정리": "파일 정리",
            "Revisa los archivos": "Revisa los archivos",
        }

        for source, expected in samples.items():
            with self.subTest(source=source):
                self.assertEqual(task_overview(source), expected)

    def test_cleans_skill_commands_images_and_injected_blocks(self):
        samples = {
            "$code-review: [Image #1] 审查当前修改。不要提交。":
                "审查当前修改。",
            (
                "<skill><name>code-review</name></skill>\n"
                "<environment_context><cwd>/tmp</cwd></environment_context>\n"
                "审查当前修改。不要提交。"
            ): "审查当前修改。",
            (
                "# AGENTS.md instructions\n"
                "<INSTRUCTIONS>internal</INSTRUCTIONS>\n"
                "<environment_context><cwd>/tmp</cwd></environment_context>\n"
                "整理开源仓库。随后测试。"
            ): "整理开源仓库。",
        }

        for source, expected in samples.items():
            with self.subTest(source=source):
                self.assertEqual(task_overview(source), expected)

    def test_injection_only_text_is_not_a_task_overview(self):
        injections = (
            "## Skills\n- code-review",
            "# Handoff\nInternal continuation instructions",
            "<skill>internal instructions</skill>",
            "<environment_context><cwd>/tmp</cwd></environment_context>",
            "<skill>unterminated instructions",
            (
                "Another language model started to solve this problem "
                "and produced a summary of its thinking process."
            ),
        )

        for injection in injections:
            with self.subTest(injection=injection):
                self.assertEqual(task_overview(injection), "")

    def test_literal_injection_term_inside_a_request_is_preserved(self):
        self.assertEqual(
            task_overview(
                "Explain <environment_context> parsing. Then test it."
            ),
            "Explain <environment_context> parsing.",
        )

    def test_overview_is_single_line_and_bounded(self):
        result = task_overview(
            "修复 " + "很长的面板任务概述 " * 20
        )

        self.assertLessEqual(
            display_width(result),
            DATA["TASK_OVERVIEW_COLUMNS"],
        )
        self.assertNotIn("\n", result)
        self.assertTrue(result.endswith("…"))

    def test_long_overview_prefers_a_natural_break(self):
        result = task_overview(
            "调整 Codex Dashboard 的任务标题显示方式，"
            "同时保留后面大量不会完整显示的实现细节"
        )

        self.assertLessEqual(
            display_width(result),
            DATA["TASK_OVERVIEW_COLUMNS"],
        )
        self.assertTrue(result.endswith("，…"))


class RecentTaskReaderTest(unittest.TestCase):
    def database(self, codex_home: Path, rows: list[ThreadRow]) -> None:
        with sqlite3.connect(codex_home / "state_5.sqlite") as connection:
            connection.execute(
                """
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    rollout_path TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    first_user_message TEXT NOT NULL,
                    name TEXT,
                    archived INTEGER NOT NULL,
                    thread_source TEXT,
                    agent_path TEXT
                )
                """
            )
            connection.executemany(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    def read_rows(self, rows: list[ThreadRow]) -> list[dict]:
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory) / "codex"
            codex_home.mkdir()
            self.database(codex_home, rows)
            return RecentTaskReader(codex_home).read()

    def test_name_then_first_user_message_then_title_precedence(self):
        rows = [
            ThreadRow(
                "name",
                "/missing/name.jsonl",
                30,
                "Title fallback",
                "First message fallback",
                "  Explicit dashboard name. Extra sentence.  ",
            ),
            ThreadRow(
                "first",
                "/missing/first.jsonl",
                20,
                "Title fallback",
                "$code-review 检查 Codex 面板。然后部署。",
                " ",
            ),
            ThreadRow(
                "title",
                "/missing/title.jsonl",
                10,
                "Revisa los archivos",
                "<skill>injected instructions</skill>",
            ),
        ]

        tasks = self.read_rows(rows)

        self.assertEqual(
            [task["title"] for task in tasks],
            [
                "Explicit dashboard name.",
                "检查 Codex 面板。",
                "Revisa los archivos",
            ],
        )

    def test_injected_name_falls_through_to_first_message(self):
        tasks = self.read_rows([
            ThreadRow(
                "root",
                "/missing/root.jsonl",
                20,
                "Title fallback",
                "保留真实任务概述。",
                "<skill>internal instructions</skill>",
            ),
        ])

        self.assertEqual(tasks[0]["title"], "保留真实任务概述。")

    def test_rollout_messages_are_not_scanned(self):
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory) / "codex"
            rollout = codex_home / "sessions/root.jsonl"
            rollout.parent.mkdir(parents=True)
            rollout.write_text(
                '{"timestamp":"2026-03-20T01:00:00Z",'
                '"type":"event_msg","payload":{"type":"user_message",'
                '"message":"不要采用这条后续消息"}}\n',
                encoding="utf-8",
            )
            self.database(codex_home, [
                ThreadRow(
                    "root",
                    str(rollout),
                    1_700_000_000_000,
                    "Title fallback",
                    "采用数据库首条任务。",
                ),
            ])

            tasks = RecentTaskReader(codex_home).read()

        self.assertEqual(tasks[0]["title"], "采用数据库首条任务。")
        self.assertEqual(
            tasks[0]["updated_at"],
            "2023-11-14T22:13:20Z",
        )

    def test_filters_non_root_threads_and_keeps_five_recent_rows(self):
        rows = [
            ThreadRow(
                str(index),
                f"/missing/{index}.jsonl",
                100 - index,
                "相同任务" if index < 2 else f"Task {index}",
                "",
                None,
                thread_source=None if index == 0 else "user",
            )
            for index in range(7)
        ]
        rows.extend([
            ThreadRow(
                "archived",
                "/missing/archived.jsonl",
                200,
                "Archived",
                archived=1,
            ),
            ThreadRow(
                "subagent-source",
                "/missing/subagent-source.jsonl",
                190,
                "Subagent source",
                thread_source="subagent",
            ),
            ThreadRow(
                "subagent-path",
                "/missing/subagent-path.jsonl",
                180,
                "Subagent path",
                agent_path="/root/review",
            ),
        ])

        tasks = self.read_rows(rows)

        self.assertEqual(len(tasks), 5)
        self.assertEqual(
            [task["title"] for task in tasks],
            ["相同任务", "相同任务", "Task 2", "Task 3", "Task 4"],
        )
        self.assertNotRegex(
            " ".join(task["title"] for task in tasks),
            r"Task [0-9A-F]{8}:",
        )

    def test_first_message_can_supply_text_when_title_is_empty(self):
        tasks = self.read_rows([
            ThreadRow(
                "root",
                "/missing/root.jsonl",
                20,
                "",
                "数据库中的真实任务。",
            ),
        ])

        self.assertEqual(tasks[0]["title"], "数据库中的真实任务。")

    def test_legacy_schema_without_name_or_first_message_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory) / "codex"
            codex_home.mkdir()
            with sqlite3.connect(codex_home / "state_4.sqlite") as connection:
                connection.execute(
                    """
                    CREATE TABLE threads (
                        id TEXT PRIMARY KEY,
                        updated_at INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        archived INTEGER NOT NULL,
                        thread_source TEXT,
                        agent_path TEXT
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?)",
                    ("legacy", 20, "Legacy task title", 0, "user", None),
                )

            tasks = RecentTaskReader(codex_home).read()

        self.assertEqual(tasks[0]["title"], "Legacy task title")



if __name__ == "__main__":
    unittest.main()
