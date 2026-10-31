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
    assert generate_pr_content.call_args.kwargs["temperature"] == 0.6


def test_anthropic_provider_uses_claude_client_key_and_haiku_default(
    monkeypatch, github_client, anthropic_llm, generate_pr_content
):
    monkeypatch.setenv("INPUT_PROVIDER", "anthropic")

    assert cli.main(ANTHROPIC_ARGV) == 0

    anthropic_llm.build_client.assert_called_once_with("sk-ant-test")
    assert anthropic_llm.generate.call_args.args[1] == "claude-haiku-4-5-20251001"
    # Claude's generate_pr_content takes no temperature, so none may be passed.
    assert "temperature" not in anthropic_llm.generate.call_args.kwargs
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


DETAILED = "A detailed description written by a person, with real reasoning."


def _review_result(mock, **overrides):
    mock.return_value.update(
        {"description_action": "keep", "title_action": "keep", **overrides}
    )


@pytest.fixture
def smart(monkeypatch, github_client, generate_pr_content):
    """Every overwrite mode set to smart, on a PR that already has content."""
    monkeypatch.setenv("INPUT_ATTRIBUTION", "false")
    monkeypatch.setenv("INPUT_GENERATE_TITLE", "true")
    monkeypatch.setenv("INPUT_ENABLE_LABELS", "true")
    monkeypatch.setenv("INPUT_OVERWRITE_DESCRIPTION", "smart")
    monkeypatch.setenv("INPUT_OVERWRITE_TITLE", "smart")
    monkeypatch.setenv("INPUT_OVERWRITE_LABELS", "smart")
    github_client.get_pull_request.return_value.update(
        {
            "body": DETAILED,
            "title": "Add dark mode toggle",
            "head": {"ref": "feat/dark-mode"},
            "labels": [{"name": "feature"}, {"name": "needs-qa"}],
        }
    )
    _review_result(generate_pr_content)
    return github_client


@pytest.mark.parametrize("input_name", ["DESCRIPTION", "TITLE", "LABELS"])
def test_unknown_overwrite_mode_fails(monkeypatch, capsys, github_client, input_name):
    monkeypatch.setenv(f"INPUT_OVERWRITE_{input_name}", "maybe")

    assert cli.main(BASE_ARGV) == 1

    assert "maybe" in capsys.readouterr().out
    github_client.get_pull_request.assert_not_called()


def test_unknown_description_style_fails(monkeypatch, capsys, github_client):
    monkeypatch.setenv("INPUT_DESCRIPTION_STYLE", "fancy")

    assert cli.main(BASE_ARGV) == 1

    assert "fancy" in capsys.readouterr().out


def test_description_style_reaches_the_model(
    monkeypatch, github_client, generate_pr_content
):
    monkeypatch.setenv("INPUT_DESCRIPTION_STYLE", "plain")

    assert cli.main(BASE_ARGV) == 0

    assert generate_pr_content.call_args.kwargs["description_style"] == "plain"


@pytest.mark.parametrize("value", ["true", "always"])
def test_always_replaces_the_description(
    monkeypatch, github_client, generate_pr_content, value
):
    monkeypatch.setenv("INPUT_OVERWRITE_DESCRIPTION", value)
    monkeypatch.setenv("INPUT_ATTRIBUTION", "false")
    github_client.get_pull_request.return_value["body"] = DETAILED

    assert cli.main(BASE_ARGV) == 0

    assert generate_pr_content.call_args.kwargs["review"] is None
    github_client.update_description.assert_called_once_with(42, "Adds a feature")


def test_frozen_description_does_not_block_a_smart_title(
    monkeypatch, smart, generate_pr_content
):
    monkeypatch.setenv("INPUT_OVERWRITE_DESCRIPTION", "never")
    _review_result(generate_pr_content, title="Enhancement: Add Dark Mode")
    generate_pr_content.return_value["title_action"] = "replace"

    assert cli.main(BASE_ARGV) == 0

    smart.update_description.assert_not_called()
    smart.update_title.assert_called_once_with(42, "Enhancement: Add Dark Mode")


