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

- Treat each recent root Codex session as one terminal task.
- Show at most five recent, unarchived root sessions, newest first.
- Represent every task with one complete printable-ASCII English
  action-and-subject phrase no wider than 48 display columns.
- Prefer a concise English user-assigned session name when Codex provides one
  and it passes the same content, width, and completeness validation as a
  generated overview. Otherwise, use that name as primary classification
  evidence without displaying unverified source text.
- Anchor the action in the explicit name or initial request so routine
  follow-ups do not rename the task.
- Use substantive user turns available within the bounded transcript scan to
  confirm or fill a missing subject. Prefer a conservatively validated,
  specific ASCII technical identifier when it is more informative than a broad
  domain, and otherwise use the deterministic English subject rules.
- Prefer the assistant's opening task restatement as supporting semantic
  evidence; use the latest completed answer only when no trustworthy opening
  restatement exists.
- Use a stable English generic phrase only when no more specific subject can be
  derived. Never expose a non-English fallback or a truncated source fragment.
- Ignore subagents, generic acknowledgements, injected instruction envelopes,
  image placeholders, bare skill-command prefixes, and unrelated workflow
  status.
- Validate that every transcript belongs to the indexed root thread, and read
  the local thread index and transcript without modifying either one.
- Task overviews must not trigger another model request, consume tokens, cache
  source text, or send session text elsewhere.
- Render the bounded phrase as a complete single line. Neither the generated
  value nor the UI may add a trailing ellipsis to valid task data.

## Open-source delivery

- Provide a self-contained Git repository named `codex-dashboard`.
- Include an OSI-approved license, installation and removal instructions,
  contribution guidance, security reporting guidance, syntax checks, and CI.
- Do not include credentials, personal absolute paths, session contents,
  generated runtime state, or unrelated Workspace extension code.
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
