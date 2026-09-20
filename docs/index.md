<!-- Generated from README.md by scripts/sync_docs_index.py. Edit README.md, not this file. -->

# `devsetgo/ai-pr-assistant` GitHub Action

[![Tests](badges/tests-badge.svg)](https://github.com/devsetgo/ai-pr-assistant/actions/workflows/test.yml)
[![Test coverage](badges/coverage-badge.svg)](https://github.com/devsetgo/ai-pr-assistant/actions/workflows/test.yml)
[![Quality gate status](https://sonarcloud.io/api/project_badges/measure?project=devsetgo_ai-pr-assistant&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=devsetgo_ai-pr-assistant)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=devsetgo_ai-pr-assistant&metric=coverage)](https://sonarcloud.io/summary/new_code?id=devsetgo_ai-pr-assistant)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=devsetgo_ai-pr-assistant&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=devsetgo_ai-pr-assistant)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=devsetgo_ai-pr-assistant&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=devsetgo_ai-pr-assistant)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=devsetgo_ai-pr-assistant&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=devsetgo_ai-pr-assistant)
[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=devsetgo_ai-pr-assistant&metric=sqale_index)](https://sonarcloud.io/summary/new_code?id=devsetgo_ai-pr-assistant)

Autofill the description (and optionally the title and labels) of your pull requests with the power of OpenAI!

Inspired by the excellent work of [`platisd/openai-pr-description`](https://github.com/platisd/openai-pr-description)
by Dimitris Platis, this project has since gone in its own direction —
substantially updated for current OpenAI models (including the `gpt-5`
family) and extended with optional title generation, auto-labeling and
breaking-change detection. See the [migration guide](MIGRATING.md) for
its history and how it differs from upstream.

![openai-pr-description-screenshot](media/repo-1.png)

## What does it do?

`ai-pr-assistant` is a GitHub Action that looks at the title as well as the contents
of your pull request and uses the [OpenAI API](https://openai.com/blog/openai-api) to automatically
fill up the description of your pull request. Just like ChatGPT would! 🎉<br>
The Action tries to focus on **why** the changes are needed rather on **what** they are,
like any proper pull request description should.

By default it only runs when a PR description is not already provided, so it
will never accidentally overwrite an existing one unless you opt in via
`overwrite_description`. You can also restrict it to only run for specific
PR authors, e.g. the repository's maintainers.

Optionally, it can also:
- propose (or apply) an improved **pull request title**
- **auto-label** the pull request from a configurable taxonomy
- flag likely **breaking changes** with a note in the description and a `breaking-change` label

All of these are opt-in and default to off, so a minimal workflow keeps the
exact plain-description behavior described above. See
the [configuration reference](CONFIGURATION.md) for every input and how these
features interact.

Keep in mind the OpenAI API is not free to use. That being said, so far it's been rather cheap,
i.e. around ~$0.10 for 15-20 pull requests.

## Quickstart

1. Create an account on OpenAI, set up a payment method and get your [OpenAI API key].
2. Add the OpenAI API key as a [secret] in your repository's settings.
3. Create a workflow YAML file, e.g. `.github/workflows/ai-pr-assistant.yml`:

```yaml
name: Autofill PR description

on: pull_request

jobs:
  ai-pr-assistant:
    runs-on: ubuntu-latest

    steps:
      - uses: devsetgo/ai-pr-assistant@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          openai_model: gpt-5-mini
          max_tokens: '2000'
          max_diff_tokens: '6000'
```

That's it — every new pull request without a description will get one.

## Documentation

- [**GitHub Pages site**](https://devsetgo.github.io/ai-pr-assistant/) — published docs built with Zensical
- [**Setup guide**](SETUP.md) — a full-capability example workflow and a step-by-step walkthrough
- [**Configuration reference**](CONFIGURATION.md) — every input, defaults,
  classic vs. structured mode, and required permissions
- [**Changelog**](CHANGELOG.md)
- [**Troubleshooting**](TROUBLESHOOTING.md) — the `403` error, missing
  labels, and other common issues
- [**History & migrating from `platisd/openai-pr-description`**](MIGRATING.md)
- [**Action metadata (`action.yml`)**](https://github.com/devsetgo/ai-pr-assistant/blob/main/action.yml)

## Demo

These examples show the kind of developer tooling and product surfaces this project is designed to complement.

### [BumpCalver](https://github.com/devsetgo/bumpcalver)

BumpCalver is my calendar-versioning library for Python that helps manage versions while also maintaining a changelog. It keeps versioning and release notes aligned, making release management more predictable and easier to automate.

![BumpCalver dashboard screenshot](media/bumpcalver-1.png)

### [pydantic-schemaforms](https://github.com/devsetgo/pydantic-schemaforms)

`pydantic-schemaforms` is a modern Python library that generates dynamic HTML forms from Pydantic 2.x+ models. It is designed for server-rendered apps: you define a model and optional UI hints, and get back ready-to-embed HTML with validation and framework styling.

![pydantic-schemaforms screenshot](media/pydantic-schemaform-1.png)

## License

MIT — see [LICENSE](https://github.com/devsetgo/ai-pr-assistant/blob/main/LICENSE). This project retains the original upstream
copyright notice as required by the license, alongside a copyright line for
its own modifications.

[OpenAI API key]: https://help.openai.com/en/articles/4936850-where-do-i-find-my-secret-api-key
[secret]: https://docs.github.com/en/actions/security-guides/encrypted-secrets
