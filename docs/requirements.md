# Codex Dashboard requirements

This document records the current product constraints.

## Product

- The GNOME Shell extension is named **Codex Dashboard**.
- Its UUID is `codex-dashboard@wenbo-wei`; installation migrates the legacy
  local UUID so only one dashboard remains enabled.
- The dashboard shows the live Codex quota, official historical token activity,
  and a clearly marked approximate Today value while the official current-day
  bucket is pending.
- Estimate Today from read-only numeric counters in the local thread index.
  Seed recent totals by thread start day, then use a small aggregate runtime
  snapshot to count subsequent counter growth on every thread. Never read
  session message text for this estimate.
- Keep the estimate monotonic within a local day and calibrate it against the
  most recent comparable official day.
- Keep the estimate separate from the official value and prefix it with `~`.
  An official current-day bucket, including an explicit zero, always wins.
  Known 7-day and 90-day totals and the calendar remain fully official.
- If neither an official current-day bucket nor a valid local estimate is
  available, Today remains pending rather than becoming a misleading zero.
- Keep the Token activity title's upper optical gap equal to the lower gap
  beneath the final value without changing the overview card's geometry.

## Task overview

- Show at most five recent, unarchived root Codex sessions, newest first.
- Use Codex thread identity and recency, excluding subagent sessions.
- Reuse native `name` values in their original language, including single-word
  names. Follow Codex renames on the next refresh; do not maintain separate names.
- For legacy sessions without a native name, allow a sanitized `title` fallback.
  For paginated sessions, `title` is search metadata and must not replace a
  missing name. Show an honest unavailable placeholder until Codex names it.
- Keep titles single-line and within 48 display columns. Preserve text that
  fits, apart from display safety and sensitive-data handling. Append one
  trailing Unicode ellipsis when shortening is required.
- Read task metadata only through the local read-only thread index. Never
  open transcripts or read first-user-message fields for task overviews.
- Never start a model, translate or regenerate a summary, read/write a parallel
  summary cache, or mutate Codex sessions while rendering the dashboard.
- Retain the old worker command and unit as harmless compatibility no-ops;
  installation stops any running old worker. Remove cache monitoring from the UI.
- A missing or unavailable index must preserve truthful availability reporting.

## Open-source delivery

- Provide a self-contained Git repository named `codex-dashboard`.
- Include an OSI-approved license, installation and removal instructions,
  contribution guidance, security reporting guidance, syntax checks, and CI.
- Do not include credentials, personal absolute paths, session contents,
  generated cache state, or unrelated Workspace extension code.
- Installation must work for a normal user home directory and must not require
  source edits.
- Before copying files, installation validates absolute home/XDG paths,
  `/usr/bin/python3` 3.11+, GNOME Shell 50, GJS, and user-systemd tooling.
- Extension, icon, and user-unit paths respect `XDG_DATA_HOME` and
  `XDG_CONFIG_HOME`.
- A clean install whose current Shell has not discovered the extension queues
  the new UUID for the next login without requiring a second installer run.
- If the legacy UUID is still installed and the new UUID is not live-discovered,
  preserve the legacy installation and require the safe staged migration rather
  than queueing both UUIDs for the next login.
- Deployment must preserve the user's quota/token data sources and avoid
  restarting GNOME Shell or opening foreground UI.
- If installation fails after deployment begins, restore every installer-owned
  target's previous contents and mode, preserve unknown extension files,
  restore the exact enabled and disabled extension lists, and restore the
  prior shared icon cache and systemd enabled/active state. A failed clean
  installation leaves no owned files, icon cache, or service enablement
  behind.
- Uninstall must retire queued extension UUIDs even when the current Shell has
  not discovered them.
