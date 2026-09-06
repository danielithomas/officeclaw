"""
Tests for the Outclaw tasks module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestTasksClient:
    """Test TasksClient operations."""

    @patch("officeclaw.tasks.GraphClient")
    def test_list_task_lists(self, mock_client_class, sample_task_list):
        """Test listing task lists."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = [sample_task_list]
        mock_client_class.return_value = mock_client

        client = TasksClient()
        lists = client.list_task_lists()

        assert len(lists) == 1
        assert lists[0]["displayName"] == sample_task_list["displayName"]
        mock_client.get_all.assert_called_with("/me/todo/lists")

    @patch("officeclaw.tasks.GraphClient")
    def test_list_tasks(self, mock_client_class, sample_tasks):
        """Test listing tasks in a list."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_tasks
        mock_client_class.return_value = mock_client

        client = TasksClient()
        tasks = client.list_tasks("list-123")

        assert len(tasks) == 3
        mock_client.get_all.assert_called_once()
        call_args = mock_client.get_all.call_args
        assert "/me/todo/lists/list-123/tasks" in call_args[0][0]

    @patch("officeclaw.tasks.GraphClient")
    def test_list_tasks_active_only(self, mock_client_class, sample_tasks):
        """Test listing only active tasks."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = [sample_tasks[0]]
        mock_client_class.return_value = mock_client

        client = TasksClient()
        client.list_tasks("list-123", status="active")

        call_args = mock_client.get_all.call_args
        params = call_args[1]["params"]
        assert "$filter" in params
        assert "status ne 'completed'" in params["$filter"]

    @patch("officeclaw.tasks.GraphClient")
    def test_list_tasks_completed_only(self, mock_client_class, sample_tasks):
        """Test listing only completed tasks."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = [sample_tasks[1]]
        mock_client_class.return_value = mock_client

        client = TasksClient()
        client.list_tasks("list-123", status="completed")

        call_args = mock_client.get_all.call_args
        params = call_args[1]["params"]
        assert "$filter" in params
        assert "status eq 'completed'" in params["$filter"]

    @patch("officeclaw.tasks.GraphClient")
    def test_get_task(self, mock_client_class, sample_task):
        """Test getting a specific task."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.get.return_value = sample_task
        mock_client_class.return_value = mock_client

        client = TasksClient()
        task = client.get_task("list-123", "task-123")

        assert task["title"] == sample_task["title"]
        mock_client.get.assert_called_with("/me/todo/lists/list-123/tasks/task-123")

    @patch("officeclaw.tasks.GraphClient")
    def test_create_task(self, mock_client_class, sample_task):
        """Test creating a task."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.post.return_value = sample_task
        mock_client_class.return_value = mock_client

        client = TasksClient()
        task = client.create_task("list-123", "Complete report")

        assert task["title"] == sample_task["title"]
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/me/todo/lists/list-123/tasks"
        assert call_args[0][1]["title"] == "Complete report"

    @patch("officeclaw.tasks.GraphClient")
    def test_create_task_with_due_date(self, mock_client_class, sample_task):
        """Test creating task with due date."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.post.return_value = sample_task
        mock_client_class.return_value = mock_client

        client = TasksClient()
        client.create_task("list-123", "Complete report", due_date="2026-02-20")

        call_args = mock_client.post.call_args
        task_data = call_args[0][1]
        assert "dueDateTime" in task_data
        assert "2026-02-20" in task_data["dueDateTime"]["dateTime"]

    @patch("officeclaw.tasks.GraphClient")
    def test_create_task_with_body(self, mock_client_class, sample_task):
        """Test creating task with description."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.post.return_value = sample_task
        mock_client_class.return_value = mock_client

        client = TasksClient()
        client.create_task("list-123", "Task", body="Task description")

        call_args = mock_client.post.call_args
        task_data = call_args[0][1]
        assert "body" in task_data
        assert task_data["body"]["content"] == "Task description"

    @patch("officeclaw.tasks.GraphClient")
    def test_complete_task(self, mock_client_class, sample_task):
        """Test completing a task."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        completed = {**sample_task, "status": "completed"}
        mock_client.patch.return_value = completed
        mock_client_class.return_value = mock_client

        client = TasksClient()
        result = client.complete_task("list-123", "task-123")

        assert result["status"] == "completed"
        call_args = mock_client.patch.call_args
        assert call_args[0][0] == "/me/todo/lists/list-123/tasks/task-123"
        assert call_args[0][1]["status"] == "completed"
        assert "completedDateTime" in call_args[0][1]

    @patch("officeclaw.tasks.GraphClient")
    def test_complete_task_with_timestamp(self, mock_client_class, sample_task):
        """Test completing task with specific timestamp."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        completed = {**sample_task, "status": "completed"}
        mock_client.patch.return_value = completed
        mock_client_class.return_value = mock_client

        client = TasksClient()
        client.complete_task(
            "list-123",
            "task-123",
            completed_at="2026-02-12T15:30:00.0000000Z",
        )

        call_args = mock_client.patch.call_args
        assert call_args[0][1]["completedDateTime"]["dateTime"] == "2026-02-12T15:30:00.0000000Z"

    @patch("officeclaw.tasks.GraphClient")
    def test_reopen_task(self, mock_client_class, sample_task):
        """Test reopening a completed task."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        reopened = {**sample_task, "status": "notStarted"}
        mock_client.patch.return_value = reopened
        mock_client_class.return_value = mock_client

        client = TasksClient()
        result = client.reopen_task("list-123", "task-123")

        assert result["status"] == "notStarted"
        call_args = mock_client.patch.call_args
        assert call_args[0][1]["status"] == "notStarted"
        assert call_args[0][1]["completedDateTime"] is None

    @patch("officeclaw.tasks.GraphClient")
    def test_delete_task(self, mock_client_class):
        """Test deleting a task."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.delete.return_value = None
        mock_client_class.return_value = mock_client

        client = TasksClient()
        client.delete_task("list-123", "task-123")

        mock_client.delete.assert_called_with("/me/todo/lists/list-123/tasks/task-123")

    @patch("officeclaw.tasks.GraphClient")
    def test_create_task_list(self, mock_client_class, sample_task_list):
        """Test creating a task list."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.post.return_value = sample_task_list
        mock_client_class.return_value = mock_client

        client = TasksClient()
        client.create_task_list("My New List")

        mock_client.post.assert_called_with(
            "/me/todo/lists",
            {"displayName": "My New List"},
        )

    @patch("officeclaw.tasks.GraphClient")
    def test_update_task(self, mock_client_class, sample_task):
        """Test updating a task."""
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        updated = {**sample_task, "title": "Updated title"}
        mock_client.patch.return_value = updated
        mock_client_class.return_value = mock_client

        client = TasksClient()
        result = client.update_task("list-123", "task-123", title="Updated title")

        assert result["title"] == "Updated title"
        call_args = mock_client.patch.call_args
        assert call_args[0][1]["title"] == "Updated title"


