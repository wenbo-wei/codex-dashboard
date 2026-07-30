# Codex Dashboard v1 requirements

This document records the user request that defines the first public release.

## Product

- The GNOME Shell extension is named **Codex Dashboard**.
- It keeps the existing `codex-quota-centre@local` UUID so an installed copy
  upgrades in place instead of appearing as a second extension.
- The dashboard continues to show the live Codex quota and official token
  activity already provided by the installed version.

## Task overview

- Treat each recent root Codex session as one terminal task.
- Show at most five recent, unarchived root sessions, newest first.
- Represent every task with one concise sentence derived from that session's
  own user-provided title.
- Prefer a user-assigned session name when Codex provides one.
- Keep the task's original language and concrete wording.
- Do not map task text to a fixed catalogue of domains, actions, or canned
  replacement sentences.
- Ignore subagents, injected instruction envelopes, image placeholders, and
  bare skill-command prefixes.
- Read the local Codex thread index without modifying it. Task summaries must
  not trigger a model request, consume tokens, or send session text elsewhere.

## Open-source delivery

- Provide a self-contained Git repository named `codex-dashboard`.
- Include an OSI-approved license, installation and removal instructions,
  contribution guidance, security reporting guidance, automated tests, and CI.
- Do not include credentials, personal absolute paths, session contents,
  generated runtime state, or unrelated Workspace extension code.
- Installation must work for a normal user home directory and must not require
  source edits.
- Deployment must preserve the user's quota/token data sources and avoid
  restarting GNOME Shell or opening foreground UI.

