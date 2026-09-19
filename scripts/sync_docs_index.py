"""Generate docs/index.md from README.md so the docs home page has one source.

The README's links are relative to the repo root (`docs/CONFIGURATION.md`), which
is what GitHub needs. The docs site is rooted at `docs/`, so the same links must
lose their `docs/` prefix there. Anything else in the README that must work in
both places (LICENSE, action.yml) is linked absolutely instead.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
INDEX = ROOT / "docs" / "index.md"

HEADER = (
    "<!-- Generated from README.md by scripts/sync_docs_index.py. "
    "Edit README.md, not this file. -->\n\n"
)

# Markdown links/images `](docs/...)` and HTML `src="docs/..."` / `href="docs/..."`.
DOCS_PREFIX = re.compile(r'(\]\(|(?:src|href)=")docs/')


def render(readme_text: str) -> str:
    return HEADER + DOCS_PREFIX.sub(r"\1", readme_text)


def main() -> int:
    INDEX.write_text(render(README.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"wrote {INDEX.relative_to(ROOT)} from {README.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