@pytest.mark.parametrize("body", [None, "", "  \n "])
def test_smart_fills_a_blank_description_without_reviewing_it(
    smart, generate_pr_content, body
):
    smart.get_pull_request.return_value["body"] = body
    generate_pr_content.return_value["description_action"] = "keep"

    assert cli.main(BASE_ARGV) == 0

    assert generate_pr_content.call_args.kwargs["review"].description is None
    smart.update_description.assert_called_once_with(42, "Adds a feature")


def test_smart_keep_leaves_the_description_untouched(smart, generate_pr_content):
    assert cli.main(BASE_ARGV) == 0

    assert generate_pr_content.call_args.kwargs["review"].description == DETAILED
    smart.update_description.assert_not_called()


def test_smart_replace_writes_the_new_description(smart, generate_pr_content):
    _review_result(generate_pr_content, description_action="replace")

    assert cli.main(BASE_ARGV) == 0

    smart.update_description.assert_called_once_with(42, "Adds a feature")


def test_smart_replace_with_no_text_fails_rather_than_blanking(
    smart, generate_pr_content
):
    _review_result(generate_pr_content, description_action="replace", description=" ")

    assert cli.main(BASE_ARGV) == 1

    smart.update_description.assert_not_called()


def test_smart_extend_appends_to_the_text_verbatim(smart, generate_pr_content):
    _review_result(
        generate_pr_content, description_action="extend", description="\nAlso X.\n"
    )

    assert cli.main(BASE_ARGV) == 0

    smart.update_description.assert_called_once_with(42, f"{DETAILED}\n\nAlso X.")


def test_smart_extend_with_no_text_keeps(smart, generate_pr_content):
    _review_result(generate_pr_content, description_action="extend", description="")

    assert cli.main(BASE_ARGV) == 0

    smart.update_description.assert_not_called()


def test_smart_extend_does_not_stack_the_note_or_footer(
    monkeypatch, smart, generate_pr_content
):
    monkeypatch.setenv("INPUT_ATTRIBUTION", "true")
    footer = cli.existing_content.ATTRIBUTION_TEMPLATE.format(model="gpt-5-mini")
    note = cli.existing_content.format_breaking_note("Removed /v1")
    smart.get_pull_request.return_value["body"] = f"{note}\n\n{DETAILED}{footer}"
    _review_result(
        generate_pr_content, description_action="extend", description="Also X."
    )

    assert cli.main(BASE_ARGV) == 0

    assert generate_pr_content.call_args.kwargs["review"].description == DETAILED
    smart.update_description.assert_called_once_with(
        42, f"{note}\n\n{DETAILED}\n\nAlso X.{footer}"
    )


def test_smart_keep_still_surfaces_a_new_breaking_change(
    monkeypatch, smart, generate_pr_content
):
    monkeypatch.setenv("INPUT_DETECT_BREAKING_CHANGES", "true")
    _review_result(
        generate_pr_content, breaking_change=True, breaking_change_notes="Removed /v1"
    )

    assert cli.main(BASE_ARGV) == 0

    written = smart.update_description.call_args.args[1]
    assert written.startswith("> [!CAUTION]")
    assert written.endswith(DETAILED)
    assert "breaking-change" in smart.add_labels.call_args.args[1]


def test_smart_keep_does_not_repeat_a_breaking_note(
    monkeypatch, smart, generate_pr_content
):
    monkeypatch.setenv("INPUT_DETECT_BREAKING_CHANGES", "true")
    note = cli.existing_content.format_breaking_note("Removed /v1")
    smart.get_pull_request.return_value["body"] = f"{note}\n\n{DETAILED}"
    _review_result(
        generate_pr_content, breaking_change=True, breaking_change_notes="Reworded"
    )

    assert cli.main(BASE_ARGV) == 0

    smart.update_description.assert_not_called()


def test_smart_fallback_protects_everything(capsys, smart, generate_pr_content):
    """A plain-text fallback has no verdicts, so existing content must survive."""
    generate_pr_content.return_value.update(
        cli.llm.plain_result("A plain text description from the fallback")
    )

    assert cli.main(BASE_ARGV) == 0

    assert "::warning::" in capsys.readouterr().out
    smart.update_description.assert_not_called()
    smart.update_title.assert_not_called()
    smart.add_labels.assert_not_called()
    smart.remove_label.assert_not_called()


