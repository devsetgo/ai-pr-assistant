"""Turn a pull request's file diffs into a size-bounded model prompt.

Two independent concerns live here: dropping files that match a glob
exclude-list (lockfiles, generated code, binary assets, ...), and trimming
the remaining diff text down to a token budget using the target model's own
tokenizer instead of a rough character-count guess.
"""

from __future__ import annotations

import fnmatch
from typing import Any

import tiktoken

#: Glob patterns excluded from the diff prompt by default. These tend to be
#: large, machine-generated, or non-textual, and mostly waste token budget
#: without helping the model explain *why* a change was made.
DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "*.min.js",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "dist/*",
    "build/*",
)

#: Encoding used when the installed tiktoken version doesn't yet recognize
#: a given model name (e.g. a model released after tiktoken was pinned).
#: This is the encoding used by current GPT-4o/GPT-5-family models.
_FALLBACK_ENCODING: str = "o200k_base"


def parse_patterns(patterns_csv: str) -> list[str]:
    """Parse a comma-separated glob pattern list (an action input) into a list.

    Args:
        patterns_csv: Comma-separated glob patterns, e.g. ``"*.lock,dist/*"``.
            Whitespace around each pattern is stripped and empty entries are
            dropped.

    Returns:
        The individual patterns, in the order given. Empty when
        ``patterns_csv`` is empty or blank.
    """
    if not patterns_csv:
        return []
    return [pattern.strip() for pattern in patterns_csv.split(",") if pattern.strip()]


def is_excluded(filename: str, patterns: list[str]) -> bool:
    """Return whether ``filename`` matches any of the glob ``patterns``.

    Args:
        filename: A file path as reported by the GitHub API (repo-relative).
        patterns: Glob patterns to test against, as returned by
            :func:`parse_patterns`.

    Returns:
        ``True`` if ``filename`` matches at least one pattern.
    """
    return any(fnmatch.fnmatch(filename, pattern) for pattern in patterns)


def get_encoding(model: str) -> tiktoken.Encoding:
    """Look up the tiktoken encoding used to count tokens for ``model``.

    Args:
        model: An OpenAI model name, e.g. ``"gpt-5-mini"``.

    Returns:
        The model's tiktoken encoding, or the :data:`_FALLBACK_ENCODING`
        encoding when the installed tiktoken version doesn't recognize the
        model name yet, so newly released models don't crash token counting.
    """
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding(_FALLBACK_ENCODING)


def count_tokens(text: str, encoding: tiktoken.Encoding) -> int:
    """Count how many tokens ``text`` encodes to under ``encoding``."""
    return len(encoding.encode(text))


def build_diff_prompt(
    files: list[dict[str, Any]],
    exclude_patterns: list[str],
    max_diff_tokens: int,
    model: str,
) -> str:
    """Concatenate per-file diff chunks into a single, token-bounded prompt.

    Each GitHub "pull request file" entry becomes a
    ``"Changes in file <name>: <patch>\\n"`` chunk. Files without a
    ``"patch"`` key (e.g. removed binary files) and files matching
    ``exclude_patterns`` are skipped entirely. Chunks are appended until
    ``max_diff_tokens`` (counted with the real tokenizer for ``model``, not a
    character-count guess) would be exceeded; the file that crosses the
    budget is truncated to fit exactly rather than dropped outright, so the
    model sees partial context instead of none.

    Args:
        files: Raw "list pull request files" entries from the GitHub API,
            each expected to have at least a ``"filename"`` key and
            optionally a ``"patch"`` key.
        exclude_patterns: Glob patterns; a matching filename is skipped.
        max_diff_tokens: Maximum number of tokens the returned prompt may
            spend on diff content.
        model: The model name whose tokenizer should be used for counting.

    Returns:
        The concatenated, budget-truncated diff prompt. Empty if every file
        was excluded or lacked a patch, or if ``max_diff_tokens`` is ``0``.
    """
    encoding = get_encoding(model)
    chunks: list[str] = []
    used_tokens = 0

    for pull_request_file in files:
        # Not all PR file metadata entries contain a patch section, e.g.
        # entries related to removed binary files.
        if "patch" not in pull_request_file:
            continue

        filename: str = pull_request_file["filename"]
        if is_excluded(filename, exclude_patterns):
            continue

        chunk = f"Changes in file {filename}: {pull_request_file['patch']}\n"
        chunk_tokens = count_tokens(chunk, encoding)
        remaining = max_diff_tokens - used_tokens

        if chunk_tokens > remaining:
            if remaining > 0:
                truncated_tokens = encoding.encode(chunk)[:remaining]
                chunks.append(encoding.decode(truncated_tokens))
            break

        chunks.append(chunk)
        used_tokens += chunk_tokens

    return "".join(chunks)
