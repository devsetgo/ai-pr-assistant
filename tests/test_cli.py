import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import openai
import pytest

from pr_description import cli

REPO_ROOT = Path(__file__).resolve().parent.parent

BASE_ARGV = [
    "--github-api-url",
    "https://api.github.com",
    "--github-repository",
    "acme/widgets",
    "--pull-request-id",
    "42",
    "--github-token",
    "gh-token",
    "--openai-api-key",
    "sk-test",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in list(cli.os.environ):
        if key.startswith("INPUT_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def github_client(monkeypatch):
    instance = MagicMock()
    instance.get_pull_request.return_value = {
        "body": None,
        "title": "Add feature",
        "user": {"login": "alice"},
    }
    instance.get_pull_request_files.return_value = [
        {"filename": "app.py", "patch": "+print('hi')"}
    ]
    monkeypatch.setattr(cli, "GitHubClient", MagicMock(return_value=instance))
    return instance


@pytest.fixture
def generate_pr_content(monkeypatch):
    result = {
        "description": "Adds a feature",
        "title": None,
        "labels": [],
        "breaking_change": False,
        "breaking_change_notes": None,
    }
    mock = MagicMock(return_value=result)
    monkeypatch.setattr(cli.llm, "generate_pr_content", mock)
    monkeypatch.setattr(cli.llm, "build_client", MagicMock())
    return mock


def test_skips_when_description_exists_and_not_overwrite(
    github_client, generate_pr_content
):
    github_client.get_pull_request.return_value["body"] = "Already has a description"
    assert cli.main(BASE_ARGV) == 0
    generate_pr_content.assert_not_called()
    github_client.update_description.assert_not_called()


def test_skips_when_author_not_allowed(monkeypatch, github_client, generate_pr_content):
    monkeypatch.setenv("INPUT_ALLOWED_USERS", "bob,carol")
    assert cli.main(BASE_ARGV) == 0
    generate_pr_content.assert_not_called()


def test_proceeds_when_author_is_allowed(
    monkeypatch, github_client, generate_pr_content
):
    monkeypatch.setenv("INPUT_ALLOWED_USERS", "bob,alice")

    assert cli.main(BASE_ARGV) == 0

    github_client.update_description.assert_called_once()


@pytest.mark.parametrize(
    ("allowed_users", "author"),
    [
        ("alice, bob", "bob"),  # spaces after the commas
        ("ALICE", "alice"),  # GitHub logins are case-insensitive
        ("bob,alice", "Alice"),
    ],
)
def test_allowed_users_ignores_spaces_and_case(
    monkeypatch, github_client, generate_pr_content, allowed_users, author
):
    github_client.get_pull_request.return_value["user"]["login"] = author
    monkeypatch.setenv("INPUT_ALLOWED_USERS", allowed_users)

    assert cli.main(BASE_ARGV) == 0

    github_client.update_description.assert_called_once()


def test_custom_sample_prompt_and_response_reach_the_model(
    monkeypatch, github_client, generate_pr_content
):
    monkeypatch.setenv("INPUT_SAMPLE_PROMPT", "my example prompt")
    monkeypatch.setenv("INPUT_SAMPLE_RESPONSE", "my example response")

    assert cli.main(BASE_ARGV) == 0

    kwargs = generate_pr_content.call_args.kwargs
    assert kwargs["sample_prompt"] == "my example prompt"
    assert kwargs["sample_response"] == "my example response"


def test_returns_error_when_openai_request_fails(
    capsys, github_client, generate_pr_content
):
    generate_pr_content.side_effect = openai.OpenAIError("quota exceeded")

    assert cli.main(BASE_ARGV) == 1

    assert "OpenAI request failed: quota exceeded" in capsys.readouterr().out
    github_client.update_description.assert_not_called()


def test_happy_path_updates_description(
    monkeypatch, github_client, generate_pr_content
):
    monkeypatch.setenv("INPUT_ATTRIBUTION", "false")

    assert cli.main(BASE_ARGV) == 0

    github_client.update_description.assert_called_once_with(42, "Adds a feature")
    github_client.update_title.assert_not_called()
    github_client.add_labels.assert_not_called()


def test_attribution_footer_is_appended_by_default(github_client, generate_pr_content):
    assert cli.main(BASE_ARGV) == 0

    description_arg = github_client.update_description.call_args.args[1]
    assert description_arg.startswith("Adds a feature\n\n---\n<sub>")
    assert "devsetgo/ai-pr-assistant" in description_arg
    assert "with gpt-5-mini</sub>" in description_arg


def test_attribution_footer_names_the_configured_model(
    monkeypatch, github_client, generate_pr_content
):
    monkeypatch.setenv("INPUT_OPENAI_MODEL", "gpt-4.1")

    assert cli.main(BASE_ARGV) == 0

    description_arg = github_client.update_description.call_args.args[1]
    assert description_arg.endswith("with gpt-4.1</sub>")


def test_attribution_can_be_disabled(monkeypatch, github_client, generate_pr_content):
    monkeypatch.setenv("INPUT_ATTRIBUTION", "false")

    assert cli.main(BASE_ARGV) == 0

    github_client.update_description.assert_called_once_with(42, "Adds a feature")


def test_empty_description_is_not_written(github_client, generate_pr_content):
    generate_pr_content.return_value["description"] = "   "

    assert cli.main(BASE_ARGV) == 1

    github_client.update_description.assert_not_called()


def test_generate_title_without_overwrite_only_logs(
    monkeypatch, github_client, generate_pr_content
):
    generate_pr_content.return_value["title"] = "Better title"
    monkeypatch.setenv("INPUT_GENERATE_TITLE", "true")

    assert cli.main(BASE_ARGV) == 0

    github_client.update_title.assert_not_called()


def test_generate_title_with_overwrite_updates_title(
    monkeypatch, github_client, generate_pr_content
):
    generate_pr_content.return_value["title"] = "Better title"
    monkeypatch.setenv("INPUT_GENERATE_TITLE", "true")
    monkeypatch.setenv("INPUT_OVERWRITE_TITLE", "true")

    assert cli.main(BASE_ARGV) == 0

    github_client.update_title.assert_called_once_with(42, "Better title")


def test_breaking_change_prepends_note_and_applies_label(
    monkeypatch, github_client, generate_pr_content
):
    generate_pr_content.return_value.update(
        {
            "labels": ["bug"],
            "breaking_change": True,
            "breaking_change_notes": "Removed /v1 endpoint",
        }
    )
    monkeypatch.setenv("INPUT_DETECT_BREAKING_CHANGES", "true")
    monkeypatch.setenv("INPUT_ENABLE_LABELS", "true")

    assert cli.main(BASE_ARGV) == 0

    description_arg = github_client.update_description.call_args.args[1]
    assert "Potential breaking change" in description_arg
    assert "Removed /v1 endpoint" in description_arg

    github_client.ensure_labels_exist.assert_called_once()
    applied = set(github_client.ensure_labels_exist.call_args.args[0])
    assert applied == {"bug", "breaking-change"}
    github_client.add_labels.assert_called_once()


def test_returns_error_when_get_pull_request_fails(github_client, generate_pr_content):
    github_client.get_pull_request.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1

    generate_pr_content.assert_not_called()


def test_returns_error_when_get_pull_request_files_fails(
    github_client, generate_pr_content
):
    github_client.get_pull_request_files.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1

    generate_pr_content.assert_not_called()


def test_returns_error_when_update_description_fails(
    github_client, generate_pr_content
):
    github_client.update_description.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1


def test_returns_error_when_update_title_fails(
    monkeypatch, github_client, generate_pr_content
):
    generate_pr_content.return_value["title"] = "Better title"
    monkeypatch.setenv("INPUT_GENERATE_TITLE", "true")
    monkeypatch.setenv("INPUT_OVERWRITE_TITLE", "true")
    github_client.update_title.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1


def test_returns_error_when_label_update_fails(
    monkeypatch, github_client, generate_pr_content
):
    generate_pr_content.return_value["labels"] = ["bug"]
    monkeypatch.setenv("INPUT_ENABLE_LABELS", "true")
    github_client.ensure_labels_exist.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1


def test_enable_labels_without_any_labels_makes_no_label_calls(
    monkeypatch, github_client, generate_pr_content
):
    monkeypatch.setenv("INPUT_ENABLE_LABELS", "true")

    assert cli.main(BASE_ARGV) == 0

    github_client.ensure_labels_exist.assert_not_called()
    github_client.add_labels.assert_not_called()


def _action_input_names() -> list[str]:
    """Top-level input names declared in action.yml (no YAML dependency needed)."""
    names: list[str] = []
    in_inputs = False
    for line in (REPO_ROOT / "action.yml").read_text().splitlines():
        if line == "inputs:":
            in_inputs = True
        elif in_inputs and re.match(r"^\S", line):
            break  # next top-level key, e.g. `runs:`
        elif in_inputs and (match := re.match(r"^  ([a-z_]+):", line)):
            names.append(match.group(1))
    return names


@pytest.mark.parametrize("input_name", _action_input_names())
def test_every_action_input_is_read_by_the_code(input_name):
    """action.yml exposes each input to the container as INPUT_<NAME>; if nothing
    reads that exact variable the input is silently dead."""
    sources = (REPO_ROOT / "pr_description" / "cli.py").read_text() + (
        REPO_ROOT / "entrypoint.sh"
    ).read_text()
    assert f"INPUT_{input_name.upper()}" in sources


ANTHROPIC_ARGV = [*BASE_ARGV, "--anthropic-api-key", "sk-ant-test"]


@pytest.fixture
def anthropic_llm(monkeypatch):
    """Stub out the Anthropic client and generation, like `generate_pr_content`."""
    result = {
        "description": "Adds a feature",
        "title": None,
        "labels": [],
        "breaking_change": False,
        "breaking_change_notes": None,
    }
    generate = MagicMock(return_value=result)
    build_client = MagicMock()
    monkeypatch.setattr(cli.llm_anthropic, "generate_pr_content", generate)
    monkeypatch.setattr(cli.llm_anthropic, "build_client", build_client)
    return SimpleNamespace(generate=generate, build_client=build_client)


def test_default_provider_is_openai_and_ignores_the_anthropic_key(
    github_client, generate_pr_content
):
    assert cli.main(ANTHROPIC_ARGV) == 0

    cli.llm.build_client.assert_called_once_with("sk-test", "", "")
    assert generate_pr_content.call_args.args[1] == "gpt-5-mini"


def test_anthropic_provider_uses_claude_client_key_and_haiku_default(
    monkeypatch, github_client, anthropic_llm, generate_pr_content
):
    monkeypatch.setenv("INPUT_PROVIDER", "anthropic")

    assert cli.main(ANTHROPIC_ARGV) == 0

    anthropic_llm.build_client.assert_called_once_with("sk-ant-test")
    assert anthropic_llm.generate.call_args.args[1] == "claude-haiku-4-5-20251001"
    generate_pr_content.assert_not_called()


def test_anthropic_model_input_is_used_and_named_in_the_footer(
    monkeypatch, github_client, anthropic_llm
):
    monkeypatch.setenv("INPUT_PROVIDER", "anthropic")
    monkeypatch.setenv("INPUT_ANTHROPIC_MODEL", "claude-sonnet-5")
    # Must not leak in: openai_model only applies to the openai provider.
    monkeypatch.setenv("INPUT_OPENAI_MODEL", "gpt-4.1")

    assert cli.main(ANTHROPIC_ARGV) == 0

    assert anthropic_llm.generate.call_args.args[1] == "claude-sonnet-5"
    description_arg = github_client.update_description.call_args.args[1]
    assert description_arg.endswith("with claude-sonnet-5</sub>")


def test_provider_is_case_and_whitespace_insensitive(
    monkeypatch, github_client, anthropic_llm
):
    monkeypatch.setenv("INPUT_PROVIDER", " Anthropic ")

    assert cli.main(ANTHROPIC_ARGV) == 0

    anthropic_llm.generate.assert_called_once()


def test_unknown_provider_fails_before_touching_github(
    monkeypatch, capsys, github_client, generate_pr_content
):
    monkeypatch.setenv("INPUT_PROVIDER", "gemini")

    assert cli.main(ANTHROPIC_ARGV) == 1

    assert "Unknown provider 'gemini'" in capsys.readouterr().out
    github_client.get_pull_request.assert_not_called()


@pytest.mark.parametrize(
    ("provider", "argv"),
    [
        ("anthropic", BASE_ARGV),  # only the OpenAI key is set
        ("openai", ["--anthropic-api-key", "sk-ant-test", *BASE_ARGV[:-2]]),
    ],
)
def test_missing_api_key_for_the_selected_provider_fails(
    monkeypatch, capsys, github_client, generate_pr_content, provider, argv
):
    monkeypatch.setenv("INPUT_PROVIDER", provider)

    assert cli.main(argv) == 1

    assert f"requires the {provider}_api_key input" in capsys.readouterr().out
    github_client.get_pull_request.assert_not_called()


def test_returns_error_when_anthropic_request_fails(
    monkeypatch, capsys, github_client, anthropic_llm
):
    monkeypatch.setenv("INPUT_PROVIDER", "anthropic")
    anthropic_llm.generate.side_effect = cli.llm_anthropic.AnthropicRefusalError(
        "declined"
    )

    assert cli.main(ANTHROPIC_ARGV) == 1

    assert "Anthropic request failed: declined" in capsys.readouterr().out
    github_client.update_description.assert_not_called()
