"""
Tests for the optional config file, including what it may not configure.
"""

from __future__ import annotations

import pytest

from officeclaw import config

CONFIG = """
default_task_list_name = "Work"
default_output = "json"
timezone = "Australia/Melbourne"
"""

INSECURE_CONFIG = """
default_task_list_name = "Work"
enable_send = true
allowed_recipients = "anyone@example.com"
"""


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    def write(contents: str):
        path = tmp_path / "config.toml"
        path.write_text(contents)
        monkeypatch.setenv("OFFICECLAW_CONFIG", str(path))
        return path

    return write


class TestLoadConfig:
    def test_missing_file_is_not_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OFFICECLAW_CONFIG", str(tmp_path / "absent.toml"))
        assert config.load_config() == {}

    def test_recognized_settings_are_read(self, config_file):
        config_file(CONFIG)
        settings = config.load_config()
        assert settings["default_task_list_name"] == "Work"
        assert settings["default_output"] == "json"

    def test_unknown_keys_are_ignored(self, config_file):
        config_file('default_task_list_name = "Work"\nnonsense = 1\n')
        assert "nonsense" not in config.load_config()

    def test_malformed_file_warns_and_yields_nothing(self, config_file):
        config_file("not = = toml")
        with pytest.warns(UserWarning, match="malformed config"):
            assert config.load_config() == {}


class TestSecuritySettingsAreRefused:
    def test_gates_and_allowlists_are_ignored(self, config_file):
        config_file(INSECURE_CONFIG)

        with pytest.warns(UserWarning, match="Ignoring security settings"):
            settings = config.load_config()

        assert "enable_send" not in settings
        assert "allowed_recipients" not in settings
        assert settings["default_task_list_name"] == "Work"

    def test_environment_is_not_polluted_with_security_settings(self, config_file, monkeypatch):
        config_file(INSECURE_CONFIG)
        monkeypatch.delenv("OFFICECLAW_ENABLE_SEND", raising=False)

        with pytest.warns(UserWarning):
            config.apply_to_environment()

        import os

        assert "OFFICECLAW_ENABLE_SEND" not in os.environ


class TestApplyToEnvironment:
    def test_fills_in_unset_variables(self, config_file, monkeypatch):
        config_file(CONFIG)
        monkeypatch.delenv("OFFICECLAW_DEFAULT_TASK_LIST_NAME", raising=False)

        config.apply_to_environment()

        import os

        assert os.environ["OFFICECLAW_DEFAULT_TASK_LIST_NAME"] == "Work"

    def test_does_not_override_the_environment(self, config_file, monkeypatch):
        config_file(CONFIG)
        monkeypatch.setenv("OFFICECLAW_DEFAULT_TASK_LIST_NAME", "FromEnv")

        config.apply_to_environment()

        import os

        assert os.environ["OFFICECLAW_DEFAULT_TASK_LIST_NAME"] == "FromEnv"


class TestPlatformLocations:
    """Config is found in the platform's own directory as well as ~/.config."""

    def test_env_override_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OFFICECLAW_CONFIG", str(tmp_path / "custom.toml"))
        assert config.config_path() == tmp_path / "custom.toml"

    def test_xdg_path_preferred_when_it_exists(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OFFICECLAW_CONFIG", raising=False)
        xdg = tmp_path / "xdg.toml"
        xdg.write_text("")
        platform = tmp_path / "platform.toml"
        platform.write_text("")
        monkeypatch.setattr(config, "XDG_CONFIG_PATH", xdg)
        monkeypatch.setattr(config, "PLATFORM_CONFIG_PATH", platform)

        assert config.config_path() == xdg

    def test_platform_path_used_when_xdg_is_absent(self, tmp_path, monkeypatch):
        """A Windows user keeping config in %LOCALAPPDATA% is found."""
        monkeypatch.delenv("OFFICECLAW_CONFIG", raising=False)
        platform = tmp_path / "platform.toml"
        platform.write_text('default_task_list_name = "Work"')
        monkeypatch.setattr(config, "XDG_CONFIG_PATH", tmp_path / "absent.toml")
        monkeypatch.setattr(config, "PLATFORM_CONFIG_PATH", platform)

        assert config.config_path() == platform
        assert config.load_config()["default_task_list_name"] == "Work"

    def test_documented_path_reported_when_neither_exists(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OFFICECLAW_CONFIG", raising=False)
        monkeypatch.setattr(config, "XDG_CONFIG_PATH", tmp_path / "absent.toml")
        monkeypatch.setattr(config, "PLATFORM_CONFIG_PATH", tmp_path / "also-absent.toml")
        monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", tmp_path / "absent.toml")

        assert config.config_path() == tmp_path / "absent.toml"
