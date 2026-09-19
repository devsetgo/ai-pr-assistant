# Configuration reference

All inputs the Action accepts, in the order you'd typically reach for them.
For a minimal starter workflow, see the [project README](https://github.com/devsetgo/ai-pr-assistant#quickstart).

## Example: full-capability setup

The workflow below enables the action's optional title generation, label application, and breaking-change detection.

```yaml
name: AI PR Assistant

on:
  pull_request:
    types: [opened, synchronize, reopened, edited]

jobs:
  ai-pr-assistant:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      issues: write

    steps:
      - name: Generate PR description and metadata
        uses: devsetgo/ai-pr-assistant@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          openai_model: gpt-5-mini
          allowed_users: "your-github-username,maintainer-2"
          overwrite_description: true
          generate_title: true
          overwrite_title: true
          enable_labels: true
          label_taxonomy: "bug,feature,enhancement,documentation,dependencies,refactor,test,chore,breaking-change"
          detect_breaking_changes: true
          max_diff_tokens: "8000"
          max_tokens: "2000"
```

## Setup walkthrough

1. Add the OpenAI key to GitHub as a secret. For public OpenAI, use `OPENAI_API_KEY`.
2. Create a workflow under `.github/workflows/` using the example above.
3. Add the minimum GitHub permissions needed for the feature set you want:
   - `pull-requests: write` for descriptions and titles
   - `issues: write` when `enable_labels` is `true`
4. Turn on optional features one at a time if you want to start simple:
   - `generate_title` for title suggestions
   - `overwrite_title` to apply the suggested title
   - `enable_labels` for label generation and label creation
   - `detect_breaking_changes` to warn on likely breaking changes
   - `overwrite_description` to refresh the description on PR updates
5. Adjust `openai_model`, `max_tokens`, and `max_diff_tokens` if your repo has large diffs or you want more concise output.
6. For Azure OpenAI, set `azure_endpoint` and `azure_openai_api_version` instead of using the public OpenAI key flow.

## Required

| Input             | Description                                   |
| ----------------- | ---------------------------------------------- |
| `github_token`    | The GitHub token to use for the Action         |
| `openai_api_key`  | The [OpenAI API key] to use, keep it hidden    |

## Core behavior

| Input                   | Description                                                             | Default                 |
| ----------------------- | ------------------------------------------------------------------------ | ------------------------ |
| `pull_request_id`       | The ID of the pull request to use                                        | Extracted from metadata |
| `allowed_users`         | Comma-separated GitHub usernames this Action will run for; empty runs for everyone | `` (all users) |
| `overwrite_description` | Overwrite the PR description if it already exists (also means the Action runs on every PR update, not just when the description is empty) | `false` |
| `openai_model`          | The [OpenAI model] to use, any model compatible with the chat completions endpoint | `gpt-5-mini` |
| `temperature`           | Higher values make the model more creative (0-2). **Ignored for reasoning models** (`gpt-5*`, `o1*`, `o3*`, `o4*`), which only support the default temperature | `0.6` |
| `max_tokens`            | Maximum number of **output/completion tokens** the model may generate. Reasoning models spend part of this on hidden reasoning tokens before any visible output, so a large diff can need more headroom. | `2000` |

## Diff handling

| Input               | Description                                                                 | Default   |
| -------------------- | ---------------------------------------------------------------------------- | --------- |
| `max_diff_tokens`   | Maximum tokens of PR diff sent to the model, counted with the real tokenizer for `openai_model` (not a character-count guess) | `6000` |
| `exclude_patterns`  | Comma-separated glob patterns for files dropped from the diff before token budgeting — useful for lockfiles, generated code, and binary/asset files that just waste tokens | `*.lock,package-lock.json,yarn.lock,pnpm-lock.yaml,*.min.js,*.svg,*.png,*.jpg,*.jpeg,*.gif,*.ico,dist/*,build/*` |

## Prompt customization

| Input                | Description                                                              | Default |
| --------------------- | --------------------------------------------------------------------------| ------- |
| `sample_prompt`      | Few-shot example prompt given to the model for tone/style. **Classic mode only** — see [Classic vs. structured mode](#classic-vs-structured-mode) below | See `SAMPLE_PROMPT` in `pr_description/llm.py` |
| `sample_response`    | Few-shot example response paired with `sample_prompt`. **Classic mode only** | See `GOOD_SAMPLE_RESPONSE` in `pr_description/llm.py` |
| `completion_prompt`  | The task prompt prepended to the diff content, for both modes            | See `COMPLETION_PROMPT` in `pr_description/llm.py` |

## Optional capabilities (all opt-in, default off)

| Input                      | Description                                                                                          | Default  |
| --------------------------- | ------------------------------------------------------------------------------------------------------ | -------- |
| `generate_title`           | Also ask the model to propose an improved PR title                                                    | `false`  |
| `overwrite_title`          | Actually apply the proposed title (requires `generate_title`); otherwise the suggestion is only printed in the action log | `false`  |
| `enable_labels`            | Auto-label the PR from `label_taxonomy`, creating any missing labels in the repo first                | `false`  |
| `label_taxonomy`           | Comma-separated labels the model may choose from when `enable_labels` is set                          | `bug,feature,enhancement,documentation,dependencies,refactor,test,chore` |
| `detect_breaking_changes`  | Flag likely breaking changes: prepends a note to the description, and (if `enable_labels` is also set) applies a `breaking-change` label | `false`  |

## Azure OpenAI

| Input                       | Description                                     | Default |
| ---------------------------- | ------------------------------------------------- | ------- |
| `azure_endpoint`            | Azure OpenAI resource endpoint. Setting this switches the Action to Azure OpenAI instead of the public OpenAI API | `` |
| `azure_openai_api_version`  | The Azure OpenAI API version to target             | `` |

## Classic vs. structured mode

By default (`generate_title`, `enable_labels`, and `detect_breaking_changes` all
`false`), the Action uses **classic mode**: the original plain-text behavior,
using `sample_prompt`/`sample_response` as a few-shot example and returning
just a description. This is unchanged from earlier versions of this Action.

Turning on any one of `generate_title`, `enable_labels`, or
`detect_breaking_changes` switches to **structured mode**: a single request
constrained by a JSON schema returns the description, title, labels, and
breaking-change assessment together. `sample_prompt`/`sample_response` are not
used in this mode — the schema itself constrains the response shape instead.

In structured mode, the description is a short summary followed by a bulleted
list of key points (grouped under subheadings for changes spanning multiple
areas), and the title is Title Case, prefixed with its category — e.g.
`Enhancement: Add Dark Mode Toggle` or `Bug: Fix Crash on Empty Input`
(`Breaking Change:` instead when `detect_breaking_changes` finds one).

If the API rejects a structured request (for example, an older Azure
deployment or API version without structured-output support), the Action
falls back once to a classic plain-text request rather than failing the run,
and logs a warning.

## Permissions

- Updating the description/title requires `pull-requests: write` (or
  equivalent classic `GITHUB_TOKEN` permissions — see
  [Troubleshooting](TROUBLESHOOTING.md)).
- `enable_labels` additionally requires `issues: write`, since labels live on
  the issue object in the GitHub API, even for pull requests.

## A note on breaking-change detection

`detect_breaking_changes` is judged by the model from the diff content alone,
not by static analysis of your language or framework. Treat it as a helpful
heuristic that can save you a re-read, not a guarantee — it can both miss
real breaking changes and flag things that aren't.

[OpenAI API key]: https://help.openai.com/en/articles/4936850-where-do-i-find-my-secret-api-key
[OpenAI model]: https://platform.openai.com/docs/models
