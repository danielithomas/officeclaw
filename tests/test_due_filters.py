"""
Tests for client-side due-date filtering on tasks list.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time


def task(title: str, due: str | None, status: str = "notStarted") -> dict:
    """Task as Graph returns it — due dates are a nested dateTimeTimeZone."""
    payload: dict = {"id": title, "title": title, "status": status}
    if due:
        payload["dueDateTime"] = {"dateTime": f"{due}T00:00:00.0000000", "timeZone": "UTC"}
    return payload


TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)

TASKS = [
    task("overdue", YESTERDAY.isoformat()),
    task("today", TODAY.isoformat()),
    task("tomorrow", TOMORROW.isoformat()),
    task("done-overdue", YESTERDAY.isoformat(), status="completed"),
    task("no-due-date", None),
]


@pytest.fixture
def client():
    with patch("officeclaw.tasks.GraphClient") as mock_class:
        from officeclaw.tasks import TasksClient

        graph = MagicMock()
        graph.get_all.return_value = TASKS
        mock_class.return_value = graph
        yield TasksClient(), graph


def titles(results):
    return [t["title"] for t in results]


class TestDueFilters:
    def test_no_filter_returns_everything(self, client):
        tc, _ = client
        assert len(tc.list_tasks("l1")) == len(TASKS)

    def test_due_on(self, client):
        tc, _ = client
        assert titles(tc.list_tasks("l1", due_on=TODAY.isoformat())) == ["today"]

    def test_due_before_is_exclusive(self, client):
        tc, _ = client
        assert titles(tc.list_tasks("l1", due_before=TODAY.isoformat())) == [
            "overdue",
            "done-overdue",
        ]

    def test_due_after_is_exclusive(self, client):
        tc, _ = client
        assert titles(tc.list_tasks("l1", due_after=TODAY.isoformat())) == ["tomorrow"]

    def test_overdue_excludes_completed(self, client):
        tc, _ = client
        assert titles(tc.list_tasks("l1", overdue=True)) == ["overdue"]

    def test_tasks_without_due_date_never_match(self, client):
        tc, _ = client
        for kwargs in (
            {"due_on": TODAY.isoformat()},
            {"due_before": TOMORROW.isoformat()},
            {"due_after": YESTERDAY.isoformat()},
            {"overdue": True},
        ):
            assert "no-due-date" not in titles(tc.list_tasks("l1", **kwargs))

    def test_filters_combine(self, client):
        tc, _ = client
        results = tc.list_tasks(
            "l1", due_after=YESTERDAY.isoformat(), due_before=TOMORROW.isoformat()
        )
        assert titles(results) == ["today"]

    def test_limit_applies_after_filtering(self, client):
        tc, graph = client
        results = tc.list_tasks("l1", due_before=TOMORROW.isoformat(), limit=1)

        assert len(results) == 1
        # The server-side limit must not truncate before the date filter runs.
        assert graph.get_all.call_args[1]["limit"] is None

    def test_limit_without_date_filter_is_server_side(self, client):
        tc, graph = client
        tc.list_tasks("l1", limit=5)
        assert graph.get_all.call_args[1]["limit"] == 5

    def test_malformed_due_date_does_not_crash(self, client):
        tc, graph = client
        graph.get_all.return_value = [
            {"id": "x", "title": "bad", "dueDateTime": {"dateTime": "not-a-date"}}
        ]
        assert tc.list_tasks("l1", overdue=True) == []


class TestTodayIsLocal:
    """`--overdue` must mean "before today where the user is", not in UTC."""

    def test_timezone_env_selects_the_date(self):
        from officeclaw.tasks import TasksClient

        # 23:30 UTC on the 5th is already 09:30 on the 6th in Melbourne.
        with freeze_time("2026-09-05T23:30:00Z"):
            with patch.dict("os.environ", {"OFFICECLAW_TIMEZONE": "UTC"}):
                assert TasksClient.today() == date(2026, 9, 5)
            with patch.dict("os.environ", {"OFFICECLAW_TIMEZONE": "Australia/Melbourne"}):
                assert TasksClient.today() == date(2026, 9, 6)

    def test_unknown_timezone_warns_and_falls_back(self):
        from officeclaw.tasks import TasksClient

        with (
            patch.dict("os.environ", {"OFFICECLAW_TIMEZONE": "Mars/Olympus_Mons"}),
            pytest.warns(UserWarning, match="OFFICECLAW_TIMEZONE"),
        ):
            assert TasksClient.today() == date.today()

    @freeze_time("2026-09-05T23:30:00Z")
    def test_morning_huddle_window_reports_yesterday_as_overdue(self, client):
        """The bug this guards: 9am in Melbourne is still 'yesterday' in UTC."""
        tc, graph = client
        graph.get_all.return_value = [task("due-5th", "2026-09-05")]

        with patch.dict("os.environ", {"OFFICECLAW_TIMEZONE": "Australia/Melbourne"}):
            assert titles(tc.list_tasks("l1", overdue=True)) == ["due-5th"]

    @freeze_time("2026-09-05T23:30:00Z")
    def test_same_instant_in_utc_does_not_report_it_overdue(self, client):
        """In UTC the 5th is still today, so the same task is not yet late."""
        tc, graph = client
        graph.get_all.return_value = [task("due-5th", "2026-09-05")]

        with patch.dict("os.environ", {"OFFICECLAW_TIMEZONE": "UTC"}):
            assert tc.list_tasks("l1", overdue=True) == []
