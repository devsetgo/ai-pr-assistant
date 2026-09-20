# Troubleshooting

### `403` error when updating the PR description or title

This means the GitHub Action's token isn't allowed to write to the
repository. Grant the necessary permissions to the `GITHUB_TOKEN` secret at
`<your_repo_url>/settings/actions`, under **Workflow permissions** — select
**Read and write permissions**.

### Labels aren't being applied even though `enable_labels: true`

Labeling needs `issues: write` in addition to `pull-requests: write` (labels
live on the issue object in the GitHub API, even for pull requests). If your
workflow sets an explicit `permissions:` block rather than relying on the
repository-wide default, add it there:

```yaml
permissions:
  pull-requests: write
  issues: write
```

### The Action fails with a 400 error from OpenAI mentioning `temperature` or `max_tokens`

This should not happen with the models this Action's `openai_model` default
targets, but if you've pointed `openai_model` at a newer "reasoning" model
family not yet in the `REASONING_MODEL_PREFIXES` list in
`pr_description/llm.py` (currently `gpt-5*`, `gpt-6*`, `o1*`, `o3*`, `o4*`), the Action
may still send an unsupported `temperature`/`max_tokens` combination for it.
Open an issue (or a PR extending that list) with the model name.

### The generated description/title/labels seem cut off or missing entirely

- Check `max_tokens` — this bounds how much the model is allowed to generate
  for its response. A very small value can truncate the output.
- Check `max_diff_tokens` — a large pull request may have its diff trimmed
  before it ever reaches the model. Raising this, or narrowing
  `exclude_patterns`, gives the model more (or more relevant) context.

### Structured features (title/labels/breaking-change) silently don't come through

If the OpenAI/Azure deployment doesn't support structured outputs (an older
Azure API version is the most common cause), the Action falls back to a
plain-text description for that run and logs a warning rather than failing —
check the workflow run's logs for `"Structured PR content request was
rejected by the API"`.
