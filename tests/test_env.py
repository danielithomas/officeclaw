"""
Tests for .env / environment composition.

The rule under test: ordinary settings come from .env, security settings
compose to the stricter of the two sources, and neither source can widen what
the other permits.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from officeclaw import env


@pytest.fixture
def dotenv(tmp_path, monkeypatch):
    """Write a .env and make it the one dotenv finds."""

    def write(contents: str):
        path = tmp_path / ".env"
        path.write_text(contents)
        monkeypatch.chdir(tmp_path)
        return path

    return write


def load(dotenv, contents: str, environment: dict[str, str]):
    """Apply composition for a given .env and process environment."""
    dotenv(contents)
    os.environ.clear()
    os.environ.update(environment)
    env.load_environment(force=True)
    return dict(os.environ)


class TestOrdinarySettings:
    def test_dotenv_wins(self, dotenv):
        """The Kriti bug: an edited .env must not be silently ignored."""
        result = load(
            dotenv, "OFFICECLAW_TENANT_ID=consumers\n", {"OFFICECLAW_TENANT_ID": "common"}
        )
        assert result["OFFICECLAW_TENANT_ID"] == "consumers"

    def test_dotenv_fills_in_what_the_environment_lacks(self, dotenv):
        result = load(dotenv, "OFFICECLAW_TIMEZONE=Australia/Melbourne\n", {})
        assert result["OFFICECLAW_TIMEZONE"] == "Australia/Melbourne"


class TestAllowlistsIntersect:
    def test_dotenv_cannot_widen_an_injected_allowlist(self, dotenv):
        """A daemon-injected allowlist must not be broadened by a local file."""
        result = load(
            dotenv,
            "OFFICECLAW_ALLOWED_RECIPIENTS=dan@example.com,kriti@example.com,third@example.com\n",
            {"OFFICECLAW_ALLOWED_RECIPIENTS": "dan@example.com,kriti@example.com"},
        )
        assert result["OFFICECLAW_ALLOWED_RECIPIENTS"] == "dan@example.com,kriti@example.com"

    def test_dotenv_can_narrow(self, dotenv):
        """Being stricter locally is always allowed."""
        result = load(
            dotenv,
            "OFFICECLAW_ALLOWED_RECIPIENTS=dan@example.com\n",
            {"OFFICECLAW_ALLOWED_RECIPIENTS": "dan@example.com,kriti@example.com"},
        )
        assert result["OFFICECLAW_ALLOWED_RECIPIENTS"] == "dan@example.com"

    def test_a_dropped_entry_is_reported(self, dotenv):
        """Nothing is ignored silently — that is how the original bug hid."""
        dotenv("OFFICECLAW_ALLOWED_RECIPIENTS=dan@example.com,kriti@example.com\n")
        os.environ.clear()
        os.environ["OFFICECLAW_ALLOWED_RECIPIENTS"] = "dan@example.com"

        with pytest.warns(UserWarning, match="kriti@example.com"):
            env.load_environment(force=True)

    def test_only_one_source_set_means_it_applies(self, dotenv):
        result = load(dotenv, "OFFICECLAW_ALLOWED_RECIPIENTS=dan@example.com\n", {})
        assert result["OFFICECLAW_ALLOWED_RECIPIENTS"] == "dan@example.com"

    def test_wildcard_does_not_narrow(self, dotenv):
        result = load(
            dotenv,
            "OFFICECLAW_ATTACHMENT_ALLOWED_TYPES=*\n",
            {"OFFICECLAW_ATTACHMENT_ALLOWED_TYPES": "application/pdf"},
        )
        assert result["OFFICECLAW_ATTACHMENT_ALLOWED_TYPES"] == "application/pdf"


class TestGatesRequireBoth:
    def test_dotenv_cannot_enable_what_the_environment_disables(self, dotenv):
        result = load(
            dotenv,
            "OFFICECLAW_ENABLE_SEND=true\n",
            {"OFFICECLAW_ENABLE_SEND": "false"},
        )
        assert result["OFFICECLAW_ENABLE_SEND"] == "false"

    def test_enabling_in_both_works(self, dotenv):
        result = load(dotenv, "OFFICECLAW_ENABLE_SEND=true\n", {"OFFICECLAW_ENABLE_SEND": "true"})
        assert result["OFFICECLAW_ENABLE_SEND"] == "true"

    def test_dotenv_alone_still_enables(self, dotenv):
        """With nothing injected, .env is the only authority."""
        result = load(dotenv, "OFFICECLAW_ENABLE_SEND=true\n", {})
        assert result["OFFICECLAW_ENABLE_SEND"] == "true"

    def test_environment_alone_still_enables(self, dotenv):
        result = load(dotenv, "\n", {"OFFICECLAW_ENABLE_SEND": "true"})
        assert result["OFFICECLAW_ENABLE_SEND"] == "true"

    def test_refused_enable_is_reported(self, dotenv):
        dotenv("OFFICECLAW_ENABLE_DELETE=true\n")
        os.environ.clear()
        os.environ["OFFICECLAW_ENABLE_DELETE"] = "false"

        with pytest.warns(UserWarning, match="OFFICECLAW_ENABLE_DELETE"):
            env.load_environment(force=True)


class TestRestrictionsAndLimits:
    def test_either_source_can_require_safe_senders(self, dotenv):
        result = load(
            dotenv,
            "OFFICECLAW_SAFE_SENDERS_ONLY=false\n",
            {"OFFICECLAW_SAFE_SENDERS_ONLY": "true"},
        )
        assert result["OFFICECLAW_SAFE_SENDERS_ONLY"] == "true"

    def test_lower_size_ceiling_wins(self, dotenv):
        result = load(
            dotenv,
            "OFFICECLAW_ATTACHMENT_MAX_SIZE_MB=100\n",
            {"OFFICECLAW_ATTACHMENT_MAX_SIZE_MB": "10"},
        )
        assert result["OFFICECLAW_ATTACHMENT_MAX_SIZE_MB"] == "10"


class TestAttachmentDirsCompose:
    def test_dotenv_cannot_add_a_directory(self, dotenv, tmp_path):
        allowed = tmp_path / "wip"
        result = load(
            dotenv,
            f"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS={Path.home()},{allowed}\n",
            {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(allowed)},
        )
        assert result["OFFICECLAW_ALLOWED_ATTACHMENT_DIRS"] == str(allowed)
