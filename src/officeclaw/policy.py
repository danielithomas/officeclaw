"""
Outbound email policy for Outclaw.

Two opt-in controls on what may leave the mailbox:

- OFFICECLAW_ALLOWED_RECIPIENTS — addresses mail may be sent to. The check
  lives here, rather than in the CLI, so every outbound path goes through it:
  ``mail send``, ``mail reply``, ``mail forward``, and the Python API
  (:class:`MailClient`).
- OFFICECLAW_ALLOWED_ATTACHMENT_DIRS — directories files may be attached from,
  so an agent cannot mail out an arbitrary file it can read.

Both are unrestricted when unset. When set, a violation raises a
:class:`PolicyViolationError` subclass and the attempt is logged for monitoring.
"""

from __future__ import annotations

import json
import os
import warnings
from collections.abc import Iterable
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path, PurePosixPath

import platformdirs

from officeclaw.exceptions import AttachmentNotAllowedError, RecipientNotAllowedError

ALLOWLIST_ENV = "OFFICECLAW_ALLOWED_RECIPIENTS"
ATTACHMENT_DIRS_ENV = "OFFICECLAW_ALLOWED_ATTACHMENT_DIRS"
DOWNLOADS_DIR_ENV = "OFFICECLAW_DOWNLOADS_DIR"

# The name this setting had in 1.0.5. Still honoured, so an existing .env keeps
# working rather than silently sending downloads somewhere else.
LEGACY_DOWNLOADS_DIR_ENV = "OFFICECLAW_ATTACHMENT_DOWNLOAD_PATH"

# Subdirectory created inside a general-purpose directory (the platform's
# Downloads folder, say) so saved attachments stay together.
DOWNLOAD_SUBDIR = "officeclaw_downloads"

# Characters Windows forbids in a filename, plus the C0 control range.
_WINDOWS_FORBIDDEN = set('<>:"/\\|?*') | {chr(c) for c in range(32)}

# Windows device names, which cannot be used as filenames even with a suffix.
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Blocked attempts are recorded here for external monitoring.
LOG_DIR = Path.home() / ".openclaw" / "workspace" / "automation" / "logs"
BLOCK_LOG = LOG_DIR / "email-blocked.log"
ALERT_FILE = LOG_DIR / "email-alert.json"


def normalize_address(address: str) -> str:
    """Reduce an address to its bare, lowercase form ("A <a@b.c>" -> "a@b.c")."""
    _, addr = parseaddr(address or "")
    return addr.strip().lower()


def get_allowed_recipients() -> set[str] | None:
    """
    Return the configured allowlist.

    Returns:
        Set of normalized addresses, or None when no allowlist is configured
        (in which case all recipients are permitted).
    """
    raw = os.environ.get(ALLOWLIST_ENV, "")
    if not raw.strip():
        return None
    allowed = {normalize_address(entry) for entry in raw.split(",")}
    allowed.discard("")
    return allowed


def check_recipients(
    recipients: Iterable[str],
    action: str,
    subject: str | None = None,
) -> None:
    """
    Verify every recipient against the allowlist.

    Args:
        recipients: Addresses the message would be delivered to.
        action: Outbound operation being attempted ("send", "reply", "forward").
        subject: Message subject, when known (recorded in the block log).

    Raises:
        RecipientNotAllowedError: If any recipient is not on the allowlist, or
            cannot be parsed as an address (the check fails closed).
    """
    allowed = get_allowed_recipients()
    if allowed is None:
        return

    blocked = [
        raw for raw in recipients if (norm := normalize_address(raw)) == "" or norm not in allowed
    ]
    if not blocked:
        return

    log_blocked_attempt(blocked, action=action, subject=subject, allowed=allowed)

    listed = ", ".join(blocked)
    raise RecipientNotAllowedError(
        f"Blocked: {listed} "
        f"{'is' if len(blocked) == 1 else 'are'} not in the allowed recipients list.\n"
        f"Action: {action}\n"
        f"Allowed: {', '.join(sorted(allowed))}"
    )


def get_allowed_attachment_dirs() -> list[Path] | None:
    """
    Return the directories attachments may be read from.

    Returns:
        List of configured directories, or None when unconfigured (in which
        case any readable file may be attached).
    """
    raw = os.environ.get(ATTACHMENT_DIRS_ENV, "")
    if not raw.strip():
        return None
    dirs = [Path(entry.strip()).expanduser() for entry in raw.split(",") if entry.strip()]
    return dirs or None


def check_attachment_path(path: str | Path) -> Path:
    """
    Resolve a file to attach and confirm it is inside a permitted directory.

    Symlinks are resolved before the comparison, so a link planted inside an
    allowed directory cannot reach outside it.

    Args:
        path: File the caller wants to attach.

    Returns:
        The resolved path.

    Raises:
        AttachmentNotAllowedError: If the file lies outside every configured
            directory.
    """
    resolved = Path(path).expanduser().resolve()

    allowed = get_allowed_attachment_dirs()
    if allowed is None:
        return resolved

    resolved_dirs = []
    for directory in allowed:
        try:
            resolved_dirs.append(directory.resolve())
        except OSError:  # pragma: no cover - unreadable directory in config
            continue

    if any(resolved.is_relative_to(directory) for directory in resolved_dirs):
        return resolved

    _log_blocked(
        f"attachment={resolved}",
        action="attachment",
        alert={
            "type": "attachment_blocked",
            "action": "attachment",
            "path": str(resolved),
            "allowed_dirs": [str(d) for d in resolved_dirs],
        },
    )
    listed = ", ".join(str(d) for d in allowed)
    raise AttachmentNotAllowedError(
        f"Blocked: {resolved} is outside the allowed attachment directories.\n" f"Allowed: {listed}"
    )


