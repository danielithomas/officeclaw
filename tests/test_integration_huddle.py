"""
End-to-end check of the Morning Huddle scenario against a real account.

Marked ``integration``: skipped by default, run by the CI integration job
(`pytest -m integration`) or locally once `officeclaw auth login` has been run.
This is the acceptance test for the 1.1.0 task work — resolve a list by name,
create a task, find it through the due-date filters, and clean up.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.integration

MARKER = "officeclaw integration test — safe to delete"


@pytest.fixture(scope="module")
def tasks_client():
    """A TasksClient against the signed-in account, or skip."""
    from officeclaw.auth import TokenManager
    from officeclaw.tasks import TasksClient

    if not TokenManager().is_authenticated:
        pytest.skip("Not authenticated; run 'officeclaw auth login' first")

    with TasksClient() as client:
        yield client


@pytest.fixture
def temporary_task(tasks_client):
    """A task due yesterday in the default list, removed afterwards."""
    list_id = tasks_client.resolve_list_id()
    task = tasks_client.create_task(
        list_id,
        MARKER,
        body="Created by the OfficeClaw test suite.",
        due_date=(date.today() - timedelta(days=1)).isoformat(),
        importance="low",
    )
    try:
        yield list_id, task
    finally:
        tasks_client.delete_task(list_id, task["id"])


class TestMorningHuddle:
    def test_default_list_resolves(self, tasks_client):
        assert tasks_client.resolve_list_id()

    def test_list_name_resolves_to_the_same_list(self, tasks_client):
        lists = tasks_client.list_task_lists()
        default = next(lst for lst in lists if lst.get("wellknownListName") == "defaultList")

        assert tasks_client.find_list_id_by_name(default["displayName"]) == default["id"]

    def test_overdue_finds_the_task(self, temporary_task, tasks_client):
        list_id, task = temporary_task

        overdue = tasks_client.list_tasks(list_id, overdue=True)

        assert task["id"] in [t["id"] for t in overdue]

    def test_due_on_yesterday_finds_the_task(self, temporary_task, tasks_client):
        list_id, task = temporary_task
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        found = tasks_client.list_tasks(list_id, due_on=yesterday)

        assert task["id"] in [t["id"] for t in found]

    def test_completed_task_drops_out_of_overdue(self, temporary_task, tasks_client):
        list_id, task = temporary_task
        tasks_client.complete_task(list_id, task["id"])

        overdue = tasks_client.list_tasks(list_id, overdue=True)

        assert task["id"] not in [t["id"] for t in overdue]

    def test_status_filter_is_accepted_by_graph(self, tasks_client):
        """Spike S1: the server-side status filter is exercised for real here."""
        list_id = tasks_client.resolve_list_id()

        assert isinstance(tasks_client.list_tasks(list_id, status="completed"), list)
