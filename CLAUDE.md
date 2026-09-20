# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Docker-based GitHub Action (`devsetgo/ai-pr-assistant`) that reads a pull request's title and file
diffs and asks OpenAI to write its description, and optionally its title, labels, and a
breaking-change note. It's inspired by `platisd/openai-pr-description`, started as a fork of it, and
has since gone in its own direction with no intent to merge back upstream — see `docs/MIGRATING.md`
for what changed and why. Full user-facing docs live under `docs/`; this file is for working on the
implementation itself.

**`docs/index.md` is generated — edit `README.md` instead.** `scripts/sync_docs_index.py` copies the README
to the docs home page (a pre-commit hook, `make docs-index`, and the docs workflow all run it), stripping the
`docs/` prefix from relative links. So in the README: link docs pages and images as `docs/...` (e.g.
`docs/media/x.png`), and link anything outside `docs/` (LICENSE, action.yml) by absolute GitHub URL. Content
that belongs only on the site goes in its own page under `docs/` and `mkdocs.yml` nav, not in the README.

## License

MIT (`LICENSE`), with two copyright lines: the original `platisd/openai-pr-description` author
(Dimitris Platis) and DevSetGo for this project's own modifications. MIT requires the original copyright
and permission notice be kept in all copies/substantial portions of the software, so:
- Never remove, replace, or backdate the Dimitris Platis copyright line in `LICENSE` — only add to
  it, the way the DevSetGo line already does.
- Any new file added to this repo (source or vendored) must stay MIT-compatible; don't add a
  conflicting license header to an individual file.
- If code is ever copied in from another project, its license must be checked for MIT-compatibility
  first, and its own attribution preserved per that license's terms — same obligation this repo
  places on anyone who copies from it.

## Commands

```bash
# Install
pip install -r requirements-dev.txt   # requirements.txt + the whole dev toolchain: pytest(+cov), ruff, pre-commit,
                                       # mypy, genbadge, zensical, bumpcalver (ruff must match .pre-commit-config.yaml's rev)

# Test (coverage is automatic — see pyproject.toml [tool.pytest.ini_options] addopts)
pytest -q                              # full suite, prints coverage summary, writes htmlcov/
make test                              # the full gate: ruff format/fix + pre-commit + mypy + pytest + genbadge
                                       # (writes docs/badges/*.svg, coverage.xml, report.xml)
pytest tests/test_llm.py -q            # one file
pytest tests/test_llm.py::test_generate_pr_content_classic_path -q   # one test

# Type-check
mypy pr_description --python-version 3.12 --ignore-missing-imports

# Lint + format (ruff; config in pyproject.toml [tool.ruff]) — also runs on every commit via pre-commit
pre-commit install                     # one-time; the devcontainer does this in postCreateCommand
pre-commit run --all-files             # or: make lint (check only) / make format (apply fixes)

# Build the actual Action image (installs from the hash-locked requirements.lock)
docker build -t ai-pr-assistant .
make lock                              # regenerate requirements.lock from requirements.txt (pip-compile, hashed,
                                       # wheels-only); rerun after ANY change to requirements.txt — tests/test_packaging.py
                                       # fails if the lock is stale, and .dockerignore must keep whitelisting the lock

# Version bump (CalVer via BumpCalver) — run locally, never from CI
make bump-preview                      # dry run: shows the next version + changelog entry
make bump                              # commit + tag locally (BUMP=beta / BUMP=rc for pre-releases); needs a clean
                                       # tree, loads OPENAI_API_KEY from .env for the changelog; pushes nothing
make git-cleanup                       # fetch --prune, then force-delete local branches whose upstream is gone
                                       # (never main/master/dev or the current branch)
```

Ruff is the only lint/format tool (`.pre-commit-config.yaml` pins its version; keep it in sync with
`requirements-dev.txt`) — don't assume `black`/`flake8` exist here. CI doesn't run it yet.

## Architecture

**Entry path**: `entrypoint.sh` (resolves the PR number from `$GITHUB_EVENT_PATH` if
`INPUT_PULL_REQUEST_ID` isn't set) → `autofill_description.py` (thin shim, kept only so the Docker
`ENTRYPOINT` and existing invocation keep working) → `pr_description.cli.main()`, which does
everything else. All non-required action inputs are read directly from `INPUT_*` env vars inside
`cli.py` (GitHub Actions populates these from `action.yml` defaults) — only the GitHub token, PR
number and the two API keys arrive as CLI flags. Neither API key is individually required: `cli.py`
checks the one for the selected `provider`.

**`pr_description/` package**, in call order from `cli.main()`:
- `github_api.py` — `GitHubClient` wraps the handful of GitHub REST calls needed (get PR, get
  changed files, update description/title, create+apply labels). Uses the issues endpoint (not the
  pulls endpoint) for description/title/label writes since a PR is also an issue in GitHub's data
  model. Paginates via the response `Link` header, not a fixed page count. A `requests.Session`
  with a real `Retry` adapter is built once per client.
- `diff_filter.py` — turns raw PR file entries into the diff text sent to the model: drops files
  matching `exclude_patterns` (glob), then token-budgets the rest using `tiktoken` against the
  target model's real encoding (`max_diff_tokens`), truncating the file that crosses the budget
  rather than dropping it.
