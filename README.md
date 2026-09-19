# `devsetgo/ai-pr-assistant` GitHub Action

Autofill the description (and optionally the title and labels) of your pull requests with the power of OpenAI!

This is a hard fork of [`platisd/openai-pr-description`](https://github.com/platisd/openai-pr-description)
by Dimitris Platis — substantially updated for current OpenAI models
(including the `gpt-5` family) and extended with optional title generation,
auto-labeling and breaking-change detection. See
[docs/MIGRATING.md](docs/MIGRATING.md) for the fork's history and how it
differs from upstream.

![openai-pr-description-screenshot](media/openai-pr-description-screenshot.png)

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
[docs/CONFIGURATION.md](docs/CONFIGURATION.md) for every input and how these
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
      - uses: devsetgo/ai-pr-assistant@master
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
```

That's it — every new pull request without a description will get one.

## Documentation

- [**Configuration reference**](docs/CONFIGURATION.md) — every input, defaults,
  classic vs. structured mode, and required permissions
- [**Troubleshooting**](docs/TROUBLESHOOTING.md) — the `403` error, missing
  labels, and other common issues
- [**Fork history & migrating from `platisd/openai-pr-description`**](docs/MIGRATING.md)

## Demo

The examples below are from the upstream project this was forked from, prior
to the rename and the features described above:

* [platisd/smartcar_shield/pull/70](https://github.com/platisd/smartcar_shield/pull/70)
  * The GitHub Action explained why it is useful to add itself to a repository. 🤯

![openai-pr-description-screenshot](media/openai-pr-description-screenshot.png)

* [platisd/cpp-command-parser/pull/16](https://github.com/platisd/cpp-command-parser/pull/16)
  * A decent explanation on why fetching `GoogleTest` during the `cmake` build instead of
  version controlling it, is a good idea. 🎯

![cpp-command-parser-screenshot](media/cpp-command-parser-screenshot.png)

* [platisd/clang-tidy-pr-comments/pull/43](https://github.com/platisd/clang-tidy-pr-comments/pull/43)
  * A decent explanation, with small modifications it'd be even better. 😅

![clang-tidy-pr-comments-screenshot](media/clang-tidy-pr-comments-screenshot.png)

## License

MIT — see [LICENSE](LICENSE). This fork retains the original upstream
copyright notice as required by the license, alongside a copyright line for
this fork's own modifications.

[OpenAI API key]: https://help.openai.com/en/articles/4936850-where-do-i-find-my-secret-api-key
[secret]: https://docs.github.com/en/actions/security-guides/encrypted-secrets
