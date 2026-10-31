"""Command-line entry point: orchestrates the whole "autofill a PR" flow.

Reads the pull request via the GitHub API, builds a token-bounded diff
prompt, asks the model for content (plain description, or the richer
structured mode - see :mod:`pr_description.llm`), and writes the result
back. Each of description, title and labels has an always/never/smart overwrite
mode (see :mod:`pr_description.existing_content`) deciding what happens to
content the pull request already has.

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

from . import diff_filter, existing_content, llm, llm_anthropic
from .existing_content import ALWAYS, NEVER, SMART, ExistingDescription
from .github_api import GitHubApiError, GitHubClient

#: Label applied when `detect_breaking_changes` finds one. Not part of
#: `DEFAULT_LABEL_TAXONOMY` since it's applied directly by this module rather
#: than chosen by the model from the taxonomy.
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


def _overwrite_modes() -> tuple[str, str, str] | None:
    """Read the description, title and labels overwrite modes.

    Returns:
        The three modes, or `None` (after printing why) if any is unrecognized.
    """
    modes: list[str] = []
    for input_name in (
        "INPUT_OVERWRITE_DESCRIPTION",
        "INPUT_OVERWRITE_TITLE",
        "INPUT_OVERWRITE_LABELS",
    ):
        value = os.environ.get(input_name, NEVER)
        mode = existing_content.parse_overwrite_mode(value)
        if mode is None:
            print(
                f"Unknown {input_name} value '{value}', expected {ALWAYS}, {NEVER} or {SMART}"
            )
            return None
        modes.append(mode)
    return modes[0], modes[1], modes[2]


def _resolve_description(
    existing: ExistingDescription,
    mode: str,
    content: llm.PRContent,
    breaking_note: str,
    footer: str,
) -> str | None:
    """Work out the description to write.

    Args:
        existing: The pull request's current description.
        mode: The description's overwrite mode.
        content: What the model returned.
        breaking_note: The note the description must carry, or `""`. Written
            whatever `mode` is, since a breaking change must always be visible.
        footer: The rendered attribution footer, or `""`.

    Returns:
        The new description, or `None` to leave the current one as it is.
    """
    generated = content["description"]
    if not existing.text or mode == ALWAYS:
        return existing_content.compose_description(generated, breaking_note, footer)

    action = content["description_action"] if mode == SMART else "keep"
    if action == "replace":
        return existing_content.compose_description(generated, breaking_note, footer)
    if action == "extend" and generated.strip():
        return existing_content.compose_description(
            f"{existing.text}\n\n{generated.strip()}",
            breaking_note or existing.note,
            footer,
        )
    # Keep. A breaking change newly found is still worth surfacing, but nothing
    # else about the text changes, the footer included.
    if breaking_note and not existing.note:
        return f"{breaking_note}\n\n{existing.raw}"
    return None


def _needs_generated_description(
    existing: ExistingDescription, mode: str, content: llm.PRContent
) -> bool:
    """Whether the model's description text is about to replace the current one."""
    if not existing.text or mode == ALWAYS:
        return True
    return mode == SMART and content["description_action"] == "replace"


