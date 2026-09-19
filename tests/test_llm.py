import json
from unittest.mock import MagicMock

import openai
import pytest

from pr_description import llm


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-5-mini", True),
        ("gpt-5", True),
        ("o1-preview", True),
        ("o3-mini", True),
        ("gpt-4o-mini", False),
        ("gpt-4o", False),
    ],
)
def test_is_reasoning_model_detection(model, expected):
    assert llm.is_reasoning_model(model) is expected


def test_is_reasoning_model_override_wins():
    assert llm.is_reasoning_model("gpt-4o-mini", override=True) is True
    assert llm.is_reasoning_model("gpt-5-mini", override=False) is False


def test_completion_kwargs_for_reasoning_model_omits_temperature():
    kwargs = llm._completion_kwargs(
        "gpt-5-mini", temperature=0.6, max_tokens=500, reasoning_override=None
    )
    assert kwargs == {"max_completion_tokens": 500}


def test_completion_kwargs_for_classic_model_includes_temperature():
    kwargs = llm._completion_kwargs(
        "gpt-4o-mini", temperature=0.6, max_tokens=500, reasoning_override=None
    )
    assert kwargs == {"max_tokens": 500, "temperature": 0.6}


def test_strip_redundant_prefix():
    assert llm.strip_redundant_prefix("This pull request adds X") == "Adds X"
    assert llm.strip_redundant_prefix("Adds X") == "Adds X"


def _mock_response(content):
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


def test_generate_pr_content_classic_path():
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response(
        "This pull request adds a feature"
    )

    result = llm.generate_pr_content(
        client,
        "gpt-4o-mini",
        "Add feature",
        "some diff",
        structured=False,
    )

    assert result == {
        "description": "Adds a feature",
        "title": None,
        "labels": [],
        "breaking_change": False,
        "breaking_change_notes": None,
    }
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "temperature" in kwargs
    assert "response_format" not in kwargs


def test_generate_pr_content_structured_path_filters_unknown_labels():
    client = MagicMock()
    payload = {
        "description": "This pull request removes the old API",
        "title": "Remove deprecated API",
        "labels": ["bug", "not-a-real-label"],
        "breaking_change": True,
        "breaking_change_notes": "Removed the /v1 endpoint",
    }
    client.chat.completions.create.return_value = _mock_response(json.dumps(payload))

    result = llm.generate_pr_content(
        client,
        "gpt-5-mini",
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

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert "max_completion_tokens" in kwargs
    assert "temperature" not in kwargs


def test_generate_pr_content_falls_back_when_structured_output_rejected():
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        openai.BadRequestError(
            "structured outputs not supported",
            response=MagicMock(status_code=400, request=MagicMock()),
            body=None,
        ),
        _mock_response("Plain text description"),
    ]

    result = llm.generate_pr_content(
        client,
        "gpt-4o-mini",
        "Some title",
        "some diff",
        structured=True,
        label_taxonomy=["bug"],
    )

    assert result["description"] == "Plain text description"
    assert result["title"] is None
    assert client.chat.completions.create.call_count == 2


def test_build_client_uses_openai_when_no_azure_endpoint(monkeypatch):
    openai_client = object()
    mock_openai = MagicMock(return_value=openai_client)
    monkeypatch.setattr(llm.openai, "OpenAI", mock_openai)

    client = llm.build_client("k", max_retries=9)

    assert client is openai_client
    mock_openai.assert_called_once_with(api_key="k", max_retries=9)


def test_build_client_uses_azure_client_when_endpoint_set(monkeypatch):
    azure_client = object()
    mock_azure = MagicMock(return_value=azure_client)
    monkeypatch.setattr(llm.openai, "AzureOpenAI", mock_azure)

    client = llm.build_client(
        "k", azure_endpoint="https://example.azure.com", azure_api_version="2024-06-01"
    )

    assert client is azure_client
    mock_azure.assert_called_once_with(
        api_key="k",
        azure_endpoint="https://example.azure.com",
        api_version="2024-06-01",
        max_retries=3,
    )


def test_require_content_raises_on_none():
    with pytest.raises(ValueError):
        llm._require_content(None)
