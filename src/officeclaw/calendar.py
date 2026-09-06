"""
Calendar operations for Outclaw.

Provides calendar management through Microsoft Graph API.
"""

from __future__ import annotations

from typing import Any

from officeclaw import policy
from officeclaw import recurrence as recurrence_module
from officeclaw.client import GraphClient


class CalendarClient:
    """
    Client for Microsoft Graph Calendar API.

    Example:
        client = CalendarClient()
        events = client.list_events("2026-02-01", "2026-02-28")
        client.create_event("Meeting", "2026-02-15T10:00:00", "2026-02-15T11:00:00")
    """

    def __init__(self, graph_client: GraphClient | None = None) -> None:
        """Initialize calendar client."""
        self._client = graph_client or GraphClient()
        self._owns_client = graph_client is None

    def list_events(
        self,
        start: str,
        end: str,
        limit: int = 50,
        timezone: str | None = None,
        select: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List calendar events in a date range.

        Args:
            start: Start date (YYYY-MM-DD or ISO datetime)
            end: End date (YYYY-MM-DD or ISO datetime)
            limit: Maximum events to return
            timezone: Timezone for results (e.g., "Pacific Standard Time")
            select: Fields to return

        Returns:
            List of event objects
        """
        # Normalize dates to ISO format
        start_dt = self._normalize_datetime(start)
        end_dt = self._normalize_datetime(end, end_of_day=True)

        params: dict[str, Any] = {
            "startDateTime": start_dt,
            "endDateTime": end_dt,
            "$top": limit,
            "$orderby": "start/dateTime",
        }

        if select:
            params["$select"] = select
        else:
            params["$select"] = (
                "id,subject,start,end,location,organizer,isAllDay,isCancelled,bodyPreview"
            )

        # Graph returns times in the mailbox's default timezone unless asked
        # otherwise, and only via a header.
        headers = {"Prefer": f'outlook.timezone="{timezone}"'} if timezone else None

        return self._client.get_all(
            "/me/calendarView",
            params=params,
            limit=limit,
            headers=headers,
        )

    # Recurrence spellings accepted by --recurrence; the parser is shared with
    # tasks, so `weekly:MON,WED` means the same thing in both.
    RECURRENCE_PATTERNS = recurrence_module.KINDS

    @staticmethod
    def build_recurrence(
        pattern: str,
        start: str,
        until: str | None = None,
        count: int | None = None,
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        """
        Build a patternedRecurrence from a shorthand spec.

        See :mod:`officeclaw.recurrence` for the accepted spellings.

        Raises:
            ValueError: If the spec is unknown, or both until and count given.
        """
        return recurrence_module.build(pattern, start, until=until, count=count, timezone=timezone)

    def get_event(self, event_id: str) -> dict[str, Any]:
        """
        Get a specific event.

        Args:
            event_id: Event ID

        Returns:
            Event object with full details
        """
        event: dict[str, Any] = self._client.get(f"/me/events/{event_id}")
        return event

    def create_event(
        self,
        subject: str,
        start: str,
        end: str,
        location: str | None = None,
        body: str | None = None,
        attendees: list[str] | None = None,
        timezone: str = "UTC",
        is_all_day: bool = False,
        is_online_meeting: bool = False,
        recurrence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a calendar event.

        Args:
            subject: Event subject
            start: Start datetime (ISO format)
            end: End datetime (ISO format)
            location: Event location
            body: Event description
            attendees: List of attendee emails
            timezone: Timezone for start/end
            is_all_day: All-day event
            is_online_meeting: Create Teams meeting
            recurrence: patternedRecurrence object; see build_recurrence()

        Returns:
            Created event object
        """
        event: dict[str, Any] = {
            "subject": subject,
            "start": {
                "dateTime": self._normalize_datetime(start),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": self._normalize_datetime(end),
                "timeZone": timezone,
            },
            "isAllDay": is_all_day,
        }

        if location:
            event["location"] = {"displayName": location}

        if body:
            event["body"] = {
                "contentType": "Text",
                "content": body,
            }

        if attendees:
            # A meeting invitation is email: Graph mails every attendee. This
            # is the same allowlist that governs `mail send`, for the same
            # reason — otherwise an agent blocked from mailing someone could
            # simply invite them instead.
            policy.check_recipients(attendees, action="calendar-invite", subject=subject)
            event["attendees"] = [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in attendees
            ]

        if is_online_meeting:
            event["isOnlineMeeting"] = True
            event["onlineMeetingProvider"] = "teamsForBusiness"

        if recurrence:
            event["recurrence"] = recurrence

        created: dict[str, Any] = self._client.post("/me/events", event)
        return created

    def update_event(
        self,
        event_id: str,
        subject: str | None = None,
        start: str | None = None,
        end: str | None = None,
        location: str | None = None,
        body: str | None = None,
        attendees: list[str] | None = None,
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        """
        Update a calendar event.

        Args:
            event_id: Event ID
            subject: New subject
            start: New start datetime
            end: New end datetime
            location: New location
            body: New description
            attendees: Replacement attendee list; checked against the recipient
                allowlist, since updating attendees sends invitations
            timezone: Timezone for dates

        Returns:
            Updated event object
        """
        data: dict[str, Any] = {}

        if subject is not None:
            data["subject"] = subject

        if start is not None:
            data["start"] = {
                "dateTime": self._normalize_datetime(start),
                "timeZone": timezone,
            }

        if end is not None:
            data["end"] = {
                "dateTime": self._normalize_datetime(end),
                "timeZone": timezone,
            }

        if location is not None:
            data["location"] = {"displayName": location}

        if body is not None:
            data["body"] = {
                "contentType": "Text",
                "content": body,
            }

        if attendees is not None:
            policy.check_recipients(attendees, action="calendar-invite", subject=subject)
            data["attendees"] = [
                {"emailAddress": {"address": email}, "type": "required"} for email in attendees
            ]

        updated: dict[str, Any] = self._client.patch(f"/me/events/{event_id}", data)
        return updated

    def delete_event(self, event_id: str) -> None:
        """Delete a calendar event."""
        self._client.delete(f"/me/events/{event_id}")

    def accept_event(self, event_id: str, comment: str = "") -> None:
        """Accept a meeting invitation."""
        self._client.post(
            f"/me/events/{event_id}/accept",
            {"comment": comment, "sendResponse": True},
        )

    def decline_event(self, event_id: str, comment: str = "") -> None:
        """Decline a meeting invitation."""
        self._client.post(
            f"/me/events/{event_id}/decline",
            {"comment": comment, "sendResponse": True},
        )

    def tentatively_accept_event(self, event_id: str, comment: str = "") -> None:
        """Tentatively accept a meeting invitation."""
        self._client.post(
            f"/me/events/{event_id}/tentativelyAccept",
            {"comment": comment, "sendResponse": True},
        )

    def list_calendars(self) -> list[dict[str, Any]]:
        """List all calendars."""
        return self._client.get_all("/me/calendars")

    def _normalize_datetime(self, dt: str, end_of_day: bool = False) -> str:
        """
        Normalize datetime string to ISO format.

        Args:
            dt: Date or datetime string
            end_of_day: If True and only date provided, use 23:59:59

        Returns:
            ISO formatted datetime string
        """
        # Already has time component
        if "T" in dt:
            # Remove any Z suffix and microseconds
            dt = dt.replace("Z", "")
            if "." in dt:
                dt = dt.split(".")[0]
            return dt

        # Just a date - add time
        if end_of_day:
            return f"{dt}T23:59:59"
        return f"{dt}T00:00:00"

    def close(self) -> None:
        """Close the client."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> CalendarClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