class TestTaskStatusFilter:
    """list_tasks only accepts statuses Microsoft To Do defines."""

    @patch("officeclaw.tasks.GraphClient")
    def test_known_status_is_filtered(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = []
        mock_client_class.return_value = mock_client

        TasksClient().list_tasks("list-123", status="inProgress")

        params = mock_client.get_all.call_args[1]["params"]
        assert params["$filter"] == "status eq 'inProgress'"

    @patch("officeclaw.tasks.GraphClient")
    def test_unknown_status_is_rejected(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        with pytest.raises(ValueError, match="Unknown task status"):
            TasksClient().list_tasks("list-123", status="completed' or startswith(id,'")

        mock_client.get_all.assert_not_called()


class TestTaskMetadata:
    """Categories and reminders round-trip through create and update."""

    @patch("officeclaw.tasks.GraphClient")
    def test_create_sets_reminder_and_categories(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.post.return_value = {}
        mock_client_class.return_value = mock_client

        TasksClient().create_task(
            "l1",
            "Dentist",
            reminder="2026-09-10T08:00:00",
            categories=["health"],
        )

        payload = mock_client.post.call_args[0][1]
        assert payload["reminderDateTime"]["dateTime"] == "2026-09-10T08:00:00"
        assert payload["isReminderOn"] is True
        assert payload["categories"] == ["health"]

    @patch("officeclaw.tasks.GraphClient")
    def test_update_can_clear_a_reminder(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.patch.return_value = {}
        mock_client_class.return_value = mock_client

        TasksClient().update_task("l1", "t1", reminder="")

        payload = mock_client.patch.call_args[0][1]
        assert payload["reminderDateTime"] is None
        assert payload["isReminderOn"] is False


class TestTaskRecurrence:
    """--repeat on tasks, sharing the calendar recurrence parser (PR #9)."""

    @patch("officeclaw.tasks.GraphClient")
    def test_create_sends_a_recurrence(self, mock_client_class):
        from officeclaw import recurrence
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.post.return_value = {}
        mock_client_class.return_value = mock_client

        TasksClient().create_task(
            "l1", "Water plants", recurrence=recurrence.build("weekly:MON,THU", "2026-09-08")
        )

        payload = mock_client.post.call_args[0][1]
        assert payload["recurrence"]["pattern"]["daysOfWeek"] == ["monday", "thursday"]

    @patch("officeclaw.tasks.GraphClient")
    def test_update_can_stop_a_task_repeating(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.patch.return_value = {}
        mock_client_class.return_value = mock_client

        TasksClient().update_task("l1", "t1", clear_recurrence=True)

        assert mock_client.patch.call_args[0][1]["recurrence"] is None

    @patch("officeclaw.tasks.GraphClient")
    def test_update_can_clear_a_reminder(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.patch.return_value = {}
        mock_client_class.return_value = mock_client

        TasksClient().update_task("l1", "t1", clear_reminder=True)

        payload = mock_client.patch.call_args[0][1]
        assert payload["reminderDateTime"] is None and payload["isReminderOn"] is False


class TestChecklistItems:
    """Steps within a task (PR #9)."""

    @patch("officeclaw.tasks.GraphClient")
    def test_list(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = [{"id": "i1", "displayName": "Step", "isChecked": False}]
        mock_client_class.return_value = mock_client

        items = TasksClient().list_checklist_items("l1", "t1")

        assert items[0]["displayName"] == "Step"
        assert mock_client.get_all.call_args[0][0].endswith("/tasks/t1/checklistItems")

    @patch("officeclaw.tasks.GraphClient")
    def test_add(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.post.return_value = {"id": "i1"}
        mock_client_class.return_value = mock_client

        TasksClient().add_checklist_item("l1", "t1", "Buy pots")

        assert mock_client.post.call_args[0][1] == {"displayName": "Buy pots"}

    @patch("officeclaw.tasks.GraphClient")
    def test_check_and_uncheck(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client.patch.return_value = {}
        mock_client_class.return_value = mock_client

        client = TasksClient()
        client.check_checklist_item("l1", "t1", "i1")
        assert mock_client.patch.call_args[0][1] == {"isChecked": True}

        client.check_checklist_item("l1", "t1", "i1", is_checked=False)
        assert mock_client.patch.call_args[0][1] == {"isChecked": False}

    @patch("officeclaw.tasks.GraphClient")
    def test_delete(self, mock_client_class):
        from officeclaw.tasks import TasksClient

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        TasksClient().delete_checklist_item("l1", "t1", "i1")

        assert mock_client.delete.call_args[0][0].endswith("/checklistItems/i1")
