import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import pytest

from pr_description import llm, llm_anthropic


def _response(*blocks, stop_reason="end_turn"):
    """A minimal stand-in for an Anthropic `Message`."""
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _bad_request():
    return anthropic.BadRequestError(
        "structured outputs not supported",
        response=MagicMock(status_code=400, request=MagicMock()),
        body=None,
    )


def test_build_client_uses_key_and_retries():
    client = llm_anthropic.build_client("sk-ant-test", max_retries=5)

    assert isinstance(client, anthropic.Anthropic)
    assert client.api_key == "sk-ant-test"
    assert client.max_retries == 5


def test_classic_path_returns_plain_description():
    client = MagicMock()
    client.messages.create.return_value = _response(
        _text("This pull request adds a feature")
    )

    result = llm_anthropic.generate_pr_content(
        client,
        "claude-haiku-4-5",
        "Add feature",
        "some diff",
        structured=False,
        max_tokens=1234,
    )

    assert result == {
        "description": "Adds a feature",
        "title": None,
        "labels": [],
        "breaking_change": False,
        "breaking_change_notes": None,
    }
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["max_tokens"] == 1234
    assert kwargs["system"] == llm.CLASSIC_SYSTEM_PROMPT
    assert kwargs["messages"][0]["role"] == "user"
    assert "some diff" in kwargs["messages"][-1]["content"]
    # Sampling parameters are never sent.
    assert "temperature" not in kwargs
    assert "output_config" not in kwargs


def test_classic_path_joins_multiple_text_blocks():
    client = MagicMock()
    client.messages.create.return_value = _response(_text("First. "), _text("Second."))

    result = llm_anthropic.generate_pr_content(
        client, "claude-haiku-4-5", "Title", "diff", structured=False
    )

    assert result["description"] == "First. Second."


def test_classic_path_without_a_text_block_gives_empty_description():
    """e.g. max_tokens spent on thinking; cli.py's empty-description guard handles it."""
    client = MagicMock()
    client.messages.create.return_value = _response(
        SimpleNamespace(type="thinking", thinking=""), stop_reason="max_tokens"
    )

    result = llm_anthropic.generate_pr_content(
        client, "claude-sonnet-5", "Title", "diff", structured=False
    )

    assert result["description"] == ""


def test_structured_path_uses_bare_schema_and_filters_unknown_labels():
    client = MagicMock()
    payload = {
        "description": "This pull request removes the old API",
        "title": "Remove deprecated API",
        "labels": ["bug", "not-a-real-label"],
        "breaking_change": True,
        "breaking_change_notes": "Removed the /v1 endpoint",
    }
    client.messages.create.return_value = _response(_text(json.dumps(payload)))

    result = llm_anthropic.generate_pr_content(
        client,
        "claude-haiku-4-5",
        "Remove old API",
        "some diff",
        structured=True,
        label_taxonomy=["bug", "feature"],
    )

    assert result["description"] == "Removes the old API"
    assert result["title"] == "Remove deprecated API"
    assert result["labels"] == ["bug"]
    assert result["breaking_change"] is True
    assert result["breaking_change_notes"] == "Removed the /v1 endpoint"

    kwargs = client.messages.create.call_args.kwargs
    output_format = kwargs["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    # The bare schema, not OpenAI's {"name", "strict", "schema"} wrapper.
    assert output_format["schema"] == llm.PR_CONTENT_SCHEMA["schema"]
    assert "bug, feature" in kwargs["system"]
    assert [m["role"] for m in kwargs["messages"]] == ["user", "user"]


def test_structured_path_falls_back_when_the_api_rejects_it():
    client = MagicMock()
    client.messages.create.side_effect = [
        _bad_request(),
        _response(_text("Plain text description")),
    ]

    result = llm_anthropic.generate_pr_content(
        client,
        "claude-haiku-4-5",
        "Some title",
        "some diff",
        structured=True,
        label_taxonomy=["bug"],
    )

    assert result["description"] == "Plain text description"
    assert result["title"] is None
    assert client.messages.create.call_count == 2
    assert "output_config" not in client.messages.create.call_args.kwargs


def test_structured_path_falls_back_on_invalid_json():
    client = MagicMock()
    client.messages.create.side_effect = [
        _response(_text('{"description": "cut off'), stop_reason="max_tokens"),
        _response(_text("Plain text description")),
    ]

    result = llm_anthropic.generate_pr_content(
        client, "claude-haiku-4-5", "Title", "diff", structured=True
    )

    assert result["description"] == "Plain text description"
    assert client.messages.create.call_count == 2


@pytest.mark.parametrize("structured", [False, True])
def test_refusal_raises_instead_of_falling_back(structured):
    client = MagicMock()
    client.messages.create.return_value = _response(stop_reason="refusal")

    with pytest.raises(llm_anthropic.AnthropicRefusalError):
        llm_anthropic.generate_pr_content(
            client, "claude-opus-5", "Title", "diff", structured=structured
        )

    assert client.messages.create.call_count == 1


def test_refusal_is_an_anthropic_error():
    """cli.py catches anthropic.AnthropicError, so a refusal must be one."""
    assert issubclass(llm_anthropic.AnthropicRefusalError, anthropic.AnthropicError)
