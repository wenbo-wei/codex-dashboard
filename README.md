# Codex Dashboard

A small, local-first GNOME Shell 50 extension that shows:

- the current Codex quota;
- an approximate live Today value plus official 7-day and 90-day token activity;
- five recent terminal tasks, one stable overview per root Codex session.

Task Overview reuses Codex's saved session names, including Chinese and other
languages. It does not generate, translate, or cache a second summary, start a
Codex task, or consume model quota for task titles. Names are displayed on one
line within 48 display columns, with one trailing ellipsis when needed.

> This is an unofficial community project and is not affiliated with OpenAI.

## Install

Requirements: GNOME Shell 50, `/usr/bin/python3` 3.11+, Codex CLI,
`systemd --user`, GJS, PyGObject, and dbus-python.

```sh
sudo apt install gjs python3-dbus python3-gi
git clone https://github.com/wenbo-wei/codex-dashboard.git
cd codex-dashboard
./scripts/install.sh
```

The extension UUID is `codex-dashboard@wenbo-wei`. The installer automatically
migrates the old local UUID if it is present. On a clean installation, a Shell
session that has not discovered the new UUID yet is queued to enable it at the
next login; the installer does not need to be rerun. When an old UUID is still
installed, it is preserved until the new UUID is live-discovered; the installer
then asks you to sign in again and rerun it to finish that safe migration.
Extension, icon, and user-unit files respect `XDG_DATA_HOME` and
`XDG_CONFIG_HOME` when those variables are set. The installer validates Codex
through the systemd user manager's `CODEX_BIN` or `PATH`, with
`~/.local/bin/codex` as the same fallback used by the quota backend.
If a later installation step fails, the installer restores the prior files,
GNOME extension lists, shared icon cache, and user-service state.

## How it works

- `extension.js` renders the GNOME top-panel button and menu.
- `codex-dashboard-data` reads the local Codex thread index in read-only mode
  and displays the five most recent unarchived root sessions using their native
  `name`. A legacy session without a name can use its sanitized `title`; a
  current paginated session without a name shows **Task overview unavailable**
  until Codex supplies one. Refreshing the menu picks up native name changes.
  The helper also reads numeric token counters for the live Today estimate.
  A small aggregate runtime snapshot keeps that estimate monotonic without
  storing session text.
- `codex-dashboard-task-overviews` and its systemd unit are compatibility no-ops
  for older installations. The installer stops any old worker, and the dashboard
  never requests a worker start.
- `codex-quota` publishes live quota state for the extension.
- Official historical token and quota data come from the locally installed
  Codex CLI app-server.

If the official service has not published today's bucket yet, the dashboard
seeds numeric token totals from the local thread index by thread start day,
then counts aggregate counter growth and calibrates it against the most recent
comparable settled day. Today is prefixed with `~` so the result cannot be
mistaken for an official value. An official current-day value, including `0`,
always takes precedence. The 7-day and 90-day totals and calendar remain
official; Today falls back to **Pending** if no safe local estimate is
available.

Subagents and archived sessions are excluded. Task identity and recency come
from Codex's thread index. Titles receive only local display/privacy handling;
legacy title fallbacks also filter injected instruction text. No task path
reads transcripts, first-user-message fields, or the retired summary cache.
Existing dashboard-owned summary caches are ignored and removed by uninstall.
The numeric Today estimator remains separate from task titles.

## Repository layout

- `extensions/codex-dashboard@wenbo-wei/` - GNOME Shell interface
- `codex-quota/` - dashboard data, retired worker shim, and quota publisher
- `backend/` - shared task-overview, Codex app-server, and quota modules
- `scripts/` and `systemd/` - installation and background units

## Update or remove

```sh
git pull --ff-only
./scripts/install.sh
```

GNOME Shell may keep JavaScript cached during later upgrades. If necessary,
sign out and back in when convenient.

```sh
./scripts/uninstall.sh
```

Uninstalling removes the dashboard-owned task-summary cache. It does not delete
Codex sessions, account data, configuration, or the Codex CLI. It also retires
a queued UUID that the current Shell has not discovered yet.

Run `make check` for syntax checks and native task-name regression tests.

## License

MIT