def _apply_labels(
    github: GitHubClient,
    pull_request_id: int,
    mode: str,
    chosen: set[str],
    required: set[str],
    current: set[str],
    label_taxonomy: list[str],
) -> None:
    """Bring the pull request's labels in line with those the model chose.

    `required` labels are added whatever `mode` is, unlike `chosen` ones.
    Only taxonomy labels are ever removed, so labels a team manages by hand or
    with other tools survive. `breaking-change` is never removed either: losing
    a warning to one model's judgment is worse than a stale label. An empty
    choice changes nothing, since a plain-text fallback looks exactly like one.

    Raises:
        GitHubApiError: If a GitHub request fails.
    """
    frozen = not chosen or (mode == NEVER and bool(current))
    to_add = sorted((required | (set() if frozen else chosen)) - current)
    if to_add:
        github.ensure_labels_exist(to_add)
        github.add_labels(pull_request_id, to_add)
    if frozen:
        return
    removable = set(label_taxonomy) - {BREAKING_CHANGE_LABEL}
    for label in sorted((current & removable) - chosen):
        github.remove_label(pull_request_id, label)


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

    max_tokens = int(os.environ.get("INPUT_MAX_TOKENS", "6000"))
    temperature = float(os.environ.get("INPUT_TEMPERATURE", "0.6"))
    sample_prompt = os.environ.get("INPUT_SAMPLE_PROMPT") or llm.SAMPLE_PROMPT
    sample_response = (
        os.environ.get("INPUT_SAMPLE_RESPONSE") or llm.GOOD_SAMPLE_RESPONSE
    )
    completion_prompt_template = (
        os.environ.get("INPUT_COMPLETION_PROMPT") or llm.COMPLETION_PROMPT
    )
    modes = _overwrite_modes()
    if modes is None:
        return 1
    description_mode, title_mode, labels_mode = modes
    description_style = (
        os.environ.get("INPUT_DESCRIPTION_STYLE", "rich").strip().lower()
    )
    if description_style not in llm.DESCRIPTION_STYLES:
        print(
            f"Unknown description_style '{description_style}', expected one of: "
            f"{', '.join(llm.DESCRIPTION_STYLES)}"
        )
        return 1
    azure_endpoint = os.environ.get("INPUT_AZURE_ENDPOINT", "")
    azure_api_version = os.environ.get("INPUT_AZURE_OPENAI_API_VERSION", "")

    generate_title = _bool_env(os.environ.get("INPUT_GENERATE_TITLE", "false"))
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

    existing = existing_content.split_description(pull_request_data["body"])
    current_labels: set[str] = {
        label["name"] for label in pull_request_data.get("labels") or []
    }
    description_frozen = bool(existing.text) and description_mode == NEVER
    title_frozen = not generate_title or title_mode == NEVER
    labels_frozen = not enable_labels or (labels_mode == NEVER and bool(current_labels))
    # Detection has to run even then: breaking changes must always be surfaced.
    if (
        description_frozen
        and title_frozen
        and labels_frozen
        and not detect_breaking_changes
    ):
        print(
            "Pull request already has its content and nothing may overwrite it, skipping"
        )
        return 0

    if allowed_users:
        pr_author = pull_request_data["user"]["login"]
        if pr_author.lower() not in allowed_users:
            print(
                f"Pull request author {pr_author} is not allowed to trigger this action"
            )
            return 0

    pull_request_title: str = pull_request_data["title"] or ""
    review_title = (
        generate_title
        and title_mode == SMART
        and not existing_content.is_placeholder_title(
            pull_request_title, pull_request_data.get("head", {}).get("ref", "")
        )
    )
    review_description = bool(existing.text) and description_mode == SMART
    review_labels = enable_labels and labels_mode == SMART and bool(current_labels)
    review: llm.ReviewRequest | None = None
    if review_description or review_title or review_labels:
        review = llm.ReviewRequest(
            description=existing.text if review_description else None,
            title=pull_request_title if review_title else None,
            labels=sorted(current_labels) if review_labels else None,
        )

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
    # Only OpenAI takes a temperature; Claude's generate_pr_content has no such
    # parameter (see its docstring), so it must not be passed there.
    sampling: dict[str, Any] = {}
    if provider == "anthropic":
        client = llm_anthropic.build_client(api_key)
        generate_pr_content = llm_anthropic.generate_pr_content
    else:
        client = llm.build_client(api_key, azure_endpoint, azure_api_version)
        generate_pr_content = llm.generate_pr_content
        sampling["temperature"] = temperature
    structured = (
        generate_title or enable_labels or detect_breaking_changes or review is not None
    )

    try:
        content = generate_pr_content(
            client,
            model,
            pull_request_title,
            completion_prompt,
            structured=structured,
            max_tokens=max_tokens,
            sample_prompt=sample_prompt,
            sample_response=sample_response,
            label_taxonomy=label_taxonomy,
            description_style=description_style,
            review=review,
            **sampling,
        )
    except (openai.OpenAIError, anthropic.AnthropicError) as error:
        print(f"{PROVIDER_LABELS[provider]} request failed: {error}")
        return 1

    # A successful run hides this otherwise, so surface it on the workflow summary.
    if review is not None and content["description_action"] is None:
        print(
            "::warning::The model gave no verdict, so existing content was left "
            f"unchanged. If its reply was cut off, raise max_tokens (now {max_tokens})."
        )

    content["description"] = existing_content.neutralize_mentions(
        content["description"]
    )
    if content["title"]:
        content["title"] = existing_content.neutralize_mentions(content["title"])
    if content["breaking_change_notes"]:
        content["breaking_change_notes"] = existing_content.neutralize_mentions(
            content["breaking_change_notes"]
        )

    if (
        _needs_generated_description(existing, description_mode, content)
        and not content["description"].strip()
    ):
        print(
            "Model returned an empty description (this can happen with reasoning "
            f"models when max_tokens={max_tokens} is spent on hidden reasoning "
            "tokens before any visible output) - not overwriting the pull request."
        )
        return 1

    breaking_change = detect_breaking_changes and content["breaking_change"]
    # An earlier note survives a run that doesn't detect one, including a
    # plain-text fallback, which can't detect anything.
    breaking_note = ""
    if breaking_change:
        breaking_note = existing_content.format_breaking_note(
            content["breaking_change_notes"]
        )
    elif detect_breaking_changes:
        breaking_note = existing.note
    footer = (
        existing_content.ATTRIBUTION_TEMPLATE.format(model=model) if attribution else ""
    )
    description = _resolve_description(
        existing, description_mode, content, breaking_note, footer
    )

    try:
        if description is None or description == existing.raw:
            print("Leaving the pull request description unchanged")
        else:
            print(f"Generated pull request description: '{description}'")
            github.update_description(args.pull_request_id, description)

        if generate_title and content["title"]:
            print(f"Suggested pull request title: '{content['title']}'")
            apply_title = title_mode == ALWAYS or (
                title_mode == SMART
                and (not review_title or content["title_action"] == "replace")
            )
            if apply_title and content["title"] != pull_request_title:
                github.update_title(args.pull_request_id, content["title"])

        _apply_labels(
            github,
            args.pull_request_id,
            labels_mode,
            set(content["labels"]) if enable_labels else set(),
            {BREAKING_CHANGE_LABEL} if breaking_change else set(),
            current_labels,
            label_taxonomy,
        )
    except GitHubApiError as error:
        print(str(error))
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
