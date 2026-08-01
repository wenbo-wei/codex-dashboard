# Codex Dashboard

A small, local-first GNOME Shell 50 extension that shows:

- the current Codex quota;
- an approximate live Today value plus official 7-day and 90-day token activity;
- five recent terminal tasks, one stable overview per root Codex session.

Each Task Overview prefers a valid explicit English session name and then a
private cached Codex-generated summary. Generated summaries are complete
printable-ASCII English phrases no wider than 48 display columns. Until a
summary is available, the dashboard immediately shows a bounded form of the
first substantive request in its original language, also within 48 display
columns. It adds no ellipsis when the request fits; when shortening is required,
it appends exactly one trailing Unicode ellipsis (`U+2026`) within the same
limit. Model generation runs in the background and never blocks the panel or
data helper.

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
`~/.local/bin/codex` as the same fallback used by the background worker.
If a later installation step fails, the installer restores the prior files,
GNOME extension lists, shared icon cache, and user-service state.

## How it works

- `extension.js` renders the GNOME top-panel button and menu.
- `codex-dashboard-data` reads the local Codex thread index in read-only mode,
  selects recent root tasks, serves explicit names or cached summaries, and
  falls back to the bounded first substantive request without waiting for
  generation. It also reads numeric token counters for the live Today estimate.
  A small aggregate snapshot in the user runtime directory keeps that estimate
  monotonic without storing session text. Task evidence comes only from
  thread-index fields; the dashboard and worker never open session transcripts.
- `codex-dashboard-task-overviews` generates all missing recent summaries in
  one bounded background batch. It uses the saved ChatGPT/Codex login through
  one ephemeral, non-interactive `codex exec` run with read-only sandboxing and
  structured output. This request may consume Codex quota.
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
placeholders are excluded from task rows and generation input. Task identity is
the root thread ID, while the stable generation seed comes from the explicit
name or first substantive request. A sanitized legacy thread-index title is a
generation-only compatibility fallback when both preferred fields are absent;
it is never shown as the deterministic source fallback. Routine follow-ups only
affect ordering. There is no fixed action or subject classifier.

A cache miss starts the static `codex-task-overviews.service` once and returns
the source-language fallback immediately. The worker sends only the bounded
stable seed and an opaque per-batch alias such as `task-1`; real root-thread IDs
are mapped locally and never enter the request. It does not send or open the
full transcript. Successful summaries are reused across process and
desktop-session restarts; failure or invalid output preserves the fallback and
any previous valid cache entry.

The private cache is
`$XDG_CACHE_HOME/codex-dashboard/task-overviews.json` when
`XDG_CACHE_HOME` is set, otherwise
`~/.cache/codex-dashboard/task-overviews.json`. Its directory and file use
private permissions and updates are atomic. Each entry stores only a validated
summary, seed digest, protocol version, and bounded retry or retention metadata,
and the cache retains at most 256 recent entries. Raw task text, prompts,
transcripts, credentials, and raw model responses are never cached or logged.
The estimator reads numeric counters, not message text.

## Repository layout

- `extensions/codex-dashboard@wenbo-wei/` - GNOME Shell interface
- `codex-quota/` - dashboard data, summary worker, and quota publisher
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

Run `make check` for Python, JSON, JavaScript, and shell syntax checks.

## License

MIT
