# Contributing

## Code standards

- Support Python 3.11 or newer. Keep the data helper's task-summary path
  standard-library-only and deterministic.
- Keep local paths relative to `Path.home()` or explicit environment
  overrides. Never commit a developer-specific absolute home path.
- Treat the Codex state database and session data as private, read-only input.
  Never log task source text or send it over the network.
- Use only synthetic task text in examples, screenshots, and bug reports.
  Never commit a real Codex database or JSONL session.
- Task summaries are extractive: retain the user's concrete wording and
  language. Do not add a domain-specific classification catalogue or canned
  task descriptions.
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
