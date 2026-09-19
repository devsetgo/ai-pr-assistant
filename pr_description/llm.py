"""Build prompts and call the OpenAI (or Azure OpenAI) chat completions API.

Two request shapes are supported:

- **Classic**: the original plain-text behavior - a few-shot example
  (``SAMPLE_PROMPT``/``GOOD_SAMPLE_RESPONSE``) followed by the real prompt,
  returning a plain-text description. Used when none of the new opt-in
  features (title generation, labeling, breaking-change detection) are
  enabled, so existing users see no behavior change.
- **Structured**: a JSON-schema-constrained response
  (``PR_CONTENT_SCHEMA``) carrying the description plus title/labels/
  breaking-change fields in one call. Used as soon as any of those features
  is turned on.

Model-family quirks (GPT-5/o-series "reasoning" models reject a custom
``temperature`` and require ``max_completion_tokens`` instead of
``max_tokens``) are handled centrally in :func:`_completion_kwargs` so
callers don't need to know about them.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, TypedDict

import openai
from openai.types.chat import ChatCompletionMessageParam

logger = logging.getLogger(__name__)

#: An OpenAI or Azure OpenAI client - the two are interchangeable for the
#: ``chat.completions.create`` calls made in this module.
OpenAIClient = openai.OpenAI | openai.AzureOpenAI

#: Model name prefixes for "reasoning" models. These reject a custom
#: `temperature` and require `max_completion_tokens` instead of `max_tokens`
#: on the Chat Completions endpoint.
REASONING_MODEL_PREFIXES: tuple[str, ...] = ("gpt-5", "o1", "o3", "o4")

#: Prefix the model tends to open descriptions with; stripped for a tighter
#: result since the PR body already makes clear it's describing this PR.
REDUNDANT_PREFIX: str = "This pull request "

SAMPLE_PROMPT = """
Write a pull request description focusing on the motivation behind the change and why it improves the project.
Go straight to the point.

The title of the pull request is "Enable valgrind on CI" and the following changes took place:

Changes in file .github/workflows/build-ut-coverage.yml: @@ -24,6 +24,7 @@ jobs:
        run: |
          sudo apt-get update
          sudo apt-get install -y lcov
+          sudo apt-get install -y valgrind
          sudo apt-get install -y ${{ matrix.compiler.cc }}
          sudo apt-get install -y ${{ matrix.compiler.cxx }}
      - name: Checkout repository
@@ -48,3 +49,7 @@ jobs:
        with:
          files: coverage.info
          fail_ci_if_error: true
