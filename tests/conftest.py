"""
Pytest configuration and fixtures for Outclaw tests.

This module provides:
- Mock responses for Microsoft Graph API
- Test fixtures for authentication
- Sample data generators
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import responses


@pytest.fixture(autouse=True)
def _restore_environment():
    """Undo any environment change a test leaves behind.

    monkeypatch only reverts what monkeypatch itself set; code under test that
    writes to os.environ directly — config.apply_to_environment() does — would
    otherwise leak into every test that runs after it.
    """
    original = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original)


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Point the config file at a path that does not exist.

    Without this, a developer's own ~/.config/officeclaw/config.toml would
    change what the tests see.
    """
    monkeypatch.setenv("OFFICECLAW_CONFIG", str(tmp_path / "absent.toml"))


@pytest.fixture(autouse=True)
def _isolated_home(request, tmp_path, monkeypatch):
    """Keep every test's writes inside tmp_path, never the real home directory.

    A test that forgets to patch one of these paths would otherwise write to
    the developer's own token cache, list cache or block log — and a stale
    entry left behind there changes what the installed CLI does afterwards.

    Integration tests are the exception: they need the real token cache to
    authenticate. They keep their logs and list cache isolated, but read and
    write credentials where the CLI does. Stating that here beats relying on
    fixture ordering to leave the token cache alone.
    """
    from officeclaw import auth, policy, tasks

    home = tmp_path / "home"
    officeclaw_dir = home / ".officeclaw"
    logs = home / "logs"
    officeclaw_dir.mkdir(parents=True)

    if request.node.get_closest_marker("integration") is None:
        # HOME first: paths derived from Path.home() at runtime — the legacy
        # token file among them — would otherwise still point at the real home,
        # and clearing tokens in a test would log the developer out for real.
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))  # Windows equivalent
        monkeypatch.setattr(auth, "CACHE_DIR", officeclaw_dir)
        monkeypatch.setattr(auth, "CACHE_FILE", officeclaw_dir / "token_cache.json")
        monkeypatch.setattr(tasks, "CACHE_DIR", officeclaw_dir)

    # tasks imports LIST_CACHE_FILE by name, so it needs patching separately.
    monkeypatch.setattr(tasks, "LIST_CACHE_FILE", officeclaw_dir / "list_cache.json")
    monkeypatch.setattr(policy, "LOG_DIR", logs)
    monkeypatch.setattr(policy, "BLOCK_LOG", logs / "email-blocked.log")
    monkeypatch.setattr(policy, "ALERT_FILE", logs / "email-alert.json")


# ============================================
# SAMPLE DATA
# ============================================

SAMPLE_ACCESS_TOKEN = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6Ik..."  # noqa: S105  # Truncated for safety
)
SAMPLE_REFRESH_TOKEN = "0.ARwA..."  # noqa: S105  # Truncated for safety

SAMPLE_USER = {
    "id": "user-123",
    "displayName": "Test User",
    "mail": "test@outlook.com",
    "userPrincipalName": "test@outlook.com",
}

SAMPLE_MESSAGE = {
    "id": "AAMkADEzN...",
    "subject": "Test Email Subject",
    "bodyPreview": "This is the body preview...",
    "from": {"emailAddress": {"name": "Sender Name", "address": "sender@example.com"}},
    "toRecipients": [{"emailAddress": {"name": "Test User", "address": "test@outlook.com"}}],
    "receivedDateTime": "2026-02-12T10:30:00Z",
    "isRead": False,
    "importance": "normal",
    "hasAttachments": False,
}

SAMPLE_EVENT = {
    "id": "AAMkADE...",
    "subject": "Team Meeting",
    "bodyPreview": "Weekly sync",
    "start": {"dateTime": "2026-02-12T14:00:00.0000000", "timeZone": "UTC"},
    "end": {"dateTime": "2026-02-12T15:00:00.0000000", "timeZone": "UTC"},
    "location": {"displayName": "Conference Room A"},
    "organizer": {"emailAddress": {"name": "Test User", "address": "test@outlook.com"}},
    "isAllDay": False,
    "isCancelled": False,
}

SAMPLE_ATTACHMENT = {
    "@odata.type": "#microsoft.graph.fileAttachment",
    "id": "AAMkAGUz...",
    "lastModifiedDateTime": "2026-04-23T23:31:17Z",
    "name": "meeting_notes.txt",
    "contentType": "text/plain",
    "size": 15243,
    "isInline": False,
    "contentBytes": "SGVsbG8sIHRoaXMgaXMgdGVzdCBjb250ZW50Lg==",
}

SAMPLE_ATTACHMENT_PDF = {
    "@odata.type": "#microsoft.graph.fileAttachment",
    "id": "AAMkAGUy...",
    "lastModifiedDateTime": "2026-04-23T23:31:17Z",
    "name": "report.pdf",
    "contentType": "application/pdf",
    "size": 10485760,
    "isInline": False,
    "contentBytes": "JVBERi0xLjQKJcOkw7zDtsO...",
}

SAMPLE_MESSAGE_WITH_ATTACHMENTS = {
    **SAMPLE_MESSAGE,
    "hasAttachments": True,
}

SAMPLE_TASK_LIST = {
    "id": "AAMkADE...",
    "displayName": "Tasks",
    "wellknownListName": "defaultList",
    "isOwner": True,
    "isShared": False,
}

SAMPLE_TASK = {
    "id": "AAMkADE...",
    "title": "Complete report",
    "status": "notStarted",
    "importance": "normal",
    "body": {"content": "Finish the quarterly report", "contentType": "text"},
    "dueDateTime": {"dateTime": "2026-02-15T00:00:00.0000000", "timeZone": "UTC"},
    "createdDateTime": "2026-02-10T08:00:00Z",
    "lastModifiedDateTime": "2026-02-12T10:00:00Z",
}


