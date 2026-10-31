import pytest

from pr_description import existing_content as ec

FOOTER = ec.ATTRIBUTION_TEMPLATE.format(model="gpt-5-mini")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("always", ec.ALWAYS),
        (" TRUE ", ec.ALWAYS),
        ("never", ec.NEVER),
        ("false", ec.NEVER),
        ("", ec.NEVER),
        ("Smart", ec.SMART),
        ("sometimes", None),
    ],
)
def test_parse_overwrite_mode(value, expected):
    assert ec.parse_overwrite_mode(value) == expected


@pytest.mark.parametrize("body", [None, "", "   ", FOOTER, FOOTER.strip()])
def test_split_description_finds_no_text_in_blank_or_footer_only_bodies(body):
    assert ec.split_description(body).text == ""


def test_split_description_strips_current_note_and_footer():
    note = ec.format_breaking_note("Removed /v1\nand /v2")
    body = ec.compose_description("Human text", note, FOOTER)

    existing = ec.split_description(body)

    assert existing.text == "Human text"
    assert existing.note == note
    assert existing.raw == body


def test_split_description_strips_the_older_emoji_note():
    body = "⚠️ **Potential breaking change:** Removed /v1\n\nHuman text"

    existing = ec.split_description(body)

    assert existing.text == "Human text"
    assert "Removed /v1" in existing.note


def test_split_description_leaves_a_persons_own_callout_alone():
    body = "> [!CAUTION]\n> Do not merge on Fridays\n\nHuman text"

    existing = ec.split_description(body)

    assert existing.note == ""
    assert existing.text == body


def test_split_description_handles_crlf_from_the_web_ui():
    note = ec.format_breaking_note("Removed /v1")
    body = ec.compose_description("Human\ntext", note, FOOTER).replace("\n", "\r\n")

    existing = ec.split_description(body)

    assert existing.text == "Human\ntext"
    assert existing.note == note


def test_format_breaking_note_defaults_and_quotes_every_line():
    assert "may break existing consumers" in ec.format_breaking_note(None)
    assert ec.format_breaking_note("a\nb") == (
        "> [!CAUTION]\n> **Potential breaking change:** a\n> b"
    )


@pytest.mark.parametrize(
    ("title", "branch", "expected"),
    [
        ("", "", True),
        ("dev", "feat/x", True),
        ("  DEV ", "feat/x", True),
        ("WIP:", "feat/x", True),
        ("Feat/265 material design", "feat/265-material-design", True),
        ("Add dark mode toggle", "feat/dark-mode", False),
    ],
)
def test_is_placeholder_title(title, branch, expected):
    assert ec.is_placeholder_title(title, branch) is expected


def test_split_description_keeps_text_written_after_the_footer():
    body = f"Human text{FOOTER}\n\nMore from a person"

    assert ec.split_description(body).text == body


def test_split_description_keeps_a_body_merely_ending_in_sub_tags():
    body = "Human text <sub>small print</sub>"

    assert ec.split_description(body).text == body