+      - name: Run valgrind
+        run: |
+          valgrind --tool=memcheck --leak-check=full --leak-resolution=med \
+            --track-origins=yes --vgdb=no --error-exitcode=1 ${build_dir}/test/command_parser_test
Changes in file test/CommandParserTest.cpp: @@ -566,7 +566,7 @@ TEST(CommandParserTest, ParsedCommandImpl_WhenArgumentIsSupportedNumericTypeWill
    unsigned long long expectedUnsignedLongLong { std::numeric_limits<unsigned long long>::max() };
    float expectedFloat { -164223.123f }; // std::to_string does not play well with floating point min()
    double expectedDouble { std::numeric_limits<double>::max() };
-    long double expectedLongDouble { std::numeric_limits<long double>::max() };
+    long double expectedLongDouble { 123455678912349.1245678912349L };

    auto command = UnparsedCommand::create(expectedCommand, "dummyDescription"s)
                       .withArgs<int, long, unsigned long, long long, unsigned long long, float, double, long double>();
"""

GOOD_SAMPLE_RESPONSE = """
Currently, our CI build does not include Valgrind as part of the build and test process. Valgrind is a powerful tool for detecting memory errors, and its use is essential for maintaining the integrity of our project.
This pull request adds Valgrind to the CI build, so that any memory errors will be detected and reported immediately. This will help to prevent undetected memory errors from making it into the production build.

Overall, this change will improve the quality of the project by helping us detect and prevent memory errors.
"""

COMPLETION_PROMPT = """
Write a pull request description focusing on the motivation behind the change and why it improves the project.
Go straight to the point. The following changes took place: \n
"""

#: JSON schema for the "structured" response mode, passed as
#: ``response_format={"type": "json_schema", "json_schema": PR_CONTENT_SCHEMA}``.
#: All fields are always requested regardless of which opt-in features are
#: enabled; the caller decides which fields to actually use, which keeps this
#: schema single and static instead of assembled dynamically per call.
PR_CONTENT_SCHEMA: dict[str, Any] = {
    "name": "pr_content",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "A one-to-two sentence summary followed by a bulleted list of key points, per the system prompt's formatting rules.",
            },
            "title": {
                "type": ["string", "null"],
                "description": "A Title Case title prefixed with its category (e.g. 'Enhancement: ...', 'Bug: ...'), per the system prompt's formatting rules.",
            },
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Labels that apply to this change, chosen from the allowed taxonomy.",
            },
            "breaking_change": {
                "type": "boolean",
                "description": "True if the change could break existing consumers of the project.",
            },
            "breaking_change_notes": {
                "type": ["string", "null"],
                "description": "A short explanation of the breaking change, or null when breaking_change is false.",
            },
        },
        "required": [
            "description",
            "title",
            "labels",
            "breaking_change",
            "breaking_change_notes",
        ],
        "additionalProperties": False,
    },
}


class PRContent(TypedDict):
    """The normalized result of :func:`generate_pr_content`.

    Populated the same way regardless of whether the classic or structured
    request path was used, so callers never need to branch on that.
    """

    description: str
    title: str | None
    labels: list[str]
    breaking_change: bool
    breaking_change_notes: str | None


#: A single OpenAI chat message, e.g. ``{"role": "user", "content": "..."}``.
ChatMessage = ChatCompletionMessageParam


def is_reasoning_model(model: str, override: bool | None = None) -> bool:
    """Decide whether ``model`` is a "reasoning" model needing different params.

    Args:
        model: The model name, e.g. ``"gpt-5-mini"`` or ``"gpt-4o-mini"``.
        override: When not ``None``, this value is returned as-is instead of
            inspecting ``model`` - an escape hatch for model names released
            after :data:`REASONING_MODEL_PREFIXES` was last updated.

    Returns:
        ``True`` if ``model`` should be treated as a reasoning model.
    """
    if override is not None:
        return override
    return model.lower().startswith(REASONING_MODEL_PREFIXES)


def build_client(
    api_key: str,
    azure_endpoint: str = "",
    azure_api_version: str = "",
    max_retries: int = 3,
) -> OpenAIClient:
    """Construct an OpenAI or Azure OpenAI client, depending on the inputs.

    Args:
        api_key: The OpenAI (or Azure OpenAI) API key.
        azure_endpoint: The Azure OpenAI resource endpoint. When non-empty,
            an :class:`openai.AzureOpenAI` client is returned instead of a
            plain :class:`openai.OpenAI` one.
        azure_api_version: The Azure OpenAI API version to target. Only used
            when ``azure_endpoint`` is set.
        max_retries: Number of automatic retries the SDK performs for
            transient failures (rate limits, connection errors, 5xx).

    Returns:
        A ready-to-use chat completions client.
    """
    if azure_endpoint:
        return openai.AzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=azure_api_version,
            max_retries=max_retries,
        )
    return openai.OpenAI(api_key=api_key, max_retries=max_retries)


def strip_redundant_prefix(text: str) -> str:
    """Strip a leading ``"This pull request "`` and re-capitalize, if present."""
    if text.startswith(REDUNDANT_PREFIX):
        text = text[len(REDUNDANT_PREFIX) :]
        text = text[0].upper() + text[1:]
    return text


def _completion_kwargs(
    model: str,
    temperature: float,
    max_tokens: int,
    reasoning_override: bool | None,
) -> dict[str, Any]:
    """Build the model-family-appropriate ``chat.completions.create`` kwargs.

    Reasoning models (see :func:`is_reasoning_model`) reject a custom
    ``temperature`` and use ``max_completion_tokens`` instead of
    ``max_tokens``; classic chat models use the original pair.
    """
    if is_reasoning_model(model, reasoning_override):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens, "temperature": temperature}


def _classic_messages(
    pull_request_title: str,
    completion_prompt: str,
    sample_prompt: str,
    sample_response: str,
) -> list[ChatMessage]:
    """Build the few-shot message list for the original plain-text behavior."""
    return [
        {
            "role": "system",
            "content": "You are a helpful assistant who writes pull request descriptions",
        },
        {"role": "user", "content": sample_prompt},
        {"role": "assistant", "content": sample_response},
        {"role": "user", "content": "Title of the pull request: " + pull_request_title},
        {"role": "user", "content": completion_prompt},
    ]


def _structured_messages(
    pull_request_title: str,
    completion_prompt: str,
    label_taxonomy: Sequence[str],
) -> list[ChatMessage]:
    """Build the message list for the JSON-schema-constrained structured mode.

    No few-shot example pair is included here (unlike :func:`_classic_messages`):
    the JSON schema itself constrains the response shape, and a plain-text
    few-shot example would actively mislead the model about the expected
    format.
    """
    system_content = (
        "You are a helpful assistant who writes pull request descriptions and prepares "
        "metadata about them. Respond only with JSON matching the given schema.\n"
        "- description: start with a one-to-two sentence summary of the change and why "
        "it matters, then a blank line, then a bulleted list (each line starting with "
        "'- ') of the key points. Group bullets under short bold subheadings (e.g. "
        "**CI/CD**, **Documentation**, **Dependencies**) when the change spans multiple "
        "distinct areas. Keep each bullet to one line and focus on why it matters, not "
        "just what changed.\n"
        "- title: an improved pull request title, always in Title Case (capitalize each "
        "significant word; keep short connector words like 'a', 'an', 'and', 'the', "
        "'for', 'in', 'of', 'on', 'to' lowercase unless first), prefixed with the single "
        "most representative category from the label taxonomy followed by a colon and a "
        "space - e.g. 'Enhancement: Add Dark Mode Toggle' or 'Bug: Fix Crash On Empty "
        "Input'. Use 'Breaking Change:' instead of a taxonomy category when "
        "breaking_change is true. Always produce a title in this format, even if that "
        "means only reformatting/re-prefixing the existing title.\n"
        "- labels: choose zero or more labels strictly from this list: "
        f"{', '.join(label_taxonomy) if label_taxonomy else '(none available)'}.\n"
        "- breaking_change: true only if the change could break existing consumers, "
        "e.g. removed/renamed public APIs, changed request/response schemas, changed "
        "defaults, or config/migrations that require manual action downstream.\n"
        "- breaking_change_notes: a short explanation when breaking_change is true, "
        "otherwise null."
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "Title of the pull request: " + pull_request_title},
        {"role": "user", "content": completion_prompt},
    ]


def _require_content(text: str | None) -> str:
    """Guard against the SDK's `message.content` being `None`.

    This happens for responses that only carry e.g. a tool call - not
    expected here since no tools are offered, but worth failing on loudly
    rather than passing `None` further into string-only helpers.
    """
    if text is None:
        raise ValueError("The model returned an empty (contentless) message")
    return text


def _plain_result(text: str) -> PRContent:
    """Wrap a plain-text completion in the common :class:`PRContent` shape."""
    return {
        "description": strip_redundant_prefix(text),
        "title": None,
        "labels": [],
        "breaking_change": False,
        "breaking_change_notes": None,
    }


def generate_pr_content(
    client: OpenAIClient,
    model: str,
    pull_request_title: str,
    completion_prompt: str,
    *,
    structured: bool,
    temperature: float = 0.6,
    max_tokens: int = 1000,
    sample_prompt: str = SAMPLE_PROMPT,
    sample_response: str = GOOD_SAMPLE_RESPONSE,
    label_taxonomy: Sequence[str] = (),
    reasoning_override: bool | None = None,
) -> PRContent:
    """Ask the model to generate PR content, in classic or structured mode.

    In structured mode, a JSON-schema-constrained request is made first
    (see :data:`PR_CONTENT_SCHEMA`); if the API rejects it with a
    :class:`openai.BadRequestError` (e.g. an older Azure deployment/API
    version without structured-output support), this falls back once to the
    classic plain-text request rather than failing the whole run.

    Args:
        client: A client from :func:`build_client`.
        model: The model name to call.
        pull_request_title: The pull request's current title, included in
            every prompt for context.
        completion_prompt: The assembled prompt describing the change (task
            instructions plus the diff content).
        structured: When ``True``, request the JSON-schema response carrying
            title/labels/breaking-change fields; when ``False``, use the
            original plain-text, few-shot behavior.
        temperature: Sampling temperature for classic (non-reasoning) models.
        max_tokens: Maximum number of output tokens to generate.
        sample_prompt: Few-shot example prompt, classic mode only.
        sample_response: Few-shot example response, classic mode only.
        label_taxonomy: Labels the model may choose from, structured mode
            only. Any model-chosen label outside this list is dropped.
        reasoning_override: Forwarded to :func:`is_reasoning_model`.

    Returns:
        The generated content, normalized to :class:`PRContent` regardless
        of which request path was actually used.
    """
    kwargs = _completion_kwargs(model, temperature, max_tokens, reasoning_override)

    if structured:
        try:
            # mypy can't resolve **kwargs against chat.completions.create's
            # stream-overloaded signature once response_format is also
            # passed; the arguments themselves are valid at runtime.
            response = client.chat.completions.create(  # type: ignore[call-overload]
                model=model,
                messages=_structured_messages(pull_request_title, completion_prompt, label_taxonomy),
                response_format={"type": "json_schema", "json_schema": PR_CONTENT_SCHEMA},
                **kwargs,
            )
            payload: dict[str, Any] = json.loads(_require_content(response.choices[0].message.content))
            return {
                "description": strip_redundant_prefix(payload.get("description", "")),
                "title": payload.get("title") or None,
                "labels": [
                    label for label in (payload.get("labels") or []) if label in label_taxonomy
                ],
                "breaking_change": bool(payload.get("breaking_change")),
                "breaking_change_notes": payload.get("breaking_change_notes") or None,
            }
        except openai.BadRequestError:
            logger.warning(
                "Structured PR content request was rejected by the API, "
                "falling back to a plain-text description"
            )

    response = client.chat.completions.create(
        model=model,
        messages=_classic_messages(pull_request_title, completion_prompt, sample_prompt, sample_response),
        **kwargs,
    )
    return _plain_result(_require_content(response.choices[0].message.content))
