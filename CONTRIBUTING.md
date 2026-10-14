# Contributing

## Code standards

- Support Python 3.11 or newer. Keep task selection and display handling
  standard-library-only and deterministic.
- Keep local paths relative to `Path.home()` or explicit environment overrides.
  Never commit a developer-specific absolute home path.
- Treat Codex state as private, read-only input. Reuse native `name` fields in
  their original language. Only legacy sessions without a name may fall back to
  a sanitized `title`. A missing paginated name remains unavailable.
- Never read transcripts or first-user-message fields for task titles, start a
  model request, maintain a parallel summary cache, or write to Codex state.
- Preserve native wording, including single-word names. Apply only display
  safety and sensitive-data handling. Bound names to 48 display columns and
  append one trailing Unicode ellipsis only when shortening is required.
- Keep the retired worker entry point harmless for stale installations.
- Use only synthetic task text in examples, tests, screenshots, and bug reports.
  Never commit a real Codex database or session contents. Verification must
  never invoke a real model.
- Keep source files, comments, docstrings, documentation, and explanatory text
  in English. Use Unicode escapes for non-English test fixtures.
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
