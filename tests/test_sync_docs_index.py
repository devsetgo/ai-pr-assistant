from pathlib import Path

import pytest

from scripts import sync_docs_index


def test_render_strips_docs_prefix_from_links_images_and_badges():
    readme = (
        "[guide](docs/SETUP.md)\n"
        "![shot](docs/media/repo-1.png)\n"
        "[![badge](docs/badges/tests-badge.svg)](https://example.com/run)\n"
    )

    rendered = sync_docs_index.render(readme)

    assert "[guide](SETUP.md)" in rendered
    assert "![shot](media/repo-1.png)" in rendered
    assert "[![badge](badges/tests-badge.svg)](https://example.com/run)" in rendered
    assert "](docs/" not in rendered


def test_render_strips_docs_prefix_from_html_src_and_href():
    rendered = sync_docs_index.render(
        '<img src="docs/media/a.png"><a href="docs/SETUP.md">x</a>'
    )

    assert rendered.endswith('<img src="media/a.png"><a href="SETUP.md">x</a>')


@pytest.mark.parametrize(
    "untouched",
    [
        "[LICENSE](https://github.com/acme/widgets/blob/main/LICENSE)",
        "[a doc](https://github.com/acme/widgets/blob/main/docs/SETUP.md)",
        "[elsewhere](other/docs/SETUP.md)",
        "See the docs/ folder for details.",
    ],
)
def test_render_leaves_absolute_links_and_plain_text_alone(untouched):
    assert sync_docs_index.render(untouched).endswith(untouched)


def test_render_marks_the_file_as_generated():
    assert sync_docs_index.render("# Title\n").startswith(
        "<!-- Generated from README.md"
    )


def test_main_writes_index_from_readme(tmp_path, monkeypatch, capsys):
    (tmp_path / "docs").mkdir()
    readme = tmp_path / "README.md"
    readme.write_text("[guide](docs/SETUP.md)\n", encoding="utf-8")
    monkeypatch.setattr(sync_docs_index, "ROOT", tmp_path)
    monkeypatch.setattr(sync_docs_index, "README", readme)
    monkeypatch.setattr(sync_docs_index, "INDEX", tmp_path / "docs" / "index.md")

    assert sync_docs_index.main() == 0

    written = (tmp_path / "docs" / "index.md").read_text(encoding="utf-8")
    assert written == sync_docs_index.render("[guide](docs/SETUP.md)\n")
    assert "wrote docs/index.md from README.md" in capsys.readouterr().out


def test_committed_index_matches_readme():
    """docs/index.md is generated; catches a README edit committed without it
    (e.g. with --no-verify) before it can reach the published site."""
    expected = sync_docs_index.render(
        Path(sync_docs_index.README).read_text(encoding="utf-8")
    )

    assert Path(sync_docs_index.INDEX).read_text(encoding="utf-8") == expected, (
        "docs/index.md is stale - run `make docs-index`"
    )
