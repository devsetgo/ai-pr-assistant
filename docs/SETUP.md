# Setup guide

## Full-capability example

This example enables every optional feature on a pull request workflow: generate a title,
auto-label the PR, flag likely breaking changes, and keep the description fresh when it already exists.

```yaml
name: AI PR Assistant

on:
  pull_request:
    types: [opened, synchronize, reopened, edited]
  workflow_dispatch:

jobs:
  ai-pr-assistant:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      issues: write

    steps:
      - name: Fill in PR details
        uses: devsetgo/ai-pr-assistant@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          openai_model: gpt-5-mini
          allowed_users: "your-github-username,other-maintainer"
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

1. Create an OpenAI key and save it as a repository secret named `OPENAI_API_KEY`.
2. Add the workflow file under `.github/workflows/`.
3. Choose whether you want the normal behavior or the full feature set:
   - `generate_title: true` asks for a better PR title.
   - `overwrite_title: true` applies the title automatically.
   - `enable_labels: true` makes the action create and apply labels from `label_taxonomy`.
   - `detect_breaking_changes: true` adds a warning note and a `breaking-change` label when the model suspects a breaking change.
   - `overwrite_description: true` lets the action refresh a description on subsequent PR updates.
4. Set `permissions` so the action can write to pull requests and issues:
   - `pull-requests: write` for description and title updates
   - `issues: write` for labels when `enable_labels` is enabled
5. If you use Azure OpenAI instead of the public API, add `azure_endpoint` and `azure_openai_api_version` and leave `openai_api_key` unset for the Azure path.
6. Review the options in the [Configuration reference](CONFIGURATION.md) before tuning models, token budgets, or diff exclusions.

## Versioning and pinning

Releases use calendar versioning, `YY.MM.DD-NNN` (for example `26.09.18-001`), and each release is
tagged with exactly that version. There is no floating `v1`-style tag, so choose one of:

- `uses: devsetgo/ai-pr-assistant@main` always runs the latest code.
- `uses: devsetgo/ai-pr-assistant@<version>` pins to one release for reproducible runs. Take the
  version from the [Releases page](https://github.com/devsetgo/ai-pr-assistant/releases) and
  see the [Changelog](CHANGELOG.md) for what changed between versions.

Beta and rc builds are tagged too; pin only to final releases.
