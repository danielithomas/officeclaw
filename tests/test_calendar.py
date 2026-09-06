"""
Tests for the Outclaw calendar module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCalendarClient:
    """Test CalendarClient operations."""

    @patch("officeclaw.calendar.GraphClient")
    def test_list_events(self, mock_client_class, sample_events):
        """Test listing events."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_events
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        events = client.list_events("2026-02-01", "2026-02-28")

        assert len(events) == 3
        mock_client.get_all.assert_called_once()
        call_args = mock_client.get_all.call_args
        assert "/me/calendarView" in call_args[0][0]

    @patch("officeclaw.calendar.GraphClient")
    def test_list_events_with_dates(self, mock_client_class, sample_events):
        """Test listing events with date parameters."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_events
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        client.list_events("2026-02-01", "2026-02-28", limit=10)

        call_args = mock_client.get_all.call_args
        params = call_args[1]["params"]
        assert "startDateTime" in params
        assert "endDateTime" in params
        assert "2026-02-01" in params["startDateTime"]
        assert "2026-02-28" in params["endDateTime"]

    @patch("officeclaw.calendar.GraphClient")
    def test_get_event(self, mock_client_class, sample_event):
        """Test getting a specific event."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.get.return_value = sample_event
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        event = client.get_event("evt-123")

        assert event["subject"] == sample_event["subject"]
        mock_client.get.assert_called_with("/me/events/evt-123")

    @patch("officeclaw.calendar.GraphClient")
    def test_create_event(self, mock_client_class, sample_event):
        """Test creating an event."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.post.return_value = sample_event
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        event = client.create_event(
            subject="Team Meeting",
            start="2026-02-15T10:00:00",
            end="2026-02-15T11:00:00",
        )

        assert event["subject"] == sample_event["subject"]
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/me/events"
        assert call_args[0][1]["subject"] == "Team Meeting"

    @patch("officeclaw.calendar.GraphClient")
    def test_create_event_with_attendees(self, mock_client_class, sample_event):
        """Test creating event with attendees."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.post.return_value = sample_event
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        client.create_event(
            subject="Meeting",
            start="2026-02-15T10:00:00",
            end="2026-02-15T11:00:00",
            attendees=["user1@example.com", "user2@example.com"],
        )

        call_args = mock_client.post.call_args
        event_data = call_args[0][1]
        assert "attendees" in event_data
        assert len(event_data["attendees"]) == 2

    @patch("officeclaw.calendar.GraphClient")
    def test_create_online_meeting(self, mock_client_class, sample_event):
        """Test creating Teams meeting."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.post.return_value = sample_event
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        client.create_event(
            subject="Teams Call",
            start="2026-02-15T10:00:00",
            end="2026-02-15T11:00:00",
            is_online_meeting=True,
        )

        call_args = mock_client.post.call_args
        event_data = call_args[0][1]
        assert event_data["isOnlineMeeting"] is True

    @patch("officeclaw.calendar.GraphClient")
    def test_update_event(self, mock_client_class, sample_event):
        """Test updating an event."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        updated = {**sample_event, "subject": "Updated Meeting"}
        mock_client.patch.return_value = updated
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        result = client.update_event("evt-123", subject="Updated Meeting")

        assert result["subject"] == "Updated Meeting"
        mock_client.patch.assert_called_once()

    @patch("officeclaw.calendar.GraphClient")
    def test_delete_event(self, mock_client_class):
        """Test deleting an event."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.delete.return_value = None
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        client.delete_event("evt-123")

        mock_client.delete.assert_called_with("/me/events/evt-123")

    @patch("officeclaw.calendar.GraphClient")
    def test_accept_event(self, mock_client_class):
        """Test accepting meeting invitation."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.post.return_value = None
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        client.accept_event("evt-123", comment="Looking forward to it!")

        mock_client.post.assert_called_with(
            "/me/events/evt-123/accept",
            {"comment": "Looking forward to it!", "sendResponse": True},
        )

    @patch("officeclaw.calendar.GraphClient")
    def test_decline_event(self, mock_client_class):
        """Test declining meeting invitation."""
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.post.return_value = None
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        client.decline_event("evt-123", comment="Can't make it")

        mock_client.post.assert_called_with(
            "/me/events/evt-123/decline",
            {"comment": "Can't make it", "sendResponse": True},
        )

    def test_normalize_datetime_date_only(self):
        """Test datetime normalization with date only."""
        from officeclaw.calendar import CalendarClient

        client = CalendarClient.__new__(CalendarClient)

        result = client._normalize_datetime("2026-02-15")
        assert result == "2026-02-15T00:00:00"

        result = client._normalize_datetime("2026-02-15", end_of_day=True)
        assert result == "2026-02-15T23:59:59"

    def test_normalize_datetime_full(self):
        """Test datetime normalization with full datetime."""
        from officeclaw.calendar import CalendarClient

        client = CalendarClient.__new__(CalendarClient)

        result = client._normalize_datetime("2026-02-15T10:30:00")
        assert result == "2026-02-15T10:30:00"

        # Strips Z suffix
        result = client._normalize_datetime("2026-02-15T10:30:00Z")
        assert result == "2026-02-15T10:30:00"


