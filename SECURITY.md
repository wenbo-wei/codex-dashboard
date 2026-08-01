# Security policy

## Supported versions

Security fixes are provided for the latest release on the `main` branch.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for
`wenbo-wei/codex-dashboard`. Do not open a public issue containing session
content, account details, filesystem paths, or reproduction data that may be
private.

The dashboard obtains task evidence only from read-only fields in the local
Codex thread index, including the explicit name, first substantive root request,
and a legacy title used only as a last-resort generation seed. The dashboard and
worker never open session transcripts. On a summary cache miss, a background
worker sends only the bounded, sanitized stable task seed and an opaque
per-batch alias to Codex through the locally installed CLI and the user's saved
ChatGPT/Codex login. Real root-thread IDs are mapped locally and never enter the
request. This request may consume Codex quota. The full transcript, injected
instructions, environment content, handoffs, subagent content, and assistant
output are not sent.

The worker runs one bounded batch in an ephemeral working directory with
read-only sandboxing, non-interactive execution, structured output validation,
and a fixed timeout. Credentials remain under Codex's ownership and are not
copied into dashboard files. Failure, timeout, invalid output, or unavailable
authentication leaves the source-language fallback and any previous valid
summary intact.

The private summary cache is stored under the user's XDG cache directory and is
atomically replaced. Its directory and file use private permissions. Each entry
stores a validated summary, seed digest, protocol version, and bounded retry or
retention metadata. It does not store raw task text, transcript text, prompts,
credentials, or raw model responses. Neither source text nor generated
sensitive material may appear in logs.

A report should state which data source, worker stage, or cache operation is
involved without attaching a real Codex database, session log, cache, prompt,
or generated summary.