- `llm_anthropic.py` — the Claude counterpart of `llm.py` (`provider: anthropic`, direct Anthropic
  API only): same classic/structured paths and the same `PRContent` result, reusing `llm.py`'s
  prompts, schema (`structured_system_prompt`, `PR_CONTENT_SCHEMA["schema"]` — the bare schema, not
  OpenAI's wrapper) and `parse_structured_payload`. Keep Anthropic SDK calls in this module, not in
  `llm.py`. **Never send `temperature`**: several current Claude models (Sonnet 5, Opus 5/4.8/4.7) reject
  sampling params and the 1.x SDK dropped them from `messages.create`. A `refusal` stop reason raises `AnthropicRefusalError`
  (an `anthropic.AnthropicError`, so `cli.py` reports it as a failed request); a reply with no text
  block returns `""` so the empty-description guard in `cli.py` applies.
- `llm.py` — builds the OpenAI/Azure OpenAI client and the request. Two message-building paths:
  - **Classic**: few-shot (`SAMPLE_PROMPT`/`GOOD_SAMPLE_RESPONSE`) → plain-text description. This is
    the original upstream behavior, preserved for backward compatibility.
  - **Structured**: JSON-schema-constrained (`PR_CONTENT_SCHEMA`) response carrying
    description/title/labels/breaking-change together. Falls back once to classic on
    `openai.BadRequestError` (e.g. an older Azure deployment without structured-output support).
  - `generate_pr_content()` picks classic vs. structured based on whether the caller set
    `structured=True`; `cli.py` sets it to `generate_title or enable_labels or detect_breaking_changes`.
  - **Model-family quirk, don't regress this**: "reasoning" models (`gpt-5*`, `gpt-6*`, `o1*`, `o3*`, `o4*` —
    see `REASONING_MODEL_PREFIXES`) reject a custom `temperature` and require
    `max_completion_tokens` instead of `max_tokens` on Chat Completions. `_completion_kwargs()` is
    the single place that branches on this — route any new request-building code through it rather
    than calling `chat.completions.create()` directly with hardcoded params.
- `cli.py` — orchestrates the above and owns all the gating logic: skip if a description already
  exists and `overwrite_description` is false, skip if the PR author isn't in `allowed_users`,
  only write the title if `generate_title and overwrite_title`, only touch labels if `enable_labels`.

**Tests** mock `requests`/the OpenAI client via `unittest.mock` — no live network calls. `tests/`
mirrors the package 1:1 (`test_cli.py`, `test_github_api.py`, `test_llm.py`, `test_llm_anthropic.py`, `test_diff_filter.py`).

## CI/CD

- `.github/workflows/test.yml` — pytest + coverage on push/PR, uploads `htmlcov/` as an artifact.
- `.github/workflows/sonar.yaml` — SonarCloud scan (`sonar-project.properties`); regenerates its own
  `coverage.xml` independently of test.yml (not shared via artifact) and normalizes the Cobertura
  `<sources>` block so Sonar resolves both `pr_description/foo.py`-style and bare `__init__.py`-style
  paths. Skipped for Dependabot PRs (no secret access).
- `.github/workflows/release-drafter.yml` + `.github/release-drafter.yml` — Release Drafter v7 runs as two
  jobs: the drafter drafts release notes on push to `main`, and the separate autolabeler action labels
  PRs (`pull_request`, not `pull_request_target`, so fork PRs go unlabeled; Dependabot PRs are skipped
  since Dependabot labels its own). The autolabeler matches on **branch name**, and categories (v7
  `when: labels:` form) are aligned with the labels this Action's own `enable_labels`/`label_taxonomy`
  and `breaking-change` label actually produce.
- There is deliberately no version-bump workflow: `make bump` runs `bumpcalver` locally, creating the commit and
  tag; pushing them (`git push origin HEAD <tag>`) is a separate, manual step (`bumpcalver` does not push).
- `.github/workflows/ai_pr_assistant.yml` — dogfoods the Action on this repo's own PRs (every input listed).
- `.github/workflows/docs.yml` — regenerates `docs/index.md` from the README and builds the Zensical site
  (`zensical build --clean --strict`) on docs-related PRs/pushes to `main`; deploys to GitHub Pages only on a
  release or manual dispatch (the build job uploads the artifact, deploy reuses it).
  One-time repo setting: Settings -> Pages -> Build and deployment -> Source must be **GitHub Actions**
  (this workflow publishes an artifact; it never creates a `gh-pages` branch). Without it the deploy job
  fails at `configure-pages` with "Get Pages site failed ... Not Found".
- `.github/dependabot.yaml` — pip + github-actions, monthly.

`docs/CHANGELOG.md` is a symlink to the root `CHANGELOG.md` (bumpcalver writes the root file), so the docs
site's Changelog page never goes stale.

`pyproject.toml`'s `[tool.bumpcalver]` targets three files that must stay in sync when the version
format changes: `pyproject.toml` (`project.version`), `pr_description/__init__.py` (`__version__`),
and `sonar-project.properties` (`sonar.projectVersion`).
