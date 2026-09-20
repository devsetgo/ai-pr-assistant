"""Build prompts and call the Anthropic (Claude) Messages API.

The Claude counterpart of :mod:`pr_description.llm`: same two request shapes
(classic few-shot plain text, and JSON-schema-constrained structured mode),
same normalized :class:`~pr_description.llm.PRContent` result, so
:mod:`pr_description.cli` treats both providers alike. The prompts, schema
and result normalization are shared with :mod:`pr_description.llm`; only the
request shape differs (a top-level ``system`` prompt, ``output_config`` for
the schema, and no ``temperature`` - see :func:`generate_pr_content`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

import anthropic
from anthropic.types import MessageParam

from . import llm
from .llm import PRContent

logger = logging.getLogger(__name__)


class AnthropicRefusalError(anthropic.AnthropicError):
    """The model declined the request (``stop_reason == "refusal"``).

    Subclasses :class:`anthropic.AnthropicError` so that :mod:`pr_description.cli`
    reports it like any other failed Anthropic request.
    """


def build_client(api_key: str, max_retries: int = 3) -> anthropic.Anthropic:
    """Construct an Anthropic client for the direct Anthropic API.

    Args:
        api_key: The Anthropic API key.
        max_retries: Number of automatic retries the SDK performs for
            transient failures (rate limits, connection errors, 5xx).

    Returns:
        A ready-to-use Messages API client.
    """
    return anthropic.Anthropic(api_key=api_key, max_retries=max_retries)


def _classic_messages(
    pull_request_title: str,
    completion_prompt: str,
    sample_prompt: str,
    sample_response: str,
) -> list[MessageParam]:
    """Build the few-shot message list for the original plain-text behavior.

    Unlike the OpenAI shape, the system prompt is not a message; it is passed
    separately as ``system=``. Consecutive same-role messages are allowed by
    the API, which merges them into one turn.
    """
    return [
        {"role": "user", "content": sample_prompt},
        {"role": "assistant", "content": sample_response},
        {"role": "user", "content": "Title of the pull request: " + pull_request_title},
        {"role": "user", "content": completion_prompt},
    ]


def _structured_messages(
    pull_request_title: str, completion_prompt: str
) -> list[MessageParam]:
    """Build the message list for the JSON-schema-constrained structured mode."""
    return [
        {"role": "user", "content": "Title of the pull request: " + pull_request_title},
        {"role": "user", "content": completion_prompt},
    ]


def _response_text(response: anthropic.types.Message) -> str:
    """Join the text blocks of ``response``, raising if the model refused.

    Returns an empty string when there is no text block at all, which happens
    when ``max_tokens`` is spent on thinking before any visible output (models
    that think by default, e.g. Sonnet 5 and Opus 5). The caller's existing
    handling of empty and unparseable replies then applies, as with OpenAI's
    reasoning models.

    Raises:
        AnthropicRefusalError: If the response's stop reason is ``refusal``.
    """
    if response.stop_reason == "refusal":
        raise AnthropicRefusalError("The model declined to write a description")
    return "".join(block.text for block in response.content if block.type == "text")


def generate_pr_content(
    client: anthropic.Anthropic,
    model: str,
    pull_request_title: str,
    completion_prompt: str,
    *,
    structured: bool,
    max_tokens: int = 1000,
    sample_prompt: str = llm.SAMPLE_PROMPT,
    sample_response: str = llm.GOOD_SAMPLE_RESPONSE,
    label_taxonomy: Sequence[str] = (),
) -> PRContent:
    """Ask Claude to generate PR content, in classic or structured mode.

    Mirrors :func:`pr_description.llm.generate_pr_content`: in structured
    mode a JSON-schema-constrained request is made first; if the API rejects
    it with a :class:`anthropic.BadRequestError`, or the reply is not valid
    JSON (e.g. truncated at ``max_tokens``), this falls back once to the
    classic plain-text request rather than failing the whole run.

    There is deliberately no ``temperature`` parameter: several current Claude
    models (Sonnet 5, Opus 5/4.8/4.7) reject sampling parameters, and the 1.x
    SDK no longer exposes them on ``messages.create``.

    Args:
        client: A client from :func:`build_client`.
        model: The Claude model to call, e.g. ``"claude-haiku-4-5-20251001"``.
        pull_request_title: The pull request's current title.
        completion_prompt: The assembled prompt describing the change.
        structured: When ``True``, request the JSON-schema response carrying
            title/labels/breaking-change fields; when ``False``, use the
            original plain-text, few-shot behavior.
        max_tokens: Maximum number of output tokens to generate.
        sample_prompt: Few-shot example prompt, classic mode only.
        sample_response: Few-shot example response, classic mode only.
        label_taxonomy: Labels the model may choose from, structured mode
            only. Any model-chosen label outside this list is dropped.

    Returns:
        The generated content, normalized to :class:`PRContent`.

    Raises:
        AnthropicRefusalError: If the model declines the request.
    """
    if structured:
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=llm.structured_system_prompt(label_taxonomy),
                messages=_structured_messages(pull_request_title, completion_prompt),
                # Unlike OpenAI's `response_format`, this takes the bare schema,
                # not the {"name", "strict", "schema"} wrapper.
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": llm.PR_CONTENT_SCHEMA["schema"],
                    }
                },
            )
            payload: dict[str, Any] = json.loads(_response_text(response))
            return llm.parse_structured_payload(payload, label_taxonomy)
        except (anthropic.BadRequestError, json.JSONDecodeError):
            # BadRequestError: the API rejected structured output outright.
            # JSONDecodeError: it accepted it but the reply wasn't valid JSON -
            # empty or cut off at max_tokens.
            logger.warning(
                "Structured PR content request was rejected or returned invalid "
                "JSON, falling back to a plain-text description"
            )

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=llm.CLASSIC_SYSTEM_PROMPT,
        messages=_classic_messages(
            pull_request_title, completion_prompt, sample_prompt, sample_response
        ),
    )
    return llm.plain_result(_response_text(response))
