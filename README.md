# Codex Dashboard

Codex Dashboard is a GNOME Shell top-panel extension for a compact view of:

- the current Codex quota window;
- official 7-day and 90-day token activity;
- five recent terminal tasks, one concise sentence per root Codex session.

Task rows keep the user's original language and concrete wording. The helper
does not classify tasks into fixed categories and does not call a model to
generate titles.

> Codex Dashboard is an unofficial community project. It is not affiliated
> with or endorsed by OpenAI. Codex is a trademark of OpenAI.

## Requirements

- GNOME Shell 50
- Python 3.11 or newer
- Codex CLI available on `PATH`
- PyGObject and dbus-python
- `systemd --user`

On Ubuntu, the runtime dependencies are:

```sh
sudo apt install python3-dbus python3-gi
```

## Install

```sh
git clone https://github.com/wenbo-wei/codex-dashboard.git
cd codex-dashboard
make check
./scripts/install.sh
```

The installer copies only project-owned files under `~/.local` and installs
the user service at `~/.config/systemd/user/codex-quota.service`. It does not
restart GNOME Shell. On an upgrade, sign out and back in when convenient so
GNOME Shell loads the new JavaScript.

The extension keeps the UUID `codex-quota-centre@local` for compatibility with
existing local installations, while its visible name is **Codex Dashboard**.

## How task overviews work

Codex keeps a local thread index under `CODEX_HOME` (normally `~/.codex`).
Codex Dashboard opens the newest index in SQLite read-only mode, excludes
archived sessions and subagents, and treats each remaining root session as one
terminal task.

For each row it prefers a user-assigned Codex session name. Otherwise it
extracts one display sentence from that session's stable initial task title:
skill prefixes and image placeholders are removed, whitespace is normalized,
and long text is clipped at a natural sentence or clause boundary. There is no
task-domain dictionary, translation, or model-generated replacement.

## Data and privacy

- The thread index is opened read-only. Codex Dashboard never changes or logs
  session titles.
- Task source text stays on the machine and is not sent over the network.
- Task summaries are visible in the panel menu; treat screenshots and screen
  sharing as potentially sensitive.
- Token activity comes from Codex's official `account/usage/read` app-server
  method.
- Quota state comes from Codex's `account/rateLimits/read` method and is
  published locally to the user's runtime directory.
- Missing official daily data is shown as pending rather than as a real zero.

Environment overrides supported by the Python components include `CODEX_HOME`,
`CODEX_BIN`, `XDG_RUNTIME_DIR`, and `CODEX_DASHBOARD_LIB_DIR`.

Codex's app-server protocol and local thread-index schema may evolve with
future Codex CLI releases. Compatibility fixes may therefore be needed after
major CLI updates.

## Development

Run the complete test and syntax suite:

```sh
make check
```

The main components are:

- `extensions/codex-quota-centre@local/` — GNOME Shell UI
- `codex-quota/codex-dashboard-data` — read-only dashboard data helper
- `codex-quota/codex-quota` — event-driven quota state publisher
- `codex-panel/` — shared Codex app-server and quota modules
- `scripts/` — user-scoped install and uninstall scripts

See [CONTRIBUTING.md](CONTRIBUTING.md) for code standards and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.

## Uninstall

```sh
./scripts/uninstall.sh
```

The uninstaller removes only the files installed by this project. It does not
delete Codex sessions, account data, configuration, or the Codex CLI.

## License

MIT
