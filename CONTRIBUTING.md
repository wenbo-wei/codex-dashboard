# Contributing

## Code standards

- Support Python 3.11 or newer. Keep local task selection, fallback, cache, and
  output validation standard-library-only and deterministic. Obtain task
  evidence only from read-only Codex thread-index fields; never open session
  transcripts.
- Keep local paths relative to `Path.home()` or explicit environment
  overrides. Never commit a developer-specific absolute home path.
- Treat the Codex state database and session data as private, read-only input.
  Never log task source text. Only the background summary worker may send the
  bounded stable seed and an opaque per-batch result alias through the installed
  Codex CLI and saved login. Map aliases to real root-thread IDs only after
  validating the batch locally.
- Use only synthetic task text in examples, screenshots, and bug reports.
  Never commit a real Codex database or JSONL session.
- Resolve Task Overview text from a valid explicit English name, a matching
  cached Codex summary, or the bounded first substantive request in its original
  language. Do not add a fixed action or subject classification catalogue.
- Use a sanitized legacy thread-index title only as a generation seed when the
  explicit name and first substantive request are both absent. Never display
  that compatibility field as the deterministic source fallback.
- Accept a generated summary only when it is one complete printable-ASCII
  English phrase within 48 display columns. Keep source-language fallback text
  within the same display budget without translating it, inventing meaning, or
  changing text that already fits. When shortening is required, reserve one
  display column and append exactly one trailing Unicode ellipsis (`U+2026`).
- Put semantic English summarization in the isolated model instruction. Keep
  local validation deterministic and limited to structure, display safety, and
  sensitive-data rejection; do not recreate a fixed vocabulary language
  classifier.
- Keep source files, comments, docstrings, documentation, and explanatory text
  in English. Use Unicode escapes when local matching rules must recognize
  non-English input.
- Keep model work outside the panel and data-helper critical path. Use one
  bounded, ephemeral, non-interactive, read-only `codex exec` batch with
  structured output for missing recent roots.
- Keep the task-summary cache private, bounded, and atomic. Cache only validated
  summaries, seed digests, protocol versions, and bounded retry or retention
  metadata. Never cache raw prompts, task text, transcript text, credentials, or
  unvalidated model output.
- Treat model calls, cache writes, timeouts, invalid output, concurrent misses,
  cooldowns, and source filtering as testable behavior. Tests must use synthetic
  data and a fake runner; verification must never invoke a real model.
- Keep GNOME Shell code compatible with the versions declared in
  `metadata.json`. Follow the existing four-space indentation and semicolon
  style in JavaScript.
- Preserve truthful availability states. Never present estimated data as
  official: approximate Today values use a separate field and a visible `~`;
  missing values remain pending rather than becoming a numeric zero.
- Describe the manual or runtime checks used to verify behaviour changes.

## Before submitting

Run:

```sh
make check
```

Keep commits focused and use an imperative summary such as
`fix: keep terminal task summaries concrete`.
