"""Regression checks for native Codex names, using synthetic state only."""

from contextlib import contextmanager
import importlib.machinery
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import task_overviews as tasks

loader = importlib.machinery.SourceFileLoader(
    'dashboard_data', str(ROOT / 'codex-quota/codex-dashboard-data')
)
spec = importlib.util.spec_from_loader(loader.name, loader)
data = importlib.util.module_from_spec(spec)
loader.exec_module(data)


class NativeTasksTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.database = self.home / 'state_5.sqlite'
        with sqlite3.connect(self.database) as db:
            db.execute('''CREATE TABLE threads (
                id TEXT PRIMARY KEY, name TEXT, title TEXT,
                first_user_message TEXT, history_mode TEXT,
                recency_at_ms INTEGER, archived INTEGER,
                thread_source TEXT, agent_path TEXT, source TEXT
            )''')

    def add(self, number=1, name='Native name', title='Legacy task title',
            history='paginated', archived=0, thread_source='user',
            agent_path=None, source='cli'):
        identifier = f'00000000-0000-4000-8000-{number:012d}'
        with sqlite3.connect(self.database) as db:
            db.execute('INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (
                identifier, name, title, 'Do not read or summarize this message',
                history, 1_800_000_000_000 + number, archived,
                thread_source, agent_path, source,
            ))
        return identifier

    def titles(self):
        return [item['title'] for item in tasks.recent_task_payload(self.home)]

    def test_native_names_keep_language_and_single_words(self):
        names = ['\u9879\u76ee\u6574\u7406', 'Dashboard', 'OK', 'Fix the UI']
        for number, name in enumerate(names, 1):
            self.add(number, name)
        self.assertEqual(self.titles(), list(reversed(names)))

    def test_rename_is_visible_on_next_refresh(self):
        identifier = self.add(name='Original native name')
        self.assertEqual(self.titles(), ['Original native name'])
        with sqlite3.connect(self.database) as db:
            db.execute('UPDATE threads SET name = ? WHERE id = ?',
                       ('Renamed in Codex', identifier))
        self.assertEqual(self.titles(), ['Renamed in Codex'])

    def test_pending_paginated_name_does_not_use_search_title(self):
        self.add(name=None, title='Derived search metadata')
        self.assertEqual(self.titles(), [tasks.UNAVAILABLE_OVERVIEW])

    def test_legacy_schema_uses_native_title(self):
        with sqlite3.connect(self.database) as db:
            db.execute('DROP TABLE threads')
            db.execute('CREATE TABLE threads (id TEXT, title TEXT, updated_at INTEGER)')
            db.execute('INSERT INTO threads VALUES (?, ?, ?)', (
                '00000000-0000-4000-8000-000000000001',
                'Legacy saved title', 1_800_000_000,
            ))
        self.assertEqual(self.titles(), ['Legacy saved title'])

    def test_root_filter_and_recent_limit(self):
        for number in range(1, 8):
            self.add(number, f'Native task {number}')
        self.add(8, archived=1)
        self.add(9, thread_source='subagent')
        self.add(10, agent_path='/root/child')
        self.add(11, source='{"subagent":{"spawn":{}}}')
        self.assertEqual(self.titles(), [f'Native task {n}' for n in range(7, 2, -1)])

    def test_display_width_controls_and_credentials(self):
        name = '\u6574\u7406' * 40
        title = tasks.native_name(name)
        self.assertLessEqual(tasks._display_width(title), 48)
        self.assertTrue(title.endswith('\u2026'))
        self.assertEqual(tasks.native_name('Hello\nworld\u202e'), 'Hello world')
        secret = 'sk-' + 'a' * 40
        self.assertNotIn(secret, tasks.native_name('Rotate ' + secret))

    def test_refresh_cannot_read_messages_write_state_or_start_work(self):
        self.add()
        before = self.database.read_bytes()
        retired_cache = self.home / 'task-overviews.json'
        retired_cache.write_text('{invalid cache: must never be read}')
        real_open = tasks.open_thread_index

        @contextmanager
        def restricted_index(home):
            with real_open(home) as db:
                def authorize(action, table, column, *_):
                    if action == sqlite3.SQLITE_READ and column == 'first_user_message':
                        return sqlite3.SQLITE_DENY
                    if action in (sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_INSERT,
                                  sqlite3.SQLITE_DELETE):
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                db.set_authorizer(authorize)
                yield db

        with patch.object(tasks, 'open_thread_index', restricted_index), \
                patch.object(data, '_codex_home', return_value=self.home), \
                patch.object(subprocess, 'Popen', side_effect=AssertionError('Started work')):
            for _ in range(2):
                payload, counts = data._recent_tasks()
                self.assertEqual(payload[0]['title'], 'Native name')
                self.assertEqual(counts, {'recent': 1})
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(retired_cache.read_text(), '{invalid cache: must never be read}')

    def test_retired_worker_is_noop_even_without_codex(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'codex-quota/codex-dashboard-task-overviews')],
            env={'PATH': '', 'CODEX_HOME': str(self.home)},
            capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout + result.stderr, b'')


if __name__ == '__main__':
    unittest.main()
