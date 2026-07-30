# Codex Dashboard

A small, local-first GNOME Shell 50 extension that shows:

- the current Codex quota;
- an approximate live Today value plus official 7-day and 90-day token activity;
- five recent terminal tasks, one concise sentence per root Codex session.

Task titles keep the user's language and wording. There is no fixed task
catalogue, translation, or model-generated summary.

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
`XDG_CONFIG_HOME` when those variables are set.
If a later installation step fails, the installer restores the prior files,
GNOME extension lists, shared icon cache, and user-service state.

## How it works

- `extension.js` renders the GNOME top-panel button and menu.
- `codex-dashboard-data` reads the local Codex thread index in SQLite
  read-only mode, turns each recent root session into one task sentence, and
  reads numeric token counters for the live Today estimate. A small aggregate
  snapshot in the user runtime directory keeps that estimate monotonic without
  storing session text.
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

Subagents, archived sessions, injected instructions, skill prefixes, and image
placeholders are excluded from task rows. The estimator reads numeric counters,
not message text. No session text is uploaded by this project and no model
request is made to generate task titles.

## Repository layout

- `extensions/codex-dashboard@wenbo-wei/` — GNOME Shell interface
- `codex-quota/` — dashboard data and quota publisher
- `backend/` — Codex app-server and quota backend modules
- `scripts/` and `systemd/` — installation and background service

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

Uninstalling does not delete Codex sessions, account data, configuration, or
the Codex CLI. It also retires a queued UUID that the current Shell has not
discovered yet.

Run `make check` for Python, JSON, JavaScript, and shell syntax checks.

## License

MIT
