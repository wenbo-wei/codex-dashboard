# Contributing

## Code standards

- Support Python 3.11 or newer. Keep the data helper's task-overview path
  standard-library-only, deterministic, local-only, and read-only.
- Keep local paths relative to `Path.home()` or explicit environment
  overrides. Never commit a developer-specific absolute home path.
- Treat the Codex state database and session data as private, read-only input.
  Never log task source text or send it over the network.
- Use only synthetic task text in examples, screenshots, and bug reports.
  Never commit a real Codex database or JSONL session.
- Render every Task Overview as a complete English-only phrase within 48
  display columns using printable ASCII. Keep the deterministic
  action-and-subject rules concise, preserve conservatively validated technical
  identifiers when useful, and never truncate source text into a misleading
  fragment.
- Keep source files, comments, docstrings, documentation, and explanatory text
  in English. Use Unicode escapes when local matching rules must recognize
  non-English input.
- Task overview generation must stay standard-library-only and must never
  trigger a model request, cache source text, or send conversation text
  elsewhere.
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
