# Setup guide

## Get an API key

The Action calls your chosen AI provider on your behalf, using an API key that you
create and pay for. Pick one provider (you don't need both). API access is billed
separately from any ChatGPT or Claude.ai subscription, so those don't include API
credit.

### OpenAI

1. Sign in, or create an account, on the [OpenAI API platform](https://platform.openai.com/)
   (not chatgpt.com).
2. Add a payment method or credit under **Billing**. Requests fail with a quota
   error while the account has no credit.
3. Open the [API keys page](https://platform.openai.com/api-keys) and choose
   **Create new secret key**. Give it a recognizable name such as `ai-pr-assistant`.
4. Copy the key right away. It is shown only once, and starts with `sk-`.

See OpenAI's [help article](https://help.openai.com/en/articles/4936850-where-do-i-find-my-secret-api-key)
if the pages above have moved.

Using **Azure OpenAI** instead? Use one of the keys from your Azure OpenAI resource
(Azure portal, **Keys and Endpoint**) as `openai_api_key`, and also set
`azure_endpoint` and `azure_openai_api_version`.

### Anthropic (Claude)

1. Sign in, or create an account, in the [Claude Console](https://platform.claude.com/)
   (not claude.ai).
2. Add credit under [**Billing**](https://platform.claude.com/settings/billing).
   Requests fail while the account has no credit.
3. Open the [API keys page](https://platform.claude.com/settings/keys) and choose
   **Create Key**. Give it a recognizable name such as `ai-pr-assistant`.
4. Copy the key right away. It is shown only once, and starts with `sk-ant-`.

### Add the key as a GitHub secret

Never put the key in a workflow file or commit it. Store it as an encrypted secret:

1. In your repository, go to **Settings**, then **Secrets and variables**, then
   **Actions**, and choose **New repository secret**.
2. Name it `OPENAI_API_KEY` (for OpenAI) or `ANTHROPIC_API_KEY` (for Claude), paste
   the key as the value, and save.
3. Reference it from your workflow: `openai_api_key: ${{ secrets.OPENAI_API_KEY }}`,
   or for Claude, `provider: anthropic` with
   `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}`.

A few things worth knowing:

- Workflows triggered by pull requests **from forks**, and by **Dependabot**, don't
  receive your repository secrets, so the Action can't run for those pull requests.
  (This repository's own workflow skips Dependabot for that reason.)
- Set a spending limit, or at least watch usage, in the provider's console. The Action
  makes one request per run, and runs again on every push if you enable
  `overwrite_description`.
- If a key is ever exposed, revoke it in the provider's console and create a new one.

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

1. [Get an API key](#get-an-api-key) and save it as a repository secret: `OPENAI_API_KEY` for OpenAI. To use Claude instead, save an Anthropic key as `ANTHROPIC_API_KEY` and set `provider: anthropic` with `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}` in place of the OpenAI inputs (see [Choosing a provider](CONFIGURATION.md#choosing-a-provider)).
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
5. If you use Azure OpenAI instead of the public API, add `azure_endpoint` and `azure_openai_api_version`, and set `openai_api_key` to your Azure OpenAI key.
6. Review the options in the [Configuration reference](CONFIGURATION.md) before tuning models, token budgets, or diff exclusions.

## Versioning and pinning

Releases use calendar versioning, `YY.MM.DD-NNN` (for example `26.09.18-001`), and each release is
tagged with exactly that version. There is no floating `v1`-style tag, so choose one of:

- `uses: devsetgo/ai-pr-assistant@main` always runs the latest code.
- `uses: devsetgo/ai-pr-assistant@<version>` pins to one release for reproducible runs. Take the
  version from the [Releases page](https://github.com/devsetgo/ai-pr-assistant/releases) and
  see the [Changelog](CHANGELOG.md) for what changed between versions.

Beta and rc builds are tagged too; pin only to final releases.
