# Security policy

## Supported versions

Security fixes are provided for the latest release on the `main` branch.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for
`wenbo-wei/codex-dashboard`. Do not open a public issue containing session
content, account details, filesystem paths, or reproduction data that may be
private.

The dashboard reads the local Codex thread index, selected local transcript
events, and the locally installed Codex app server. Transcript text is used
only in memory to choose a bounded overview; it is not cached, logged, or sent
elsewhere by the dashboard. A report should state which data source is involved
without attaching a real Codex database or session log.