def default_download_dir() -> Path:
    """
    Where attachments are saved when no destination is given.

    In order of preference:

    1. OFFICECLAW_DOWNLOADS_DIR (or the 1.0.5 name
       OFFICECLAW_ATTACHMENT_DOWNLOAD_PATH), used exactly as given.
    2. ``officeclaw_downloads`` inside the first allowed attachment directory,
       when an allowlist is configured — the destination is then inside the
       boundary by construction, rather than failing the check.
    3. ``officeclaw_downloads`` inside the platform's Downloads folder:
       ``~/Downloads`` on macOS, the XDG download directory on Linux, and the
       Downloads known folder on Windows (which may be relocated, so it is
       looked up rather than assumed).

    Returns:
        Directory path; not created here, and not yet checked against the
        allowlist — :func:`check_download_dir` still applies.
    """
    configured = os.environ.get(DOWNLOADS_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()

    legacy = os.environ.get(LEGACY_DOWNLOADS_DIR_ENV, "").strip()
    if legacy:
        warnings.warn(
            f"{LEGACY_DOWNLOADS_DIR_ENV} is the 1.0.5 name for this setting and still works; "
            f"rename it to {DOWNLOADS_DIR_ENV}.",
            DeprecationWarning,
            stacklevel=2,
        )
        return Path(legacy).expanduser()

    allowed = get_allowed_attachment_dirs()
    if allowed:
        return allowed[0] / DOWNLOAD_SUBDIR

    return Path(platformdirs.user_downloads_dir()).expanduser() / DOWNLOAD_SUBDIR


def check_download_dir(path: str | Path) -> Path:
    """
    Resolve a directory to save attachments into and confirm it is permitted.

    The same allowlist governs both directions: a directory OfficeClaw may read
    attachments from is also one it may write them to. Keeping it to a single
    setting means there is one place to look when auditing what the tool can
    touch on disk.

    Args:
        path: Destination directory.

    Returns:
        The resolved directory path.

    Raises:
        AttachmentNotAllowedError: If it lies outside every configured directory.
    """
    resolved = Path(path).expanduser().resolve()

    allowed = get_allowed_attachment_dirs()
    if allowed is None:
        return resolved

    resolved_dirs = []
    for directory in allowed:
        try:
            resolved_dirs.append(directory.resolve())
        except OSError:  # pragma: no cover - unreadable directory in config
            continue

    if any(resolved.is_relative_to(directory) for directory in resolved_dirs):
        return resolved

    _log_blocked(
        f"download_dir={resolved}",
        action="download",
        alert={
            "type": "download_blocked",
            "action": "download",
            "path": str(resolved),
            "allowed_dirs": [str(d) for d in resolved_dirs],
        },
    )
    listed = ", ".join(str(d) for d in allowed)
    raise AttachmentNotAllowedError(
        f"Blocked: {resolved} is outside the allowed attachment directories.\n" f"Allowed: {listed}"
    )


def safe_attachment_name(name: str | None, fallback: str = "attachment") -> str:
    """
    Reduce an attachment's name to something safe to write, on any platform.

    Attachment names come from whoever sent the mail, so a name of
    ``../../.ssh/authorized_keys`` must not be able to steer the write. Only the
    final path component survives — backslashes count as separators too, so a
    Windows-style path is not treated as one long filename on Linux.

    The result is also made legal on Windows, whatever the host: characters
    Windows forbids are dropped, trailing dots and spaces are trimmed, and
    reserved device names such as ``CON`` are prefixed. Doing this everywhere
    keeps a downloads directory portable between machines.

    Args:
        name: Name as reported by Graph.
        fallback: Name to use when nothing usable remains.

    Returns:
        A bare filename, never a path.
    """
    candidate = (name or "").replace("\\", "/")
    candidate = PurePosixPath(candidate).name
    candidate = "".join(c for c in candidate if c not in _WINDOWS_FORBIDDEN)
    candidate = candidate.strip().lstrip(".").strip()
    # Windows silently drops trailing dots and spaces; do it explicitly.
    candidate = candidate.rstrip(". ")

    if not candidate:
        return fallback

    stem = candidate.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED:
        candidate = f"_{candidate}"

    return candidate


def unique_path(directory: Path, filename: str) -> Path:
    """Path in ``directory`` for ``filename``, suffixed if it already exists."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem, suffix = candidate.stem, candidate.suffix
    for counter in range(1, 1000):
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
    raise AttachmentNotAllowedError(f"Cannot find a free filename for {filename!r}.")


def log_blocked_attempt(
    recipients: Iterable[str],
    action: str,
    subject: str | None = None,
    allowed: set[str] | None = None,
) -> None:
    """Record a blocked send to the log and alert files."""
    to_field = ",".join(recipients)
    _log_blocked(
        f"to={to_field} | subject={subject or ''}",
        action=action,
        alert={
            "type": "email_blocked",
            "action": action,
            "to": to_field,
            "subject": subject or "",
            "allowed_recipients": sorted(allowed) if allowed else [],
        },
    )


def _log_blocked(detail: str, action: str, alert: dict[str, object]) -> None:
    """
    Write a blocked attempt to the log and alert files.

    Logging is best-effort: a failure to write must never turn a blocked action
    into an unreported one, so I/O errors here are swallowed. The caller has
    already decided not to proceed.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(BLOCK_LOG, "a") as f:
            f.write(f"[{ts}] BLOCKED | {detail} | action={action}\n")

        # Machine-readable alert for external monitoring.
        with open(ALERT_FILE, "w") as f:
            json.dump({**alert, "timestamp": ts}, f, indent=2)
    except OSError:
        pass
