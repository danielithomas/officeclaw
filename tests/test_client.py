"""
Tests for the Graph HTTP client helpers.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

from officeclaw.client import _parse_retry_after


class TestParseRetryAfter:
    """Retry-After is either a delay in seconds or an HTTP-date (RFC 9110)."""

    def test_delay_in_seconds(self):
        assert _parse_retry_after("120", default=60) == 120

    def test_missing_header_uses_default(self):
        assert _parse_retry_after(None, default=60) == 60
        assert _parse_retry_after("", default=60) == 60

    def test_http_date(self):
        later = datetime.now(timezone.utc) + timedelta(seconds=90)
        parsed = _parse_retry_after(format_datetime(later), default=60)
        assert 60 <= parsed <= 90

    def test_http_date_in_the_past_is_clamped(self):
        earlier = datetime.now(timezone.utc) - timedelta(hours=1)
        assert _parse_retry_after(format_datetime(earlier), default=60) == 0

    def test_unparseable_value_uses_default(self):
        assert _parse_retry_after("soon", default=45) == 45


class TestAuthRetry:
    """A 401 drops the cached token before retrying."""

    @patch("officeclaw.client.load_environment")
    def test_invalidate_cache_called_once(self, mock_env_loader):
        from officeclaw.client import GraphClient
        from officeclaw.exceptions import AuthenticationError

        token_manager = MagicMock()
        client = GraphClient(token_manager=token_manager)

        with patch.object(client, "_session") as session:
            session.request.side_effect = AuthenticationError("expired")
            with contextlib.suppress(AuthenticationError):
                client.get("/me/messages")

        token_manager.invalidate_cache.assert_called_once()
