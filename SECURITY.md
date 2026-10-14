# Security policy

## Supported versions

Security fixes are provided for the latest release on the `main` branch.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for
`wenbo-wei/codex-dashboard`. Do not open a public issue containing session
content, account details, filesystem paths, or reproduction data that may be
private.

The dashboard reads native task names and legacy title metadata from the local
Codex thread index through a read-only connection. Task Overview never opens
session transcripts, reads first-user-message fields, sends task text to a
model, starts a Codex turn, or modifies Codex state. Names retain their original
language with local display safety and sensitive-data handling.

There is no active summary worker or summary cache. The old worker command and
systemd unit remain harmless compatibility no-ops. Existing summary caches are
ignored and removed by uninstall. Neither task text nor credentials should be
logged or included in bug reports. Quota and historical usage requests remain
separate from task names and continue through the installed Codex backend.

A report should identify the affected data source or display operation without
attaching a real database, session log, credential, or task title.