class TestListEventsTimezone:
    """The timezone argument is sent as a Prefer header."""

    @patch("officeclaw.calendar.GraphClient")
    def test_timezone_sets_prefer_header(self, mock_client_class):
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = []
        mock_client_class.return_value = mock_client

        CalendarClient().list_events("2026-02-01", "2026-02-28", timezone="Pacific Standard Time")

        headers = mock_client.get_all.call_args[1]["headers"]
        assert headers == {"Prefer": 'outlook.timezone="Pacific Standard Time"'}

    @patch("officeclaw.calendar.GraphClient")
    def test_no_header_without_timezone(self, mock_client_class):
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = []
        mock_client_class.return_value = mock_client

        CalendarClient().list_events("2026-02-01", "2026-02-28")

        assert mock_client.get_all.call_args[1]["headers"] is None


class TestRecurrence:
    """Simple recurrence names become Graph patternedRecurrence objects."""

    def test_weekly_uses_the_start_weekday(self):
        from officeclaw.calendar import CalendarClient

        # 2026-09-08 is a Tuesday.
        recurrence = CalendarClient.build_recurrence("weekly", "2026-09-08T10:00:00")

        assert recurrence["pattern"]["type"] == "weekly"
        assert recurrence["pattern"]["daysOfWeek"] == ["tuesday"]
        assert recurrence["range"]["type"] == "noEnd"

    def test_weekdays_covers_monday_to_friday(self):
        from officeclaw.calendar import CalendarClient

        pattern = CalendarClient.build_recurrence("weekdays", "2026-09-08")["pattern"]

        assert pattern["daysOfWeek"] == [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
        ]

    def test_monthly_pins_the_day_of_month(self):
        from officeclaw.calendar import CalendarClient

        pattern = CalendarClient.build_recurrence("monthly", "2026-09-08")["pattern"]

        assert pattern["type"] == "absoluteMonthly"
        assert pattern["dayOfMonth"] == 8

    def test_until_produces_an_end_date_range(self):
        from officeclaw.calendar import CalendarClient

        rng = CalendarClient.build_recurrence("daily", "2026-09-08", until="2026-12-01")["range"]

        assert rng["type"] == "endDate"
        assert rng["endDate"] == "2026-12-01"

    def test_count_produces_a_numbered_range(self):
        from officeclaw.calendar import CalendarClient

        rng = CalendarClient.build_recurrence("daily", "2026-09-08", count=6)["range"]

        assert rng["type"] == "numbered"
        assert rng["numberOfOccurrences"] == 6

    def test_until_and_count_together_are_refused(self):
        from officeclaw.calendar import CalendarClient

        with pytest.raises(ValueError, match="not both"):
            CalendarClient.build_recurrence("daily", "2026-09-08", until="2026-12-01", count=6)

    def test_unknown_pattern_is_refused(self):
        from officeclaw.calendar import CalendarClient

        with pytest.raises(ValueError, match="Unknown recurrence"):
            CalendarClient.build_recurrence("hourly", "2026-09-08")

    @patch("officeclaw.calendar.GraphClient")
    def test_recurrence_reaches_the_event_payload(self, mock_client_class):
        from officeclaw.calendar import CalendarClient

        mock_client = MagicMock()
        mock_client.post.return_value = {}
        mock_client_class.return_value = mock_client

        client = CalendarClient()
        client.create_event(
            "Weekly sync",
            "2026-09-08T10:00:00",
            "2026-09-08T11:00:00",
            recurrence=CalendarClient.build_recurrence("weekly", "2026-09-08T10:00:00"),
        )

        payload = mock_client.post.call_args[0][1]
        assert payload["recurrence"]["pattern"]["type"] == "weekly"
