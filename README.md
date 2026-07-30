# Codex Dashboard

A small, local-first GNOME Shell 50 extension that shows:

- the current Codex quota;
- official 7-day and 90-day token activity;
- five recent terminal tasks, one concise sentence per root Codex session.

Task titles keep the user's language and wording. There is no fixed task
catalogue, translation, or model-generated summary.

> This is an unofficial community project and is not affiliated with OpenAI.

## Install

Requirements: GNOME Shell 50, Python 3.11+, Codex CLI, `systemd --user`,
PyGObject, and dbus-python.

```sh
sudo apt install python3-dbus python3-gi
git clone https://github.com/wenbo-wei/codex-dashboard.git
cd codex-dashboard
./scripts/install.sh
```

The extension UUID is `codex-dashboard@wenbo-wei`. The installer automatically
migrates the old local UUID if it is present. If the current Shell session has
not discovered the new UUID yet, the old extension is preserved and the
installer asks you to sign in again before rerunning it.

## How it works

- `extension.js` renders the GNOME top-panel button and menu.
- `codex-dashboard-data` reads the local Codex thread index in SQLite
  read-only mode and turns each recent root session into one task sentence.
- `codex-quota` publishes live quota state for the extension.
- Official token and quota data come from the locally installed Codex CLI
  app-server.

Subagents, archived sessions, injected instructions, skill prefixes, and image
placeholders are excluded from task rows. No session text is uploaded by this
project and no model request is made to generate task titles.

## Repository layout

- `extensions/codex-dashboard@wenbo-wei/` — GNOME Shell interface
- `codex-quota/` — dashboard data and quota publisher
- `codex-panel/` — shared Python modules
- `scripts/` and `systemd/` — installation and background service

## Update or remove

```sh
git pull
./scripts/install.sh
```

GNOME Shell may keep JavaScript cached during later upgrades. If necessary,
sign out and back in when convenient.

```sh
./scripts/uninstall.sh
```

Uninstalling does not delete Codex sessions, account data, configuration, or
the Codex CLI.

For a basic source syntax check, run `make check`.

## License

MIT
