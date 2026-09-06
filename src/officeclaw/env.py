"""
Environment loading for Outclaw.

Two sources configure OfficeClaw: the process environment (which a supervising
process such as the OpenClaw gateway daemon injects into) and the ``.env`` file
in the working directory.

For ordinary settings the file wins, because someone who edits ``.env`` expects
it to take effect — being silently ignored is how a stale injected value went
unnoticed for months.

Security settings compose instead, to the **stricter** of the two: allowlists
intersect, permission gates must be enabled by both, restriction toggles are
honoured if either sets them, and numeric ceilings take the lower value. So
neither source can widen what the other permits — a file in the working
directory cannot loosen a restriction the daemon imposed, and the daemon cannot
override a tighter local policy. Any disagreement is reported, so a value that
does not take effect is never silent.
"""

from __future__ import annotations

import os
import warnings

from dotenv import dotenv_values, find_dotenv

# Allowlists: the effective list is the intersection of whatever is set.
LIST_SETTINGS = frozenset(
    {
        "OFFICECLAW_ALLOWED_RECIPIENTS",
        "OFFICECLAW_ALLOWED_ATTACHMENT_DIRS",
        "OFFICECLAW_SAFE_SENDERS_LIST",
        "OFFICECLAW_ATTACHMENT_ALLOWED_TYPES",
    }
)

# Permissions: both sources have to allow it.
GATE_SETTINGS = frozenset(
    {
        "OFFICECLAW_ENABLE_SEND",
        "OFFICECLAW_ENABLE_DELETE",
        "OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD",
    }
)

# Restrictions: either source can switch them on.
RESTRICTION_SETTINGS = frozenset({"OFFICECLAW_SAFE_SENDERS_ONLY"})

# Ceilings: the lower value applies.
LIMIT_SETTINGS = frozenset({"OFFICECLAW_ATTACHMENT_MAX_SIZE_MB"})

SECURITY_SETTINGS = LIST_SETTINGS | GATE_SETTINGS | RESTRICTION_SETTINGS | LIMIT_SETTINGS

TRUTHY = ("true", "1", "yes")

_loaded = False


def is_truthy(value: str | None) -> bool:
    """Whether a setting reads as enabled."""
    return (value or "").strip().lower() in TRUTHY


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _combine_list(key: str, from_env: str, from_file: str) -> str:
    """Intersect two allowlists, keeping the order of the environment's."""
    env_items = _split(from_env)
    file_items = {item.lower() for item in _split(from_file)}

    # "*" means "no restriction", so it never narrows the other side.
    if from_file.strip() == "*":
        return from_env
    if from_env.strip() == "*":
        return from_file

    kept = [item for item in env_items if item.lower() in file_items]
    dropped = [
        item for item in _split(from_file) if item.lower() not in {e.lower() for e in env_items}
    ]
    if dropped:
        warnings.warn(
            f"{key}: {', '.join(dropped)} listed in .env but not in the environment, "
            "so it is not in effect. Allowlists from both sources are intersected; "
            "add the entry where the environment value is set.",
            stacklevel=2,
        )
    return ",".join(kept)


def _combine_gate(key: str, from_env: str, from_file: str) -> str:
    """A permission needs both sources to allow it."""
    if is_truthy(from_file) and not is_truthy(from_env):
        warnings.warn(
            f"{key}=true in .env is not in effect: the environment sets it to "
            f"{from_env!r}, and a capability must be enabled in both.",
            stacklevel=2,
        )
    return "true" if is_truthy(from_env) and is_truthy(from_file) else "false"


def _combine_restriction(from_env: str, from_file: str) -> str:
    """A restriction applies if either source asks for it."""
    return "true" if is_truthy(from_env) or is_truthy(from_file) else "false"


def _combine_limit(key: str, from_env: str, from_file: str) -> str:
    """The lower ceiling wins."""
    try:
        return str(min(int(from_env), int(from_file)))
    except ValueError:
        warnings.warn(f"{key}: ignoring non-numeric value; keeping {from_env!r}.", stacklevel=2)
        return from_env


def compose(key: str, from_env: str, from_file: str) -> str:
    """Combine one setting's two sources into the stricter result."""
    if key in LIST_SETTINGS:
        return _combine_list(key, from_env, from_file)
    if key in GATE_SETTINGS:
        return _combine_gate(key, from_env, from_file)
    if key in RESTRICTION_SETTINGS:
        return _combine_restriction(from_env, from_file)
    if key in LIMIT_SETTINGS:
        return _combine_limit(key, from_env, from_file)
    return from_file  # Ordinary setting: the file wins.


def load_environment(force: bool = False) -> None:
    """
    Load ``.env`` into the process environment.

    The file is looked for in the current working directory and its parents.

    Args:
        force: Re-read even if this process has already loaded it.
    """
    global _loaded
    if _loaded and not force:
        return

    # usecwd=True searches from the directory the command was run in, walking
    # up. Without it python-dotenv searches from this file's location, which
    # for an installed package is site-packages — so a user's .env would be
    # found when running from a source checkout and silently missed otherwise.
    dotenv_path = find_dotenv(usecwd=True)

    for key, value in dotenv_values(dotenv_path).items():
        if value is None:
            continue
        existing = os.environ.get(key)
        if existing is None or key not in SECURITY_SETTINGS:
            os.environ[key] = value
        else:
            os.environ[key] = compose(key, existing, value)

    _loaded = True
