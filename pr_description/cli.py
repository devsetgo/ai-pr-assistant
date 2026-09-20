"""Command-line entry point: orchestrates the whole "autofill a PR" flow.

Reads the pull request via the GitHub API, builds a token-bounded diff
prompt, asks the model for content (plain description, or the richer
structured mode - see :mod:`pr_description.llm`), and writes the result
back: description always, title/labels only when their opt-in inputs are
enabled.

Configuration mirrors the GitHub Action's `action.yml` inputs: required
values arrive as CLI flags (set by `entrypoint.sh`), everything else is read
directly from the `INPUT_*` environment variables GitHub Actions populates
for every action input.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from typing import Any

import anthropic
import openai

from . import diff_filter, llm, llm_anthropic
from .github_api import GitHubApiError, GitHubClient

#: Label applied when `detect_breaking_changes` finds one and `enable_labels`
#: is on. Not part of `DEFAULT_LABEL_TAXONOMY` since it's applied directly by
#: this module rather than chosen by the model from the taxonomy.
BREAKING_CHANGE_LABEL: str = "breaking-change"

#: Values accepted by the `provider` input.
PROVIDERS: tuple[str, ...] = ("openai", "anthropic")

#: Provider names as shown in log messages.
PROVIDER_LABELS: dict[str, str] = {"openai": "OpenAI", "anthropic": "Anthropic"}

#: Default model per provider, used when the provider's model input is unset.
DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-5-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}

#: Default value for the `label_taxonomy` input - the labels the model may
#: choose from when `enable_labels` is set, absent an explicit override.
DEFAULT_LABEL_TAXONOMY: str = (
    "bug,feature,enhancement,documentation,dependencies,refactor,test,chore"
)

#: Footer appended to the description when `attribution` is on. Added here,
#: after generation, rather than requested in the prompt, so the model can't
#: drop it, reword it, or invent a model name.
ATTRIBUTION_TEMPLATE: str = (
    "\n\n---\n<sub>Created using "
    "[devsetgo/ai-pr-assistant](https://github.com/devsetgo/ai-pr-assistant) "
    "with {model}</sub>"
)


def _bool_env(value: object) -> bool:
    """Parse a GitHub Actions boolean input value (as a string) into a bool.

    Args:
        value: The raw `INPUT_*` environment variable value, e.g. `"true"`.

    Returns:
        `True` for (case-insensitive) `"1"`, `"true"`, `"yes"` or `"on"`;
        `False` for anything else, including an empty/missing value.
    """
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Define and parse the script's required command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Use ChatGPT to generate a description for a pull request."
    )
    parser.add_argument(
        "--github-api-url", type=str, required=True, help="The GitHub API URL"
    )
    parser.add_argument(
        "--github-repository", type=str, required=True, help="The GitHub repository"
    )
    parser.add_argument(
        "--pull-request-id", type=int, required=True, help="The pull request ID"
    )
    parser.add_argument(
        "--github-token", type=str, required=True, help="The GitHub token"
    )
    # Neither key is individually required: which one is needed depends on the
    # `provider` input, so main() checks the one for the selected provider.
    parser.add_argument(
        "--openai-api-key", type=str, default="", help="The OpenAI API key"
    )
    parser.add_argument(
        "--anthropic-api-key", type=str, default="", help="The Anthropic API key"
    )
    return parser.parse_args(argv)


def _select_provider(args: argparse.Namespace) -> tuple[str, str, str] | None:
    """Resolve the `provider` input into the provider, its API key and its model.

    Args:
        args: The parsed command-line arguments, carrying both API keys.

    Returns:
        A `(provider, api_key, model)` tuple, or `None` (after printing why)
        if the provider is unknown or its API key was not supplied.
    """
    provider = os.environ.get("INPUT_PROVIDER", "openai").strip().lower()
    if provider not in PROVIDERS:
        print(f"Unknown provider '{provider}', expected one of: {', '.join(PROVIDERS)}")
        return None
    if provider == "anthropic":
        api_key = args.anthropic_api_key
        model = os.environ.get("INPUT_ANTHROPIC_MODEL") or DEFAULT_MODELS[provider]
    else:
        api_key = args.openai_api_key
        model = os.environ.get("INPUT_OPENAI_MODEL") or DEFAULT_MODELS[provider]
    if not api_key:
        print(f"Provider '{provider}' requires the {provider}_api_key input to be set")
        return None
    return provider, api_key, model


def main(argv: list[str] | None = None) -> int:
    """Run the autofill flow end-to-end.

    Args:
        argv: Command-line arguments, excluding the program name. Defaults
            to `sys.argv[1:]` (via `argparse`) when `None`.

    Returns:
        A process exit code: `0` for success or an intentional no-op (e.g.
        an existing description, or a disallowed author), `1` if the provider
        configuration is invalid or a GitHub or model request failed.
    """
    args = _parse_args(argv)

    # GitHub logins are case-insensitive, and people write "alice, bob".
    allowed_users: list[str] = [
        user.strip().lower()
        for user in os.environ.get("INPUT_ALLOWED_USERS", "").split(",")
        if user.strip()
    ]

    selection = _select_provider(args)
    if selection is None:
        return 1
    provider, api_key, model = selection

    max_tokens = int(os.environ.get("INPUT_MAX_TOKENS", "2000"))
    temperature = float(os.environ.get("INPUT_TEMPERATURE", "0.6"))
    sample_prompt = os.environ.get("INPUT_SAMPLE_PROMPT") or llm.SAMPLE_PROMPT
    sample_response = (
        os.environ.get("INPUT_SAMPLE_RESPONSE") or llm.GOOD_SAMPLE_RESPONSE
    )
    completion_prompt_template = (
        os.environ.get("INPUT_COMPLETION_PROMPT") or llm.COMPLETION_PROMPT
    )
    overwrite_description = _bool_env(
        os.environ.get("INPUT_OVERWRITE_DESCRIPTION", "false")
    )
    azure_endpoint = os.environ.get("INPUT_AZURE_ENDPOINT", "")
    azure_api_version = os.environ.get("INPUT_AZURE_OPENAI_API_VERSION", "")

    generate_title = _bool_env(os.environ.get("INPUT_GENERATE_TITLE", "false"))
    overwrite_title = _bool_env(os.environ.get("INPUT_OVERWRITE_TITLE", "false"))
    enable_labels = _bool_env(os.environ.get("INPUT_ENABLE_LABELS", "false"))
    detect_breaking_changes = _bool_env(
        os.environ.get("INPUT_DETECT_BREAKING_CHANGES", "false")
    )
    label_taxonomy: list[str] = [
        label.strip()
        for label in os.environ.get(
            "INPUT_LABEL_TAXONOMY", DEFAULT_LABEL_TAXONOMY
        ).split(",")
        if label.strip()
    ]
    exclude_patterns = diff_filter.parse_patterns(
        os.environ.get(
            "INPUT_EXCLUDE_PATTERNS", ",".join(diff_filter.DEFAULT_EXCLUDE_PATTERNS)
        )
    )
    max_diff_tokens = int(os.environ.get("INPUT_MAX_DIFF_TOKENS", "6000"))
    attribution = _bool_env(os.environ.get("INPUT_ATTRIBUTION", "true"))

    github = GitHubClient(
        args.github_api_url, args.github_repository, args.github_token
    )

    try:
        pull_request_data = github.get_pull_request(args.pull_request_id)
    except GitHubApiError as error:
        print(str(error))
        return 1

    if pull_request_data["body"] and not overwrite_description:
        print("Pull request already has a description, skipping")
        return 0

    if allowed_users:
        pr_author = pull_request_data["user"]["login"]
        if pr_author.lower() not in allowed_users:
            print(
                f"Pull request author {pr_author} is not allowed to trigger this action"
            )
            return 0

    pull_request_title: str = pull_request_data["title"]

    try:
        pull_request_files = github.get_pull_request_files(args.pull_request_id)
    except GitHubApiError as error:
        print(str(error))
        return 1

    completion_prompt = completion_prompt_template + diff_filter.build_diff_prompt(
        pull_request_files, exclude_patterns, max_diff_tokens, model
    )

    client: Any  # OpenAI or Anthropic client; mypy would narrow it per branch
    generate_pr_content: Callable[..., llm.PRContent]
    if provider == "anthropic":
        client = llm_anthropic.build_client(api_key)
        generate_pr_content = llm_anthropic.generate_pr_content
    else:
        client = llm.build_client(api_key, azure_endpoint, azure_api_version)
        generate_pr_content = llm.generate_pr_content
    structured = generate_title or enable_labels or detect_breaking_changes

    try:
        content = generate_pr_content(
            client,
            model,
            pull_request_title,
            completion_prompt,
            structured=structured,
            temperature=temperature,
            max_tokens=max_tokens,
            sample_prompt=sample_prompt,
            sample_response=sample_response,
            label_taxonomy=label_taxonomy,
        )
    except (openai.OpenAIError, anthropic.AnthropicError) as error:
        print(f"{PROVIDER_LABELS[provider]} request failed: {error}")
        return 1

    description = content["description"]
    if not description.strip():
        print(
            "Model returned an empty description (this can happen with reasoning "
            f"models when max_tokens={max_tokens} is spent on hidden reasoning "
            "tokens before any visible output) - not overwriting the pull request."
        )
        return 1

    if detect_breaking_changes and content["breaking_change"]:
        note = (
            content["breaking_change_notes"]
            or "This change may break existing consumers."
        )
        description = f"⚠️ **Potential breaking change:** {note}\n\n{description}"

    if attribution:
        description += ATTRIBUTION_TEMPLATE.format(model=model)

    print(f"Generated pull request description: '{description}'")
    try:
        github.update_description(args.pull_request_id, description)
    except GitHubApiError as error:
        print(str(error))
        return 1

    if generate_title and content["title"]:
        print(f"Suggested pull request title: '{content['title']}'")
        if overwrite_title:
            try:
                github.update_title(args.pull_request_id, content["title"])
            except GitHubApiError as error:
                print(str(error))
                return 1

    if enable_labels:
        labels_to_apply: set[str] = set(content["labels"])
        if detect_breaking_changes and content["breaking_change"]:
            labels_to_apply.add(BREAKING_CHANGE_LABEL)
        if labels_to_apply:
            try:
                github.ensure_labels_exist(sorted(labels_to_apply))
                github.add_labels(args.pull_request_id, sorted(labels_to_apply))
            except GitHubApiError as error:
                print(str(error))
                return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
