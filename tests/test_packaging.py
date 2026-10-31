"""Guards for the Docker image's hash-locked install.

The image installs from requirements.lock (see the Dockerfile), which is
generated from requirements.txt by `make lock`. Nothing regenerates it
automatically - e.g. when Dependabot bumps requirements.txt - so these tests
turn a stale or unusable lock into a visible failure instead of a surprise at
image-build time.
"""

import re
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parent.parent
REGENERATE = "run `make lock` to regenerate requirements.lock"


def _lock_entries() -> dict[str, tuple[Version, int]]:
    """Map each locked package to its version and how many hashes it carries."""
    entries: dict[str, tuple[Version, int]] = {}
    blocks = re.split(
        r"^(?=[A-Za-z0-9_.-]+==)",
        (REPO_ROOT / "requirements.lock").read_text(),
        flags=re.M,
    )
    for block in blocks:
        match = re.match(r"([A-Za-z0-9_.-]+)==(\S+)", block)
        if match:
            name = match.group(1).lower().replace("_", "-")
            entries[name] = (Version(match.group(2)), block.count("--hash=sha256:"))
    return entries


def _direct_requirements() -> list[Requirement]:
    lines = (REPO_ROOT / "requirements.txt").read_text().splitlines()
    return [
        Requirement(line) for line in lines if line.strip() and not line.startswith("#")
    ]


def test_lock_satisfies_every_requirement_in_requirements_txt():
    locked = _lock_entries()
    for requirement in _direct_requirements():
        name = requirement.name.lower().replace("_", "-")
        assert name in locked, (
            f"{requirement.name} is missing from the lock; {REGENERATE}"
        )
        version = locked[name][0]
        assert requirement.specifier.contains(version), (
            f"requirements.txt wants {requirement} but the lock has {version}; {REGENERATE}"
        )


def test_every_locked_package_is_hashed():
    unhashed = [name for name, (_, hashes) in _lock_entries().items() if hashes == 0]
    assert not unhashed, f"locked without hashes: {unhashed}; {REGENERATE}"


def test_dockerfile_installs_from_the_lock_with_hashes_and_wheels_only():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    assert "COPY requirements.lock" in dockerfile
    assert "--require-hashes" in dockerfile
    assert "--only-binary :all:" in dockerfile
    assert "--no-install-recommends" in dockerfile


def test_dockerignore_lets_the_lock_into_the_build_context():
    """.dockerignore excludes everything by default; without this the build breaks."""
    assert (
        "!requirements.lock" in (REPO_ROOT / ".dockerignore").read_text().splitlines()
    )


def test_action_image_tag_matches_the_package_version():
    """The bump keeps these together; a mismatch runs the wrong code for users."""
    version = re.search(
        r'__version__ = "([^"]+)"',
        (REPO_ROOT / "pr_description" / "__init__.py").read_text(),
    ).group(1)
    assert (
        f"image: 'docker://ghcr.io/devsetgo/ai-pr-assistant:{version}'"
        in (REPO_ROOT / "action.yml").read_text()
    )


def test_dogfood_workflow_builds_this_checkout_instead_of_the_release():
    workflow = (REPO_ROOT / ".github/workflows/ai_pr_assistant.yml").read_text()
    assert "image: 'Dockerfile'|\" action.yml" in workflow
    assert workflow.index("action.yml\n") < workflow.index("uses: ./")


@pytest.mark.parametrize(
    "workflow",
    sorted((REPO_ROOT / ".github/workflows").glob("*.y*ml")),
    ids=lambda path: path.name,
)
def test_workflow_is_valid_yaml(workflow):
    """GitHub rejects an invalid workflow without running it or failing the PR."""
    assert "jobs" in yaml.safe_load(workflow.read_text())
