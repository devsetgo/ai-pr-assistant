"""Decide what to do with the content a pull request already has.

Holds the provider-neutral rules behind the ``overwrite_*`` inputs: parsing the
always/never/smart modes, separating the text this action added to a
description from the text being reviewed, and spotting placeholder titles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ALWAYS: str = "always"
NEVER: str = "never"
SMART: str = "smart"

#: Input values accepted as aliases, since ``overwrite_description`` and
#: ``overwrite_title`` were booleans before they gained a third mode.
_MODE_ALIASES: dict[str, str] = {
    ALWAYS: ALWAYS,
    "1": ALWAYS,
    "true": ALWAYS,
    "yes": ALWAYS,
    "on": ALWAYS,
    NEVER: NEVER,
    "": NEVER,
    "0": NEVER,
    "false": NEVER,
    "no": NEVER,
    "off": NEVER,
    SMART: SMART,
}

#: Footer appended to the description when `attribution` is on. Added after
#: generation, rather than requested in the prompt, so the model can't drop it,
#: reword it, or invent a model name.
ATTRIBUTION_TEMPLATE: str = (
    "\n\n---\n<sub>Created using "
    "[devsetgo/ai-pr-assistant](https://github.com/devsetgo/ai-pr-assistant) "
    "with {model}</sub>"
)

_ATTRIBUTION_RE = re.compile(
    r"\s*---\n<sub>Created using \[devsetgo/ai-pr-assistant\].*?</sub>\s*\Z", re.DOTALL
)
#: The current callout form, then the emoji line older versions of this action
#: wrote, so descriptions from those versions don't end up with two notes.
_BREAKING_NOTE_RE = re.compile(
    r"\A(?:> \[!CAUTION\]\n> \*\*Potential breaking change:\*\*.*(?:\n>.*)*"
    r"|⚠️ \*\*Potential breaking change:\*\*(?:.|\n(?!\n))*)\s*"
)

#: Titles too generic to describe any change, compared after normalizing.
_PLACEHOLDER_TITLES: frozenset[str] = frozenset(
    {
        "",
        "change",
        "changes",
        "dev",
        "develop",
        "development",
        "draft",
        "fix",
        "fixes",
        "main",
        "master",
        "misc",
        "patch",
        "pr",
        "tbd",
        "test",
        "tests",
        "todo",
        "update",
        "updates",
        "wip",
    }
)


@dataclass(frozen=True)
class ExistingDescription:
    """A pull request body, split into what this action added and the rest.

    Attributes:
        raw: The whole body, with line endings normalized.
        note: The breaking-change note this action prepended, or ``""``.
        text: The body without that note or the attribution footer.
    """

    raw: str
    note: str
    text: str


def parse_overwrite_mode(value: str) -> str | None:
    """Resolve an ``overwrite_*`` input to a mode, or ``None`` if unrecognized."""
    return _MODE_ALIASES.get(value.strip().lower())


def split_description(body: str | None) -> ExistingDescription:
    """Separate this action's note and footer from the rest of ``body``.

    Bodies edited in GitHub's web UI come back with CRLF line endings, which
    would otherwise defeat both the patterns here and later equality checks.
    """
    raw = (body or "").replace("\r\n", "\n")
    without_footer = _ATTRIBUTION_RE.sub("", raw)
    match = _BREAKING_NOTE_RE.match(without_footer)
    note = match.group(0).strip() if match else ""
    text = without_footer[match.end() :] if match else without_footer
    return ExistingDescription(raw=raw, note=note, text=text.strip())


def format_breaking_note(note: str | None) -> str:
    """Render a breaking-change note as a GitHub caution callout."""
    message = note or "This change may break existing consumers."
    quoted = message.strip().replace("\n", "\n> ")
    return f"> [!CAUTION]\n> **Potential breaking change:** {quoted}"


def compose_description(text: str, note: str, footer: str) -> str:
    """Assemble a final description from its note, text and footer."""
    return (f"{note}\n\n" if note else "") + text + footer


def _normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def is_placeholder_title(title: str, branch: str = "") -> bool:
    """Whether ``title`` says nothing about the change.

    True for a blank or stock title, and for one that only restates the branch
    name, which is what GitHub proposes for a pull request with several commits.
    """
    normalized = _normalized(title)
    return normalized in _PLACEHOLDER_TITLES or normalized == _normalized(branch)
