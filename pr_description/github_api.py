"""A small, retrying GitHub REST API client for the operations this action needs.

Only the handful of endpoints the action actually calls are wrapped here:
reading a pull request and its changed files, updating its description/title,
and managing labels. Everything goes through the "issues" endpoints where
possible since a pull request is also an issue under the GitHub API, which
keeps description/title/label updates on one consistent code path.
"""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

#: A GitHub API JSON object, e.g. a pull request or a label.
JSONDict = dict[str, Any]


class GitHubApiError(RuntimeError):
    """Raised when a GitHub API request fails (a non-2xx response)."""


#: Longest response body included in an error message, so an HTML error page
#: from a proxy can't flood the Actions log.
_MAX_ERROR_BODY_CHARS = 500


def _error_detail(response: requests.Response) -> str:
    """Status code plus the (truncated) response body, for actionable errors.

    GitHub's JSON error body says *why* (e.g. "Resource not accessible by
    integration" for a 403 caused by missing token permissions), which the
    bare status code doesn't.
    """
    return f"{response.status_code}. Response: {response.text[:_MAX_ERROR_BODY_CHARS]}"


def _build_session() -> requests.Session:
    """Build a :class:`requests.Session` that retries transient failures.

    Retries up to 3 times, with exponential backoff, on connection errors
    and the common transient HTTP status codes (rate limiting and server
    errors). GitHub API calls have no built-in retry behavior otherwise,
    unlike the OpenAI SDK client used elsewhere in this project.
    """
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST", "PATCH"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    # Only HTTPS is ever legitimate here (GitHub's API, and GITHUB_API_URL,
    # are always https://) - deliberately not mounting http:// too.
    session.mount("https://", adapter)
    return session


class GitHubClient:
    """Thin wrapper around the subset of the GitHub REST API this action uses."""

    def __init__(
        self,
        api_url: str,
        repo: str,
        token: str,
        session: requests.Session | None = None,
    ) -> None:
        """Create a client for one repository.

        Args:
            api_url: The GitHub API base URL (``GITHUB_API_URL`` in Actions),
                e.g. ``"https://api.github.com"``.
            repo: The ``"owner/name"`` repository slug.
            token: A GitHub token with permission to read the pull request
                and (if used) write its description/title/labels.
            session: An existing :class:`requests.Session` to use instead of
                building a new retrying one; primarily for tests.
        """
        self.api_url = api_url.rstrip("/")
        self.repo = repo
        self.session = session or _build_session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {token}",
            }
        )

    def _pulls_url(self, pull_request_id: int) -> str:
        """Build the ``.../pulls/{id}`` URL for this repo."""
        return f"{self.api_url}/repos/{self.repo}/pulls/{pull_request_id}"

    def _issues_url(self, pull_request_id: int) -> str:
        """Build the ``.../issues/{id}`` URL for this repo.

        A pull request is also an issue in the GitHub data model, so this is
        used for description/title/label operations that live on the issue
        object rather than the pull-request-specific one.
        """
        return f"{self.api_url}/repos/{self.repo}/issues/{pull_request_id}"

    def get_pull_request(self, pull_request_id: int) -> JSONDict:
        """Fetch a pull request's metadata (title, body, author, ...).

        Raises:
            GitHubApiError: If the request does not succeed.
        """
        response = self.session.get(self._pulls_url(pull_request_id))
        if not response.ok:
            raise GitHubApiError(
                f"Request to get pull request data failed: {_error_detail(response)}"
            )
        return response.json()

    def get_pull_request_files(self, pull_request_id: int) -> list[JSONDict]:
        """Fetch every changed-file entry for a pull request.

        Follows the response's ``Link: rel="next"`` header until GitHub
        reports no further pages, rather than guessing a fixed page count -
        so this scales correctly to pull requests with any number of files.

        Raises:
            GitHubApiError: If any page request does not succeed.
        """
        files: list[JSONDict] = []
        url: str | None = f"{self._pulls_url(pull_request_id)}/files?per_page=100"
        while url:
            response = self.session.get(url)
            if not response.ok:
                raise GitHubApiError(
                    "Request to get list of files failed with error code: "
                    f"{_error_detail(response)}"
                )
            files.extend(response.json())
            url = response.links.get("next", {}).get("url")
        return files

    def update_description(self, pull_request_id: int, body: str) -> None:
        """Overwrite a pull request's description (body).

        Raises:
            GitHubApiError: If the request does not succeed.
        """
        self._patch_issue(pull_request_id, {"body": body})

    def update_title(self, pull_request_id: int, title: str) -> None:
        """Overwrite a pull request's title.

        Raises:
            GitHubApiError: If the request does not succeed.
        """
        self._patch_issue(pull_request_id, {"title": title})

    def _patch_issue(self, pull_request_id: int, payload: JSONDict) -> None:
        """Send a ``PATCH`` to the issue endpoint backing this pull request."""
        response = self.session.patch(self._issues_url(pull_request_id), json=payload)
        if not response.ok:
            raise GitHubApiError(
                f"Request to update pull request failed: {_error_detail(response)}"
            )

    def list_label_names(self) -> set[str]:
        """Return the names of every label that already exists in the repo.

        Raises:
            GitHubApiError: If any page request does not succeed.
        """
        names: set[str] = set()
        url: str | None = f"{self.api_url}/repos/{self.repo}/labels?per_page=100"
        while url:
            response = self.session.get(url)
            if not response.ok:
                raise GitHubApiError(
                    f"Request to list labels failed: {_error_detail(response)}"
                )
            names.update(label["name"] for label in response.json())
            url = response.links.get("next", {}).get("url")
        return names

    def ensure_labels_exist(self, labels: list[str], color: str = "ededed") -> None:
        """Create any of ``labels`` that don't already exist in the repo.

        GitHub's "add labels to an issue" endpoint returns a 404 for a label
        name that doesn't already exist in the repository, so any
        model-chosen label has to be created here first.

        Args:
            labels: Label names to ensure exist.
            color: Hex color (without ``#``) used for newly created labels.

        Raises:
            GitHubApiError: If creating a label fails for a reason other than
                it already existing.
        """
        existing = self.list_label_names()
        for label in labels:
            if label in existing:
                continue
            response = self.session.post(
                f"{self.api_url}/repos/{self.repo}/labels",
                json={"name": label, "color": color},
            )
            # 422 means the label was created concurrently (e.g. another
            # workflow run) between the check above and this request.
            if not response.ok and response.status_code != 422:
                raise GitHubApiError(
                    f"Request to create label '{label}' failed: {_error_detail(response)}"
                )

    def add_labels(self, pull_request_id: int, labels: list[str]) -> None:
        """Apply ``labels`` to a pull request. A no-op if ``labels`` is empty.

        Callers should ensure the labels already exist first, e.g. via
        :meth:`ensure_labels_exist`.

        Raises:
            GitHubApiError: If the request does not succeed.
        """
        if not labels:
            return
        response = self.session.post(
            f"{self._issues_url(pull_request_id)}/labels",
            json={"labels": labels},
        )
        if not response.ok:
            raise GitHubApiError(
                f"Request to add labels failed: {_error_detail(response)}"
            )