@pytest.mark.parametrize("title", ["dev", "feat/dark mode", "  "])
def test_smart_always_replaces_a_placeholder_title(smart, generate_pr_content, title):
    smart.get_pull_request.return_value["title"] = title
    _review_result(generate_pr_content, title="Enhancement: Add Dark Mode")

    assert cli.main(BASE_ARGV) == 0

    assert generate_pr_content.call_args.kwargs["review"].title is None
    smart.update_title.assert_called_once_with(42, "Enhancement: Add Dark Mode")


def test_smart_title_follows_the_verdict(smart, generate_pr_content):
    _review_result(generate_pr_content, title="Other", title_action="keep")
    assert cli.main(BASE_ARGV) == 0
    smart.update_title.assert_not_called()

    _review_result(generate_pr_content, title="Other", title_action="replace")
    assert cli.main(BASE_ARGV) == 0
    smart.update_title.assert_called_once_with(42, "Other")


def test_identical_title_is_not_rewritten(monkeypatch, smart, generate_pr_content):
    monkeypatch.setenv("INPUT_OVERWRITE_TITLE", "always")
    _review_result(generate_pr_content, title="Add dark mode toggle")

    assert cli.main(BASE_ARGV) == 0

    smart.update_title.assert_not_called()


def test_labels_are_diffed_and_foreign_labels_survive(smart, generate_pr_content):
    smart.get_pull_request.return_value["labels"] = [
        {"name": "feature"},
        {"name": "chore"},
        {"name": "needs-qa"},
        {"name": "breaking-change"},
    ]
    _review_result(generate_pr_content, labels=["feature", "bug"])

    assert cli.main(BASE_ARGV) == 0

    assert sorted(generate_pr_content.call_args.kwargs["review"].labels) == [
        "breaking-change",
        "chore",
        "feature",
        "needs-qa",
    ]
    smart.add_labels.assert_called_once_with(42, ["bug"])
    smart.remove_label.assert_called_once_with(42, "chore")


def test_labels_unchanged_makes_no_write_calls(smart, generate_pr_content):
    _review_result(generate_pr_content, labels=["feature"])

    assert cli.main(BASE_ARGV) == 0

    smart.ensure_labels_exist.assert_not_called()
    smart.add_labels.assert_not_called()
    smart.remove_label.assert_not_called()


def test_never_leaves_labelled_prs_alone(monkeypatch, smart, generate_pr_content):
    monkeypatch.setenv("INPUT_OVERWRITE_LABELS", "never")
    _review_result(generate_pr_content, labels=["bug"])

    assert cli.main(BASE_ARGV) == 0

    smart.add_labels.assert_not_called()
    smart.remove_label.assert_not_called()


def test_never_still_labels_an_unlabelled_pr(monkeypatch, smart, generate_pr_content):
    monkeypatch.setenv("INPUT_OVERWRITE_DESCRIPTION", "never")
    monkeypatch.setenv("INPUT_OVERWRITE_TITLE", "never")
    monkeypatch.setenv("INPUT_OVERWRITE_LABELS", "never")
    smart.get_pull_request.return_value["labels"] = []
    _review_result(generate_pr_content, labels=["bug"])

    assert cli.main(BASE_ARGV) == 0

    smart.add_labels.assert_called_once_with(42, ["bug"])
    smart.update_description.assert_not_called()


def test_everything_frozen_skips_the_model(monkeypatch, smart, generate_pr_content):
    for name in ("DESCRIPTION", "TITLE", "LABELS"):
        monkeypatch.setenv(f"INPUT_OVERWRITE_{name}", "never")

    assert cli.main(BASE_ARGV) == 0

    generate_pr_content.assert_not_called()


def test_returns_error_when_label_removal_fails(smart, generate_pr_content):
    _review_result(generate_pr_content, labels=["bug"])
    smart.remove_label.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1


@pytest.fixture
def breaking(monkeypatch, github_client, generate_pr_content):
    """Detection on, everything else frozen, on a PR that already has content."""
    monkeypatch.setenv("INPUT_ATTRIBUTION", "false")
    monkeypatch.setenv("INPUT_DETECT_BREAKING_CHANGES", "true")
    github_client.get_pull_request.return_value.update(
        {"body": DETAILED, "labels": [{"name": "needs-qa"}]}
    )
    generate_pr_content.return_value.update(
        {"breaking_change": True, "breaking_change_notes": "Removed /v1"}
    )
    return github_client


