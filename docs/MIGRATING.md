# Fork history & migrating from `platisd/openai-pr-description`

`ai-pr-assistant` is a **hard fork** of
[`platisd/openai-pr-description`](https://github.com/platisd/openai-pr-description)
by Dimitris Platis. It was forked because the upstream project appeared
abandoned (its last commit predates this fork by over a year), and this fork
has since diverged enough — new features, an internal restructure, updated
dependencies — that there is no intent to merge back upstream. It remains
under the MIT license; see [LICENSE](../LICENSE) for the original and
fork copyright notices.

## If you're currently using `platisd/openai-pr-description` or an earlier
## `devsetgo/openai-pr-description`

Update your workflow's `uses:` line:

```diff
- uses: platisd/openai-pr-description@master
+ uses: devsetgo/ai-pr-assistant@master
```

(GitHub redirects the renamed `devsetgo/openai-pr-description` repository
automatically, but pointing at the new name directly is recommended.)

No input names were removed or repurposed, so an existing `with:` block
continues to work unchanged. Two defaults did change, described below —
both are fixes, not new opt-in behavior, so review them even if you don't
plan to touch your workflow file.

### Behavior changes worth knowing about

- **The default model now actually works.** The upstream project's last
  commit intended to default to `gpt-5-mini`, but `action.yml` still listed
  `gpt-4o-mini` as the default, so `INPUT_OPENAI_MODEL` was always
  `gpt-4o-mini` in practice regardless of that commit. This fork's
  `action.yml` genuinely defaults to `gpt-5-mini`. Separately, requests to
  GPT-5/o-series ("reasoning") models now correctly omit `temperature` and
  use `max_completion_tokens` instead of `max_tokens` — sending the old
  parameters to those models is rejected by the API with a 400 error, which
  is what upstream would hit today if used with a `gpt-5*`/`o1*`/`o3*`
  model.
- **`max_tokens` was always the output cap, not a prompt cap** — the
  `action.yml` description previously (and misleadingly) called it "prompt
  tokens." The behavior is unchanged; only the documentation was wrong.
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

Everything else added in this fork — `generate_title`, `enable_labels`,
`detect_breaking_changes`, `exclude_patterns` — defaults to off/unchanged.
A workflow that doesn't set any of these keeps the exact plain-description
behavior it had before. See [CONFIGURATION.md](CONFIGURATION.md) for what
each one does.
