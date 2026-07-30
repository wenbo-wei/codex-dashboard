#!/usr/bin/env python3
"""Smoke tests for the user-scoped installer and uninstaller."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "home"
        self.fake_bin = Path(self.temporary.name) / "bin"
        self.command_log = Path(self.temporary.name) / "commands.log"
        self.home.mkdir()
        self.fake_bin.mkdir()
        self.environment = os.environ.copy()
        self.environment.update({
            "HOME": str(self.home),
            "COMMAND_LOG": str(self.command_log),
            "CODEX_DASHBOARD_LIB_DIR": str(
                self.home / ".local/lib/codex-dashboard"
            ),
            "PATH": f"{self.fake_bin}:{os.environ['PATH']}",
        })
        self._fake_command("codex", "exit 0")
        self._fake_command(
            "systemctl",
            'printf "systemctl %s\\n" "$*" >>"$COMMAND_LOG"',
        )
        self._fake_command(
            "gtk-update-icon-cache",
            'printf "icons %s\\n" "$*" >>"$COMMAND_LOG"',
        )
        self._fake_command(
            "gnome-extensions",
            """
            if [ "${1-}" = list ]; then
                exit 0
            fi
            printf "gnome-extensions %s\\n" "$*" >>"$COMMAND_LOG"
            """,
        )

    def _fake_command(self, name: str, body: str) -> None:
        path = self.fake_bin / name
        path.write_text(
            "#!/bin/sh\nset -eu\n" + body.strip() + "\n",
            encoding="utf-8",
        )
        path.chmod(0o755)

    def _run(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(REPO_ROOT / "scripts" / script)],
            cwd=REPO_ROOT,
            env=self.environment,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_install_and_uninstall_touch_only_project_files(self) -> None:
        keep = self.home / ".codex/sessions/keep.jsonl"
        keep.parent.mkdir(parents=True)
        keep.write_text("private session placeholder\n", encoding="utf-8")

        installed = self._run("install.sh")

        helper = self.home / ".local/bin/codex-dashboard-data"
        extension = (
            self.home
            / ".local/share/gnome-shell/extensions"
            / "codex-quota-centre@local/metadata.json"
        )
        icon = (
            self.home
            / ".local/share/icons/hicolor/scalable/apps"
            / "codex-dashboard-symbolic.svg"
        )
        module = (
            self.home
            / ".local/lib/codex-dashboard/codex_app_server.py"
        )
        unit = self.home / ".config/systemd/user/codex-quota.service"
        for path in (helper, extension, icon, module, unit):
            self.assertTrue(path.is_file(), path)
        self.assertTrue(
            helper.stat().st_mode & stat.S_IXUSR,
            "data helper must remain executable",
        )
        self.assertIn("Codex Dashboard files installed", installed.stdout)
        calls = self.command_log.read_text(encoding="utf-8")
        self.assertIn(
            "systemctl --user enable codex-quota.service",
            calls,
        )
        self.assertIn(
            "systemctl --user restart codex-quota.service",
            calls,
        )
        self.assertIn(
            "gnome-extensions enable codex-quota-centre@local",
            calls,
        )
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "import runpy; "
                    f"runpy.run_path({str(helper)!r})"
                ),
            ],
            env=self.environment,
            check=True,
            capture_output=True,
            text=True,
        )

        removed = self._run("uninstall.sh")

        for path in (helper, extension, icon, module, unit):
            self.assertFalse(path.exists(), path)
        self.assertTrue(keep.is_file())
        self.assertIn("Codex Dashboard removed", removed.stdout)


if __name__ == "__main__":
    unittest.main()
