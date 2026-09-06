"""
Guards against version and Python-floor drift between files.

The version is single-sourced from ``officeclaw.__version__``, but the skill
manifest, packaging metadata, README and CI matrix all restate it or the Python
floor in prose. 1.1.0 shipped a manifest still claiming version 1.0.4 and
Python 3.9+ — metadata an OpenClaw host acts on. These tests make that a CI
failure instead of a release.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib

import officeclaw

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "skill" / "SKILL.md").read_text()
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())


def skill_frontmatter_value(key: str) -> str:
    """Read a value from the skill file's YAML frontmatter, without a YAML dep."""
    frontmatter = SKILL.split("---")[1]
    match = re.search(rf'^\s*{key}:\s*"?([^"\n]+)"?\s*$', frontmatter, re.M)
    assert match, f"{key} not found in SKILL.md frontmatter"
    return match.group(1).strip()


def python_floor() -> str:
    """The minimum Python version, e.g. '3.10'."""
    return PYPROJECT["project"]["requires-python"].lstrip(">=")


class TestVersion:
    def test_skill_manifest_matches_the_package(self):
        assert skill_frontmatter_value("version") == officeclaw.__version__

    def test_changelog_has_an_entry_for_this_version(self):
        changelog = (ROOT / "CHANGELOG.md").read_text()
        assert f"## [{officeclaw.__version__}]" in changelog

    def test_version_is_not_declared_statically_in_pyproject(self):
        """It must stay derived from __version__, or the two can disagree."""
        assert "version" not in PYPROJECT["project"]
        assert "version" in PYPROJECT["project"]["dynamic"]


class TestPythonFloor:
    def test_skill_compatibility_line(self):
        assert f"Requires Python {python_floor()}+" in skill_frontmatter_value("compatibility")

    def test_readme(self):
        readme = (ROOT / "README.md").read_text()
        assert f"Requires Python {python_floor()} or newer" in readme

    def test_classifiers_start_at_the_floor(self):
        classifiers = PYPROJECT["project"]["classifiers"]
        versions = sorted(
            c.rsplit(" :: ", 1)[1]
            for c in classifiers
            if c.startswith("Programming Language :: Python :: 3.")
        )
        assert versions[0] == python_floor()

    def test_ci_matrix_starts_at_the_floor(self):
        workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text()
        match = re.search(r"python-version: \[([^\]]+)\]", workflow)
        assert match, "python-version matrix not found"
        versions = [v.strip().strip('"') for v in match.group(1).split(",")]
        assert versions[0] == python_floor()
        assert versions == sorted(versions, key=lambda v: [int(p) for p in v.split(".")])

    def test_architecture_doc_matches(self):
        architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text()
        assert f'requires-python = ">={python_floor()}"' in architecture


class TestSkillInstallGuidance:
    def test_minimum_version_is_not_ahead_of_the_package(self):
        """SKILL.md must not tell agents to install a version that doesn't exist."""
        match = re.search(r"officeclaw>=(\d+\.\d+\.\d+)", SKILL)
        assert match, "SKILL.md should pin a minimum officeclaw version"
        required = tuple(int(p) for p in match.group(1).split("."))
        current = tuple(int(p) for p in officeclaw.__version__.split("."))
        assert required <= current


@pytest.mark.parametrize("path", ["skill", "src", "tests", "docs", "README.md", "CHANGELOG.md"])
def test_sdist_includes_what_consumers_need(path):
    """The skill file ships in the sdist; a manifest fix is useless if it does not."""
    include = PYPROJECT["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    normalised = {entry.lstrip("/") for entry in include}
    assert path in normalised
