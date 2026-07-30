# Changelog

## 1.4.0 - 2026-07-30

- Replace raw first-request task titles with fixed-length English-only
  action-and-subject overviews derived locally from the conversation.
- Keep every overview within 48 display columns and remove the UI's second
  ellipsis so the complete phrase remains visible.
- Validate transcript identity and preserve local-only, zero-extra-token
  behaviour with a safe English fallback.

## 1.3.0 - 2026-07-30

- Replace the perpetually pending Today label with a clearly marked local
  estimate, calibrated against the most recent comparable official day.
- Keep the live estimate monotonic with a small numeric-only runtime snapshot.
- Keep official current-day values authoritative and leave 7-day, 90-day, and
  calendar activity fully official.
- Optically balance the upper and lower whitespace in the Token activity card.

## 1.2.0 - 2026-07-30

- Show a pending Today value and calendar state when the official current-day
  bucket has not arrived, while preserving explicit zeroes and known totals.
- Queue clean first installs for the next login without a second installer run,
  while retaining the safe staged flow whenever a legacy UUID is installed.
- Respect XDG data/config locations and roll back owned files, the shared icon
  cache, extension settings, and prior systemd state after a late failure.
- Validate absolute home/XDG paths and declared Python, GNOME Shell, GJS, and
  systemd prerequisites before copying installation files.
- Retire queued UUIDs during uninstall even before the current Shell discovers
  them.
- Keep lightweight Python, JSON, JavaScript, and shell syntax checks in
  `make check`.

## 1.1.0 - 2026-07-30

- Replace the legacy local extension UUID with `codex-dashboard@wenbo-wei` and
  migrate installed copies without leaving a second panel entry.
- Remove the bundled test suite and keep a lightweight syntax check.
- Shorten the README and clarify the repository architecture.

## 1.0.0 - 2026-07-30

- Rename the extension to Codex Dashboard.
- Replace fixed task-category phrases with one-sentence, per-session task
  summaries that preserve the user's wording and language.
- Package the extension, helper, quota publisher, tests, installer, and
  documentation as a portable open-source repository.
