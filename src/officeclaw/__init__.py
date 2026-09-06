"""
Outclaw - Microsoft Graph API integration for OpenClaw agents.

Provides email, calendar, and task management through a simple CLI
and Python API.

Example usage:
    # CLI
    $ officeclaw mail list --limit 10
    $ officeclaw calendar list --start 2026-02-01 --end 2026-02-28
    $ officeclaw tasks list-lists

    # Python
    from officeclaw import MailClient, CalendarClient, TasksClient

    mail = MailClient()
    messages = mail.list_messages(limit=10)
"""

from __future__ import annotations

from typing import Any

__version__ = "1.1.0"
__author__ = "Daniel Thomas"
__email__ = "dan@theenquiringmind.com"


# Lazy imports to avoid loading everything on import
def __getattr__(name: str) -> Any:
    """Lazy import of client classes."""
    if name == "MailClient":
        from officeclaw.mail import MailClient

        return MailClient
    elif name == "CalendarClient":
        from officeclaw.calendar import CalendarClient

        return CalendarClient
    elif name == "TasksClient":
        from officeclaw.tasks import TasksClient

        return TasksClient
    elif name == "TokenManager":
        from officeclaw.auth import TokenManager

        return TokenManager
    elif name == "GraphClient":
        from officeclaw.client import GraphClient

        return GraphClient
    elif name == "AttachmentSecurityError":
        from officeclaw.exceptions import AttachmentSecurityError

        return AttachmentSecurityError
    elif name == "AttachmentSizeError":
        from officeclaw.exceptions import AttachmentSizeError

        return AttachmentSizeError
    elif name == "AttachmentTypeError":
        from officeclaw.exceptions import AttachmentTypeError

        return AttachmentTypeError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "__version__",
    "MailClient",
    "CalendarClient",
    "TasksClient",
    "TokenManager",
    "GraphClient",
    "AttachmentSecurityError",
    "AttachmentSizeError",
    "AttachmentTypeError",
]
