"""
Task operations for Outclaw.

Provides Microsoft To Do task management through Microsoft Graph API.
"""

from __future__ import annotations

import contextlib
import json
import os
import warnings
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from officeclaw.auth import CACHE_DIR, _write_private_file
from officeclaw.client import GraphClient
from officeclaw.exceptions import TaskListError

# Resolved list names are cached here; a miss falls back to a live lookup.
LIST_CACHE_FILE = CACHE_DIR / "list_cache.json"

DEFAULT_LIST_ID_ENV = "OFFICECLAW_DEFAULT_TASK_LIST_ID"
DEFAULT_LIST_NAME_ENV = "OFFICECLAW_DEFAULT_TASK_LIST_NAME"
TIMEZONE_ENV = "OFFICECLAW_TIMEZONE"


class TasksClient:
    """
    Client for Microsoft Graph Tasks (To Do) API.

    Example:
        client = TasksClient()
        lists = client.list_task_lists()
        tasks = client.list_tasks(list_id)
        client.create_task(list_id, "Buy groceries")
    """

    # Statuses Microsoft To Do defines; "active" is our own alias for
    # "anything not completed".
    TASK_STATUSES = frozenset(
        {"notStarted", "inProgress", "completed", "waitingOnOthers", "deferred"}
    )

    def __init__(self, graph_client: GraphClient | None = None) -> None:
        """Initialize tasks client."""
        self._client = graph_client or GraphClient()
        self._owns_client = graph_client is None

    # ------------------------------------------------------------------
    # List addressing
    # ------------------------------------------------------------------

    def resolve_list_id(self, list_id: str | None = None, list_name: str | None = None) -> str:
        """
        Work out which task list to operate on.

        Precedence: an explicit id, then an explicit name, then the
        OFFICECLAW_DEFAULT_TASK_LIST_ID / _NAME environment variables, then the
        account's built-in Tasks list.

        Args:
            list_id: Explicit list ID, if the caller has one
            list_name: Display name to resolve

        Returns:
            Task list ID

        Raises:
            TaskListError: If the name matches no list or several, or no
                default list can be found.
        """
        if list_id:
            return list_id
        if list_name:
            return self.find_list_id_by_name(list_name)

        env_id = os.environ.get(DEFAULT_LIST_ID_ENV, "").strip()
        if env_id:
            return env_id
        env_name = os.environ.get(DEFAULT_LIST_NAME_ENV, "").strip()
        if env_name:
            return self.find_list_id_by_name(env_name)

        return self.get_default_list_id()

    def find_list_id_by_name(self, name: str) -> str:
        """
        Resolve a task list's display name to its ID.

        Args:
            name: Display name, matched case-insensitively

        Returns:
            Task list ID

        Raises:
            TaskListError: If no list matches, or more than one does — an
                ambiguous name is reported rather than guessed at.
        """
        wanted = name.strip().lower()

        cached = self._read_cache().get(wanted)
        if cached:
            return cached

        matches = [
            lst for lst in self.list_task_lists() if lst.get("displayName", "").lower() == wanted
        ]

        if not matches:
            available = ", ".join(
                sorted(lst.get("displayName", "") for lst in self.list_task_lists())
            )
            raise TaskListError(f"No task list named {name!r}. Available lists: {available}.")
        if len(matches) > 1:
            raise TaskListError(
                f"{len(matches)} task lists are named {name!r}. Use --list-id to choose one."
            )

        list_id: str = matches[0]["id"]
        self._write_cache({wanted: list_id})
        return list_id

    def get_default_list_id(self) -> str:
        """
        ID of the account's built-in Tasks list.

        Identified by ``wellknownListName == "defaultList"`` rather than by the
        name "Tasks", which is localised per account language.

        Raises:
            TaskListError: If the account exposes no default list.
        """
        cached = self._read_cache().get(self._DEFAULT_CACHE_KEY)
        if cached:
            return cached

        for lst in self.list_task_lists():
            if lst.get("wellknownListName") == "defaultList":
                list_id: str = lst["id"]
                self._write_cache({self._DEFAULT_CACHE_KEY: list_id})
                return list_id

        raise TaskListError(
            "No default task list found. Pass --list-id or --list-name, or set "
            f"{DEFAULT_LIST_NAME_ENV}."
        )

    _DEFAULT_CACHE_KEY = "__default__"

    def _read_cache(self) -> dict[str, str]:
        """Read the name-to-ID cache, treating any problem as a miss."""
        try:
            with open(LIST_CACHE_FILE) as f:
                cache = json.load(f)
        except (OSError, ValueError):
            return {}
        return cache if isinstance(cache, dict) else {}

    def _write_cache(self, entries: dict[str, str]) -> None:
        """Merge entries into the cache. Best-effort: a failure only costs a lookup."""
        cache = self._read_cache()
        cache.update(entries)
        try:
            CACHE_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
            _write_private_file(LIST_CACHE_FILE, json.dumps(cache, indent=2))
        except OSError:
            pass

    @staticmethod
    def clear_list_cache() -> None:
        """Forget cached name-to-ID mappings (after renaming or deleting a list)."""
        with contextlib.suppress(OSError):
            LIST_CACHE_FILE.unlink()

    def list_task_lists(self) -> list[dict[str, Any]]:
        """
        List all task lists.

        Returns:
            List of task list objects
        """
        return self._client.get_all("/me/todo/lists")

    def get_task_list(self, list_id: str) -> dict[str, Any]:
        """
        Get a specific task list.

        Args:
            list_id: Task list ID

        Returns:
            Task list object
        """
        task_list: dict[str, Any] = self._client.get(f"/me/todo/lists/{list_id}")
        return task_list

    def create_task_list(self, name: str) -> dict[str, Any]:
        """
        Create a new task list.

        Args:
            name: List name

        Returns:
            Created task list object
        """
        created: dict[str, Any] = self._client.post("/me/todo/lists", {"displayName": name})
        return created

    def delete_task_list(self, list_id: str) -> None:
        """Delete a task list."""
        self._client.delete(f"/me/todo/lists/{list_id}")

    def list_tasks(
        self,
        list_id: str,
        status: str | None = None,
        limit: int | None = None,
        select: str | None = None,
        due_before: str | None = None,
        due_after: str | None = None,
        due_on: str | None = None,
        overdue: bool = False,
    ) -> list[dict[str, Any]]:
        """
        List tasks in a task list.

        Date filters are applied client-side. Microsoft To Do stores
        ``dueDateTime.dateTime`` as a string, so server-side comparisons against
        a date fail on operand types; the whole list is fetched and filtered
        here instead. Fine for personal task lists, not for very large ones.

        Due dates are compared by calendar date, not instant — To Do drops the
        time portion of a due date, so an instant comparison would be a fiction.

        Args:
            list_id: Task list ID
            status: Filter by status — "active" (anything not completed) or one
                of TASK_STATUSES
            limit: Maximum tasks to return
            select: Fields to return
            due_before: Only tasks due strictly before this date (YYYY-MM-DD)
            due_after: Only tasks due strictly after this date (YYYY-MM-DD)
            due_on: Only tasks due on this date (YYYY-MM-DD)
            overdue: Only tasks due before today — in the user's timezone, see
                :meth:`today` — and not yet completed

        Returns:
            List of task objects
        """
        params: dict[str, Any] = {}

        if select:
            params["$select"] = select

        if status:
            if status == "active":
                params["$filter"] = "status ne 'completed'"
            elif status in self.TASK_STATUSES:
                # Matched against a fixed set rather than interpolated, so the
                # value cannot alter the filter expression.
                params["$filter"] = f"status eq '{status}'"
            else:
                allowed = ", ".join(sorted({"active", *self.TASK_STATUSES}))
                raise ValueError(f"Unknown task status {status!r}. Expected one of: {allowed}.")

        date_filtered = any((due_before, due_after, due_on, overdue))
        tasks = self._client.get_all(
            f"/me/todo/lists/{list_id}/tasks",
            params=params,
            # A server-side limit would truncate before the date filter runs.
            limit=None if date_filtered else limit,
        )

        if not date_filtered:
            return tasks

        tasks = [
            task
            for task in tasks
            if self._matches_due_filters(task, due_before, due_after, due_on, overdue)
        ]
        return tasks[:limit] if limit else tasks

    @staticmethod
    def today() -> date:
        """
        Today's date where the user is, not in UTC.

        A To Do due date carries no time or offset — "due the 5th" means the
        5th on the user's own calendar. Comparing it against the UTC date makes
        `--overdue` wrong for hours every day east of Greenwich: at 9am in
        Melbourne it is still yesterday in UTC, so a task due yesterday would
        not be reported overdue — in exactly the morning window a daily task
        briefing runs.

        OFFICECLAW_TIMEZONE (or ``timezone`` in the config file) pins the zone;
        otherwise the system's local date is used.
        """
        tz_name = os.environ.get(TIMEZONE_ENV, "").strip()
        if tz_name:
            try:
                return datetime.now(ZoneInfo(tz_name)).date()
            except (ZoneInfoNotFoundError, ValueError) as e:
                warnings.warn(
                    f"Ignoring {TIMEZONE_ENV}={tz_name!r} ({e}); using the system timezone. "
                    "On Windows this needs the 'tzdata' package.",
                    stacklevel=2,
                )
        return date.today()

    @staticmethod
    def task_due_date(task: dict[str, Any]) -> date | None:
        """Calendar date a task is due, or None when it has no due date."""
        raw = (task.get("dueDateTime") or {}).get("dateTime")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")[:26]).date()
        except ValueError:
            return None

    @classmethod
    def _matches_due_filters(
        cls,
        task: dict[str, Any],
        due_before: str | None,
        due_after: str | None,
        due_on: str | None,
        overdue: bool,
    ) -> bool:
        """Whether one task satisfies every requested date filter."""
        due = cls.task_due_date(task)
        if due is None:
            return False  # A task with no due date matches no date filter.

        if due_before and not due < date.fromisoformat(due_before):
            return False
        if due_after and not due > date.fromisoformat(due_after):
            return False
        if due_on and due != date.fromisoformat(due_on):
            return False
        if overdue:
            return due < cls.today() and cls._is_open(task)
        return True

    @staticmethod
    def _is_open(task: dict[str, Any]) -> bool:
        """Whether a task is still outstanding."""
        return task.get("status") != "completed"

    def get_task(self, list_id: str, task_id: str) -> dict[str, Any]:
        """
        Get a specific task.

        Args:
            list_id: Task list ID
            task_id: Task ID

        Returns:
            Task object with full details
        """
        task: dict[str, Any] = self._client.get(f"/me/todo/lists/{list_id}/tasks/{task_id}")
        return task

    def create_task(
        self,
        list_id: str,
        title: str,
        body: str | None = None,
        due_date: str | None = None,
        importance: str = "normal",
        reminder: str | None = None,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new task.

        Args:
            list_id: Task list ID
            title: Task title
            body: Task description
            due_date: Due date (YYYY-MM-DD)
            importance: "low", "normal", or "high"
            reminder: Reminder datetime (ISO format)
            categories: Category labels. They are stored and returned as given;
                colour comes from the mailbox's master category list, which
                OfficeClaw does not manage.

        Returns:
            Created task object
        """
        task: dict[str, Any] = {
            "title": title,
            "importance": importance,
        }

        if body:
            task["body"] = {
                "content": body,
                "contentType": "text",
            }

        if due_date:
            task["dueDateTime"] = {
                "dateTime": f"{due_date}T00:00:00.0000000",
                "timeZone": "UTC",
            }

        if reminder:
            task["reminderDateTime"] = {
                "dateTime": reminder,
                "timeZone": "UTC",
            }
            task["isReminderOn"] = True

        if categories:
            task["categories"] = categories

        created: dict[str, Any] = self._client.post(f"/me/todo/lists/{list_id}/tasks", task)
        return created

    def update_task(
        self,
        list_id: str,
        task_id: str,
        title: str | None = None,
        body: str | None = None,
        due_date: str | None = None,
        importance: str | None = None,
        reminder: str | None = None,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Update a task.

        Args:
            list_id: Task list ID
            task_id: Task ID
            title: New title
            body: New description
            due_date: New due date
            importance: New importance
            reminder: New reminder datetime (ISO format); "" clears it
            categories: Replacement category labels

        Returns:
            Updated task object
        """
        data: dict[str, Any] = {}

        if title is not None:
            data["title"] = title

        if body is not None:
            data["body"] = {
                "content": body,
                "contentType": "text",
            }

        if due_date is not None:
            if due_date:
                data["dueDateTime"] = {
                    "dateTime": f"{due_date}T00:00:00.0000000",
                    "timeZone": "UTC",
                }
            else:
                data["dueDateTime"] = None

        if importance is not None:
            data["importance"] = importance

        if reminder is not None:
            if reminder:
                data["reminderDateTime"] = {"dateTime": reminder, "timeZone": "UTC"}
                data["isReminderOn"] = True
            else:
                data["reminderDateTime"] = None
                data["isReminderOn"] = False

        if categories is not None:
            data["categories"] = categories

        updated: dict[str, Any] = self._client.patch(
            f"/me/todo/lists/{list_id}/tasks/{task_id}",
            data,
        )
        return updated

    def complete_task(
        self,
        list_id: str,
        task_id: str,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        """
        Mark a task as completed.

        Args:
            list_id: Task list ID
            task_id: Task ID
            completed_at: Completion datetime (defaults to now)

        Returns:
            Updated task object
        """
        if completed_at is None:
            completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")

        data = {
            "status": "completed",
            "completedDateTime": {
                "dateTime": completed_at,
                "timeZone": "UTC",
            },
        }

        updated: dict[str, Any] = self._client.patch(
            f"/me/todo/lists/{list_id}/tasks/{task_id}",
            data,
        )
        return updated

    def reopen_task(self, list_id: str, task_id: str) -> dict[str, Any]:
        """
        Reopen a completed task.

        Args:
            list_id: Task list ID
            task_id: Task ID

        Returns:
            Updated task object
        """
        data = {
            "status": "notStarted",
            "completedDateTime": None,
        }

        updated: dict[str, Any] = self._client.patch(
            f"/me/todo/lists/{list_id}/tasks/{task_id}",
            data,
        )
        return updated

    def delete_task(self, list_id: str, task_id: str) -> None:
        """Delete a task."""
        self._client.delete(f"/me/todo/lists/{list_id}/tasks/{task_id}")

    def close(self) -> None:
        """Close the client."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> TasksClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