# ============================================
# FIXTURES
# ============================================


@pytest.fixture
def mock_token_data() -> dict[str, Any]:
    """Return mock token data structure."""
    return {
        "access_token": SAMPLE_ACCESS_TOKEN,
        "refresh_token": SAMPLE_REFRESH_TOKEN,
        "token_type": "Bearer",
        "expires_in": 3600,
        "expires_at": datetime.now(timezone.utc).timestamp() + 3600,
        "scope": "Mail.Read Mail.ReadWrite Mail.Send Calendars.Read Calendars.ReadWrite Tasks.ReadWrite",
    }


@pytest.fixture
def mock_keyring() -> Generator[MagicMock, None, None]:
    """Mock the keyring module for secure storage tests."""
    with patch("officeclaw.auth.keyring") as mock:
        mock.get_password.return_value = None
        mock.set_password.return_value = None
        mock.delete_password.return_value = None
        yield mock


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up mock environment variables (confidential client mode)."""
    monkeypatch.setenv("OFFICECLAW_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("OFFICECLAW_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("OFFICECLAW_REDIRECT_URI", "http://localhost:8000/callback")
    monkeypatch.setenv("OFFICECLAW_TENANT_ID", "consumers")


@pytest.fixture
def mock_env_public(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up mock environment variables (public client / device code mode)."""
    monkeypatch.setenv("OFFICECLAW_CLIENT_ID", "test-client-id")
    monkeypatch.delenv("OFFICECLAW_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("OFFICECLAW_TENANT_ID", "consumers")


@pytest.fixture
def mock_graph_api() -> Generator[responses.RequestsMock, None, None]:
    """
    Mock Microsoft Graph API responses.

    Usage:
        def test_something(mock_graph_api):
            mock_graph_api.add(
                responses.GET,
                "https://graph.microsoft.com/v1.0/me",
                json=SAMPLE_USER
            )
    """
    with responses.RequestsMock() as rsps:
        # Default: mock /me endpoint
        rsps.add(
            responses.GET,
            "https://graph.microsoft.com/v1.0/me",
            json=SAMPLE_USER,
            status=200,
        )
        yield rsps


@pytest.fixture
def sample_message() -> dict[str, Any]:
    """Return a sample email message."""
    return SAMPLE_MESSAGE.copy()


@pytest.fixture
def sample_messages() -> list[dict[str, Any]]:
    """Return a list of sample email messages."""
    return [
        SAMPLE_MESSAGE.copy(),
        {**SAMPLE_MESSAGE, "id": "msg-2", "subject": "Another Email", "isRead": True},
        {**SAMPLE_MESSAGE, "id": "msg-3", "subject": "Third Email", "importance": "high"},
    ]


@pytest.fixture
def sample_event() -> dict[str, Any]:
    """Return a sample calendar event."""
    return SAMPLE_EVENT.copy()


@pytest.fixture
def sample_attachment() -> dict[str, Any]:
    """Return a sample file attachment."""
    return SAMPLE_ATTACHMENT.copy()


@pytest.fixture
def sample_attachments() -> list[dict[str, Any]]:
    """Return a list of sample attachments."""
    return [
        SAMPLE_ATTACHMENT.copy(),
        SAMPLE_ATTACHMENT_PDF.copy(),
    ]


@pytest.fixture
def sample_message_with_attachments() -> dict[str, Any]:
    """Return a sample message with attachments."""
    return {
        **SAMPLE_MESSAGE,
        "id": "msg-with-attachments",
        "hasAttachments": True,
    }


@pytest.fixture
def sample_events() -> list[dict[str, Any]]:
    """Return a list of sample calendar events."""
    return [
        SAMPLE_EVENT.copy(),
        {**SAMPLE_EVENT, "id": "evt-2", "subject": "Client Call"},
        {**SAMPLE_EVENT, "id": "evt-3", "subject": "Project Review"},
    ]


@pytest.fixture
def sample_task_list() -> dict[str, Any]:
    """Return a sample task list."""
    return SAMPLE_TASK_LIST.copy()


@pytest.fixture
def sample_task() -> dict[str, Any]:
    """Return a sample task."""
    return SAMPLE_TASK.copy()


@pytest.fixture
def sample_tasks() -> list[dict[str, Any]]:
    """Return a list of sample tasks."""
    return [
        SAMPLE_TASK.copy(),
        {**SAMPLE_TASK, "id": "task-2", "title": "Review PR", "status": "completed"},
        {**SAMPLE_TASK, "id": "task-3", "title": "Update docs", "importance": "high"},
    ]


# ============================================
# HELPERS
# ============================================


def make_graph_response(data: Any, next_link: str | None = None) -> dict[str, Any]:
    """
    Create a paginated Graph API response.

    Args:
        data: The value array data
        next_link: Optional @odata.nextLink for pagination

    Returns:
        Dict matching Graph API response format
    """
    response = {"value": data}
    if next_link:
        response["@odata.nextLink"] = next_link
    return response


def make_error_response(code: str, message: str) -> dict[str, Any]:
    """
    Create a Graph API error response.

    Args:
        code: Error code (e.g., "InvalidAuthenticationToken")
        message: Error message

    Returns:
        Dict matching Graph API error format
    """
    return {
        "error": {
            "code": code,
            "message": message,
            "innerError": {
                "date": datetime.now(timezone.utc).isoformat(),
                "request-id": "test-request-id",
            },
        }
    }