def test_breaking_change_is_surfaced_with_every_mode_frozen_and_labels_off(breaking):
    assert cli.main(BASE_ARGV) == 0

    written = breaking.update_description.call_args.args[1]
    assert written.startswith("> [!CAUTION]")
    assert "Removed /v1" in written
    assert written.endswith(DETAILED)
    breaking.ensure_labels_exist.assert_called_once_with(["breaking-change"])
    breaking.add_labels.assert_called_once_with(42, ["breaking-change"])
    breaking.remove_label.assert_not_called()


def test_never_labels_still_get_only_the_breaking_label(
    monkeypatch, breaking, generate_pr_content
):
    monkeypatch.setenv("INPUT_ENABLE_LABELS", "true")
    generate_pr_content.return_value["labels"] = ["bug"]

    assert cli.main(BASE_ARGV) == 0

    breaking.add_labels.assert_called_once_with(42, ["breaking-change"])


def test_breaking_change_already_surfaced_writes_nothing(breaking):
    note = cli.existing_content.format_breaking_note("Removed /v1")
    breaking.get_pull_request.return_value.update(
        {
            "body": f"{note}\n\n{DETAILED}",
            "labels": [{"name": "breaking-change"}],
        }
    )

    assert cli.main(BASE_ARGV) == 0

    breaking.update_description.assert_not_called()
    breaking.add_labels.assert_not_called()


def test_no_breaking_change_with_detection_on_changes_nothing(
    breaking, generate_pr_content
):
    generate_pr_content.return_value["breaking_change"] = False

    assert cli.main(BASE_ARGV) == 0

    breaking.update_description.assert_not_called()
    breaking.add_labels.assert_not_called()


def test_regenerating_keeps_an_earlier_note_when_nothing_is_detected(
    monkeypatch, breaking, generate_pr_content
):
    """A plain-text fallback reports no breaking change, so must not erase one."""
    monkeypatch.setenv("INPUT_OVERWRITE_DESCRIPTION", "always")
    note = cli.existing_content.format_breaking_note("Removed /v1")
    breaking.get_pull_request.return_value["body"] = f"{note}\n\n{DETAILED}"
    generate_pr_content.return_value["breaking_change"] = False

    assert cli.main(BASE_ARGV) == 0

    breaking.update_description.assert_called_once_with(42, f"{note}\n\nAdds a feature")


def test_regenerating_with_detection_off_drops_an_old_note(
    monkeypatch, breaking, generate_pr_content
):
    monkeypatch.setenv("INPUT_DETECT_BREAKING_CHANGES", "false")
    monkeypatch.setenv("INPUT_OVERWRITE_DESCRIPTION", "always")
    note = cli.existing_content.format_breaking_note("Removed /v1")
    breaking.get_pull_request.return_value["body"] = f"{note}\n\n{DETAILED}"

    assert cli.main(BASE_ARGV) == 0

    breaking.update_description.assert_called_once_with(42, "Adds a feature")
    breaking.add_labels.assert_not_called()


def test_model_written_mentions_are_neutralized_everywhere(
    monkeypatch, github_client, generate_pr_content
):
    monkeypatch.setenv("INPUT_ATTRIBUTION", "false")
    monkeypatch.setenv("INPUT_GENERATE_TITLE", "true")
    monkeypatch.setenv("INPUT_OVERWRITE_TITLE", "always")
    monkeypatch.setenv("INPUT_DETECT_BREAKING_CHANGES", "true")
    generate_pr_content.return_value.update(
        {
            "description": "Ask @alice",
            "title": "Fix for @bob",
            "breaking_change": True,
            "breaking_change_notes": "Breaks @main",
        }
    )

    assert cli.main(BASE_ARGV) == 0

    written = github_client.update_description.call_args.args[1]
    assert "Ask `@alice`" in written
    assert "Breaks `@main`" in written
    github_client.update_title.assert_called_once_with(42, "Fix for `@bob`")


def test_existing_mentions_are_left_alone(smart, generate_pr_content):
    smart.get_pull_request.return_value["body"] = "Thanks @alice"
    _review_result(generate_pr_content, description_action="extend", description="X")

    assert cli.main(BASE_ARGV) == 0

    smart.update_description.assert_called_once_with(42, "Thanks @alice\n\nX")
