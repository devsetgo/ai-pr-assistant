from unittest.mock import MagicMock

import pytest

from pr_description import cli


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


def test_skips_when_description_exists_and_not_overwrite(github_client, generate_pr_content):
    github_client.get_pull_request.return_value["body"] = "Already has a description"
    assert cli.main(BASE_ARGV) == 0
    generate_pr_content.assert_not_called()
    github_client.update_description.assert_not_called()


def test_skips_when_author_not_allowed(monkeypatch, github_client, generate_pr_content):
    monkeypatch.setenv("INPUT_ALLOWED_USERS", "bob,carol")
    assert cli.main(BASE_ARGV) == 0
    generate_pr_content.assert_not_called()


def test_happy_path_updates_description(github_client, generate_pr_content):
    assert cli.main(BASE_ARGV) == 0
    github_client.update_description.assert_called_once_with(42, "Adds a feature")
    github_client.update_title.assert_not_called()
    github_client.add_labels.assert_not_called()


def test_empty_description_is_not_written(github_client, generate_pr_content):
    generate_pr_content.return_value["description"] = "   "

    assert cli.main(BASE_ARGV) == 1

    github_client.update_description.assert_not_called()


def test_generate_title_without_overwrite_only_logs(monkeypatch, github_client, generate_pr_content):
    generate_pr_content.return_value["title"] = "Better title"
    monkeypatch.setenv("INPUT_GENERATE_TITLE", "true")

    assert cli.main(BASE_ARGV) == 0

    github_client.update_title.assert_not_called()


def test_generate_title_with_overwrite_updates_title(monkeypatch, github_client, generate_pr_content):
    generate_pr_content.return_value["title"] = "Better title"
    monkeypatch.setenv("INPUT_GENERATE_TITLE", "true")
    monkeypatch.setenv("INPUT_OVERWRITE_TITLE", "true")

    assert cli.main(BASE_ARGV) == 0

    github_client.update_title.assert_called_once_with(42, "Better title")


def test_breaking_change_prepends_note_and_applies_label(monkeypatch, github_client, generate_pr_content):
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


def test_returns_error_when_get_pull_request_files_fails(github_client, generate_pr_content):
    github_client.get_pull_request_files.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1

    generate_pr_content.assert_not_called()


def test_returns_error_when_update_description_fails(github_client, generate_pr_content):
    github_client.update_description.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1


def test_returns_error_when_update_title_fails(monkeypatch, github_client, generate_pr_content):
    generate_pr_content.return_value["title"] = "Better title"
    monkeypatch.setenv("INPUT_GENERATE_TITLE", "true")
    monkeypatch.setenv("INPUT_OVERWRITE_TITLE", "true")
    github_client.update_title.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1


def test_returns_error_when_label_update_fails(monkeypatch, github_client, generate_pr_content):
    generate_pr_content.return_value["labels"] = ["bug"]
    monkeypatch.setenv("INPUT_ENABLE_LABELS", "true")
    github_client.ensure_labels_exist.side_effect = cli.GitHubApiError("boom")

    assert cli.main(BASE_ARGV) == 1
