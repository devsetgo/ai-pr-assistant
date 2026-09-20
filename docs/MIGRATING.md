# History & migrating from `platisd/openai-pr-description`

`ai-pr-assistant` is inspired by the excellent work of
[`platisd/openai-pr-description`](https://github.com/platisd/openai-pr-description)
by Dimitris Platis, and started as a fork of it — the upstream project
appeared abandoned (its last commit predates this one by over a year). It has
since gone in its own direction — new features, an internal restructure,
updated dependencies — with no intent to merge back upstream. It remains
under the MIT license; see [LICENSE](../LICENSE) for the original and this
project's own copyright notices.

## If you're currently using `platisd/openai-pr-description` or an earlier
## `devsetgo/openai-pr-description`

Update your workflow's `uses:` line:

```diff
- uses: platisd/openai-pr-description@master
+ uses: devsetgo/ai-pr-assistant@main
```

(GitHub redirects the renamed `devsetgo/openai-pr-description` repository
automatically, but pointing at the new name directly is recommended.)

No input names were removed or repurposed, so an existing `with:` block
continues to work unchanged. A few defaults did change, described below —
review them even if you don't plan to touch your workflow file.

### Behavior changes worth knowing about

- **The default model now actually works.** The upstream project's last
  commit intended to default to `gpt-5-mini`, but `action.yml` still listed
  `gpt-4o-mini` as the default, so `INPUT_OPENAI_MODEL` was always
  `gpt-4o-mini` in practice regardless of that commit. This project's
  `action.yml` genuinely defaults to `gpt-5-mini`. Separately, requests to
  GPT-5/o-series ("reasoning") models now correctly omit `temperature` and
  use `max_completion_tokens` instead of `max_tokens` — sending the old
  parameters to those models is rejected by the API with a 400 error, which
  is what upstream would hit today if used with a `gpt-5*`/`o1*`/`o3*`
  model.
- **`max_tokens` now defaults to `2000` (was `1000`).** It was always the
  output cap, not a prompt cap — the `action.yml` description previously (and
  misleadingly) called it "prompt tokens." The default was raised because
  reasoning models (`gpt-5*`, `gpt-6*`, `o1*`, `o3*`, `o4*`) spend part of this budget on
  hidden reasoning before writing any visible text, and 1000 could be used up
  entirely on a large diff, leaving an empty description. If you set
  `max_tokens` yourself, nothing changes for you.
- **Descriptions now end with a small attribution footer.** The new
  `attribution` input defaults to `true` and appends
  `Created using devsetgo/ai-pr-assistant with <model>` (in `<sub>` text, below a
  rule) to the generated description. Set `attribution: false` to keep the
  output exactly as it was.
- **Diff truncation is now token-accurate.** Previously the diff sent to the
  model was cut at a hardcoded character count as a rough proxy for tokens.
  It's now measured with the real tokenizer for the selected model and
  controlled by `max_diff_tokens` (default `6000`), so slightly more or less
  of a large diff may be included than before.
- **File pagination is now correct for very large pull requests.** The old
  implementation only fetched up to 300 changed files (10 pages of 30);
  pull requests with more files silently had the rest ignored. Pagination
  now follows GitHub's own `Link` header, with no fixed cap.

### New, opt-in only

Everything else added here — `generate_title`, `enable_labels`,
`detect_breaking_changes`, `exclude_patterns`, and `provider: anthropic` (Claude
via the direct Anthropic API, with `anthropic_api_key` and `anthropic_model`) —
defaults to off/unchanged. `provider` defaults to `openai`. One related detail:
`openai_api_key` is no longer marked `required` in `action.yml`, since which key
is needed depends on the provider; the Action instead fails early with a clear
message if the selected provider's key is missing.
A workflow that doesn't set any of these keeps the plain-description
behavior it had before (apart from the attribution footer above). See [CONFIGURATION.md](CONFIGURATION.md) for what
each one does.
