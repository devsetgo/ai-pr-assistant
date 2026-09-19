from unittest.mock import MagicMock

import pytest

from pr_description.github_api import GitHubApiError, GitHubClient


def _response(status_code=200, json_data=None, text="", links=None):
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json.return_value = json_data if json_data is not None else {}
    response.text = text
    response.links = links or {}
    return response


@pytest.fixture
def client():
    session = MagicMock()
    return GitHubClient("https://api.github.com", "acme/widgets", "token123", session=session)


def test_get_pull_request_returns_json(client):
    client.session.get.return_value = _response(json_data={"title": "Add thing"})
    assert client.get_pull_request(42) == {"title": "Add thing"}


def test_get_pull_request_raises_on_error(client):
    client.session.get.return_value = _response(status_code=404)
    with pytest.raises(GitHubApiError):
        client.get_pull_request(42)


def test_get_pull_request_files_follows_link_header_pagination(client):
    page1 = _response(
        json_data=[{"filename": "a.py"}],
        links={"next": {"url": "https://api.github.com/.../files?page=2"}},
    )
    page2 = _response(json_data=[{"filename": "b.py"}], links={})
    client.session.get.side_effect = [page1, page2]

    files = client.get_pull_request_files(42)

    assert files == [{"filename": "a.py"}, {"filename": "b.py"}]
    assert client.session.get.call_count == 2


def test_update_description_patches_issue_endpoint(client):
    client.session.patch.return_value = _response()
    client.update_description(42, "new body")
    url, kwargs = client.session.patch.call_args
    assert url[0].endswith("/issues/42")
    assert kwargs["json"] == {"body": "new body"}


def test_ensure_labels_exist_only_creates_missing_labels(client):
    client.session.get.return_value = _response(json_data=[{"name": "bug"}])
    client.session.post.return_value = _response(status_code=201)

    client.ensure_labels_exist(["bug", "enhancement"])

    # "bug" already exists, only "enhancement" should be created
    assert client.session.post.call_count == 1
    _, kwargs = client.session.post.call_args
    assert kwargs["json"]["name"] == "enhancement"


def test_ensure_labels_exist_tolerates_concurrent_creation(client):
    client.session.get.return_value = _response(json_data=[])
    client.session.post.return_value = _response(status_code=422)

    # Should not raise even though the create call "failed" with 422.
    client.ensure_labels_exist(["bug"])


def test_add_labels_noop_for_empty_list(client):
    client.add_labels(42, [])
    client.session.post.assert_not_called()


def test_add_labels_posts_to_issue_labels_endpoint(client):
    client.session.post.return_value = _response()
    client.add_labels(42, ["bug", "breaking-change"])
    url, kwargs = client.session.post.call_args
    assert url[0].endswith("/issues/42/labels")
    assert kwargs["json"] == {"labels": ["bug", "breaking-change"]}
