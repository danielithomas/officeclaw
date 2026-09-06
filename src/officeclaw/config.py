"""
Optional configuration file for Outclaw.

Reads ``~/.config/officeclaw/config.toml`` for preferences that would otherwise
have to be repeated on every command. Precedence is: command-line flag, then
environment variable, then config file, then the built-in default.

Security settings are deliberately **not** readable from here. Capability gates
and the recipient/attachment allowlists stay in the environment, so a process
that can write a file in the user's config directory cannot grant itself the
ability to send mail. Keys in FORBIDDEN_KEYS are ignored, loudly.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Any

import platformdirs

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib

CONFIG_ENV = "OFFICECLAW_CONFIG"

# ~/.config is where a CLI's config is looked for on Linux and macOS alike, and
# works on Windows too; the platform location is checked as well, so a Windows
# user can keep it in %APPDATA% where they would expect it.
XDG_CONFIG_PATH = Path.home() / ".config" / "officeclaw" / "config.toml"
PLATFORM_CONFIG_PATH = Path(platformdirs.user_config_dir("officeclaw")) / "config.toml"
DEFAULT_CONFIG_PATH = XDG_CONFIG_PATH

# Settings that may appear in the file.
ALLOWED_KEYS = frozenset(
    {
        "default_task_list_id",
        "default_task_list_name",
        "default_output",
        "timezone",
    }
)

# Settings that may never come from the file — see the module docstring.
FORBIDDEN_KEYS = frozenset(
    {
        "enable_send",
        "enable_delete",
        "allowed_recipients",
        "allowed_attachment_dirs",
        "client_id",
        "client_secret",
    }
)


def config_path() -> Path:
    """
    Location of the config file.

    OFFICECLAW_CONFIG wins outright. Otherwise the first candidate that exists
    is used: ``~/.config/officeclaw/config.toml``, then the platform's own
    config directory (the same path on Linux, ``~/Library/Application
    Support`` on macOS, ``%LOCALAPPDATA%`` on Windows). When neither exists,
    the documented ``~/.config`` path is returned so error messages name one
    location rather than several.
    """
    override = os.environ.get(CONFIG_ENV, "").strip()
    if override:
        return Path(override).expanduser()

    for candidate in (XDG_CONFIG_PATH, PLATFORM_CONFIG_PATH):
        if candidate.exists():
            return candidate
    return DEFAULT_CONFIG_PATH


def load_config() -> dict[str, Any]:
    """
    Read the config file.

    Returns:
        Recognized settings. Missing or unreadable files yield {} — a config
        file is a convenience, and its absence is not an error.
    """
    path = config_path()
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except OSError:
        return {}
    except tomllib.TOMLDecodeError as e:
        warnings.warn(f"Ignoring malformed config at {path}: {e}", stacklevel=2)
        return {}

    refused = sorted(FORBIDDEN_KEYS.intersection(raw))
    if refused:
        warnings.warn(
            f"Ignoring security settings in {path}: {', '.join(refused)}. "
            "Capability gates and allowlists are read from the environment only.",
            stacklevel=2,
        )

    return {key: value for key, value in raw.items() if key in ALLOWED_KEYS}


def get_setting(key: str, env_var: str | None = None, default: Any = None) -> Any:
    """
    Resolve one setting.

    Args:
        key: Config file key
        env_var: Environment variable that overrides the file
        default: Value when neither is set

    Returns:
        The environment value, else the config file value, else the default.
    """
    if env_var:
        from_env = os.environ.get(env_var, "").strip()
        if from_env:
            return from_env

    return load_config().get(key, default)


def apply_to_environment(settings: dict[str, Any] | None = None) -> None:
    """
    Publish config-file defaults as environment variables, without overriding.

    Lets the rest of the code keep reading environment variables while the file
    fills in what the environment does not set. Only ALLOWED_KEYS are mapped.
    """
    mapping = {
        "default_task_list_id": "OFFICECLAW_DEFAULT_TASK_LIST_ID",
        "default_task_list_name": "OFFICECLAW_DEFAULT_TASK_LIST_NAME",
        "timezone": "OFFICECLAW_TIMEZONE",
    }
    config = load_config() if settings is None else settings
    for key, env_var in mapping.items():
        value = config.get(key)
        if value and not os.environ.get(env_var):
            os.environ[env_var] = str(value)
