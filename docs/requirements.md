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
- Use `thread_id` as stable task identity and recency only for ordering.
- Resolve each overview in this order: a valid explicit English session name,
  a matching cached Codex-generated summary, and the bounded first substantive
  request in its original language. Use an honest unavailable fallback only
  when none of those sources is usable.
- Prefer a concise English user-assigned session name when Codex provides one
  and it passes the same content, width, and completeness validation as a
  generated overview.
- Derive the generation seed from the sanitized explicit name or first
  substantive request. Only when both are absent, use a sanitized legacy
  thread-index title as a generation-only compatibility seed; never display it
  as the deterministic source fallback. Routine follow-ups and recency changes
  must not rename the task or trigger another successful generation for the
  same stable seed.
- Generate missing recent-root summaries together in one bounded background
  batch. The panel and data helper must never wait for model execution.
- Use the saved ChatGPT/Codex login through one ephemeral, non-interactive
  `codex exec` run with read-only sandboxing and structured output. Generation
  may consume Codex quota.
- Accept generated output only when it is one complete printable-ASCII English
  phrase no wider than 48 display columns, with no Markdown, newline, ellipsis,
  or sensitive material.
- Preserve the first substantive request's source language in the bounded
  fallback. If it already fits within 48 display columns, leave it unchanged.
  If shortening is required, reserve one display column and append exactly one
  trailing Unicode ellipsis (`U+2026`). Do not translate it or invent meaning
  with an action or subject classification catalogue.
- Ignore subagents, generic acknowledgements, injected instruction envelopes,
  image placeholders, bare skill-command prefixes, and unrelated workflow
  status.
- Obtain task evidence only from read-only fields in the local thread index.
  Never open a session transcript.
- Send only the bounded stable seed and an opaque per-batch result alias. Map
  that alias to the real root-thread ID locally; never place the real ID in the
  request. Never send the full transcript, injected text, environment data,
  handoff content, subagent content, or assistant output.
- Keep the summary cache private, persistent across desktop sessions, bounded,
  and atomically replaced, retaining at most 256 recent entries. Each entry may
  contain only its validated summary, seed digest, protocol version, and bounded
  retry or retention metadata, never raw task or transcript text.
- A cache or generation failure must preserve the immediate fallback and any
  previous valid cached summary. Concurrent misses must start at most one
  worker, and retries must observe a cooldown.
- Render generated values as complete single lines without adding a trailing
  ellipsis. The UI must also safely accept the bounded source-language fallback,
  including its single trailing `U+2026` when the source must be shortened.

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
