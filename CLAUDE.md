# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Docker-based GitHub Action (`devsetgo/ai-pr-assistant`) that reads a pull request's title and file
diffs and asks OpenAI to write its description, and optionally its title, labels, and a
breaking-change note. It is a **hard fork** of `platisd/openai-pr-description` with no intent to
merge back upstream — see `docs/MIGRATING.md` for what changed and why. Full user-facing docs live
under `docs/`; this file is for working on the implementation itself.

## Commands

```bash
# Install
pip install -r requirements-dev.txt   # includes requirements.txt + pytest, pytest-cov, mypy-relevant deps

# Test (coverage is automatic — see pyproject.toml [tool.pytest.ini_options] addopts)
pytest -q                              # full suite, prints coverage summary, writes htmlcov/
pytest tests/test_llm.py -q            # one file
pytest tests/test_llm.py::test_generate_pr_content_classic_path -q   # one test

# Type-check
mypy pr_description --python-version 3.12 --ignore-missing-imports

# Build the actual Action image
docker build -t ai-pr-assistant .

# Version bump (CalVer via BumpCalver) — normally run through the manual
# "Version Bump" GitHub Actions workflow (workflow_dispatch: build/beta/rc), not locally
bumpcalver --build --dry-run --json   # preview what a bump would do, without writing/tagging
```

No lint/format tool is configured yet — don't assume `ruff`/`black`/`flake8` exist here.

## Architecture

**Entry path**: `entrypoint.sh` (resolves the PR number from `$GITHUB_EVENT_PATH` if
`INPUT_PULL_REQUEST_ID` isn't set) → `autofill_description.py` (thin shim, kept only so the Docker
`ENTRYPOINT` and existing invocation keep working) → `pr_description.cli.main()`, which does
everything else. All non-required action inputs are read directly from `INPUT_*` env vars inside
`cli.py` (GitHub Actions populates these from `action.yml` defaults) — only the required inputs
arrive as CLI flags.

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
- `llm.py` — builds the OpenAI/Azure OpenAI client and the request. Two message-building paths:
  - **Classic**: few-shot (`SAMPLE_PROMPT`/`GOOD_SAMPLE_RESPONSE`) → plain-text description. This is
    the original upstream behavior, preserved for backward compatibility.
  - **Structured**: JSON-schema-constrained (`PR_CONTENT_SCHEMA`) response carrying
    description/title/labels/breaking-change together. Falls back once to classic on
    `openai.BadRequestError` (e.g. an older Azure deployment without structured-output support).
  - `generate_pr_content()` picks classic vs. structured based on whether the caller set
    `structured=True`; `cli.py` sets it to `generate_title or enable_labels or detect_breaking_changes`.
  - **Model-family quirk, don't regress this**: "reasoning" models (`gpt-5*`, `o1*`, `o3*`, `o4*` —
    see `REASONING_MODEL_PREFIXES`) reject a custom `temperature` and require
    `max_completion_tokens` instead of `max_tokens` on Chat Completions. `_completion_kwargs()` is
    the single place that branches on this — route any new request-building code through it rather
    than calling `chat.completions.create()` directly with hardcoded params.
- `cli.py` — orchestrates the above and owns all the gating logic: skip if a description already
  exists and `overwrite_description` is false, skip if the PR author isn't in `allowed_users`,
  only write the title if `generate_title and overwrite_title`, only touch labels if `enable_labels`.

**Tests** mock `requests`/the OpenAI client via `unittest.mock` — no live network calls. `tests/`
mirrors the package 1:1 (`test_cli.py`, `test_github_api.py`, `test_llm.py`, `test_diff_filter.py`).

## CI/CD

- `.github/workflows/test.yml` — pytest + coverage on push/PR, uploads `htmlcov/` as an artifact.
- `.github/workflows/sonar.yaml` — SonarCloud scan (`sonar-project.properties`); regenerates its own
  `coverage.xml` independently of test.yml (not shared via artifact) and normalizes the Cobertura
  `<sources>` block so Sonar resolves both `pr_description/foo.py`-style and bare `__init__.py`-style
  paths. Skipped for Dependabot PRs (no secret access).
- `.github/workflows/release-drafter.yml` + `.github/release-drafter.yml` — drafts release notes on
  push to `master`; autolabeler matches on **branch name**, and categories are aligned with the
  labels this Action's own `enable_labels`/`label_taxonomy` and `breaking-change` label actually
  produce.
- `.github/workflows/version-bump.yml` — manual-only (`workflow_dispatch`). Runs `bumpcalver`, then
  pushes the resulting commit + tag itself (`bumpcalver` does not push).
- `.github/workflows/pr-description.yml` — dogfoods the Action on this repo's own PRs.
- `.github/dependabot.yaml` — pip + github-actions, monthly.

`pyproject.toml`'s `[tool.bumpcalver]` targets three files that must stay in sync when the version
format changes: `pyproject.toml` (`project.version`), `pr_description/__init__.py` (`__version__`),
and `sonar-project.properties` (`sonar.projectVersion`).
