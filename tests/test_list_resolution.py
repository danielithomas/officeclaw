"""
Tests for task list addressing: --list-name, defaults, and the name cache.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from officeclaw.exceptions import TaskListError

LISTS = [
    {"id": "id-tasks", "displayName": "Tasks", "wellknownListName": "defaultList"},
    {"id": "id-shop", "displayName": "🛒 Groceries", "wellknownListName": "none"},
    {"id": "id-work", "displayName": "Work", "wellknownListName": "none"},
]


@pytest.fixture
def client(tmp_path):
    """TasksClient with a mock Graph client and a cache in tmp_path."""
    with (
        patch("officeclaw.tasks.GraphClient") as mock_class,
        patch("officeclaw.tasks.LIST_CACHE_FILE", tmp_path / "list_cache.json"),
        patch("officeclaw.tasks.CACHE_DIR", tmp_path),
    ):
        from officeclaw.tasks import TasksClient

        graph = MagicMock()
        graph.get_all.return_value = LISTS
        mock_class.return_value = graph
        yield TasksClient(), graph


class TestResolveListId:
    def test_explicit_id_wins(self, client):
        tc, graph = client
        assert tc.resolve_list_id(list_id="explicit") == "explicit"
        graph.get_all.assert_not_called()

    def test_name_is_resolved(self, client):
        tc, _ = client
        with patch.dict("os.environ", {}, clear=True):
            assert tc.resolve_list_id(list_name="Work") == "id-work"

    def test_name_match_is_case_insensitive(self, client):
        tc, _ = client
        with patch.dict("os.environ", {}, clear=True):
            assert tc.resolve_list_id(list_name="  wOrK ") == "id-work"

    def test_emoji_name(self, client):
        tc, _ = client
        with patch.dict("os.environ", {}, clear=True):
            assert tc.resolve_list_id(list_name="🛒 Groceries") == "id-shop"

    def test_unknown_name_lists_what_is_available(self, client):
        tc, _ = client
        with patch.dict("os.environ", {}, clear=True), pytest.raises(TaskListError) as exc:
            tc.resolve_list_id(list_name="Nope")
        assert "Work" in str(exc.value)

    def test_ambiguous_name_is_refused_not_guessed(self, client):
        tc, graph = client
        graph.get_all.return_value = [
            {"id": "a", "displayName": "Tasks"},
            {"id": "b", "displayName": "Tasks"},
        ]
        with patch.dict("os.environ", {}, clear=True), pytest.raises(TaskListError) as exc:
            tc.resolve_list_id(list_name="Tasks")
        assert "--list-id" in str(exc.value)

    def test_env_id_used_when_no_argument(self, client):
        tc, _ = client
        with patch.dict("os.environ", {"OFFICECLAW_DEFAULT_TASK_LIST_ID": "env-id"}, clear=True):
            assert tc.resolve_list_id() == "env-id"

    def test_env_name_used_when_no_argument(self, client):
        tc, _ = client
        with patch.dict("os.environ", {"OFFICECLAW_DEFAULT_TASK_LIST_NAME": "Work"}, clear=True):
            assert tc.resolve_list_id() == "id-work"

    def test_falls_back_to_wellknown_default_list(self, client):
        tc, _ = client
        with patch.dict("os.environ", {}, clear=True):
            assert tc.resolve_list_id() == "id-tasks"

    def test_no_default_list_is_reported(self, client):
        tc, graph = client
        graph.get_all.return_value = [
            {"id": "x", "displayName": "Work", "wellknownListName": "none"}
        ]
        with patch.dict("os.environ", {}, clear=True), pytest.raises(TaskListError):
            tc.resolve_list_id()


class TestListCache:
    def test_second_lookup_uses_the_cache(self, client):
        tc, graph = client
        with patch.dict("os.environ", {}, clear=True):
            assert tc.resolve_list_id(list_name="Work") == "id-work"
            calls_after_first = graph.get_all.call_count
            assert tc.resolve_list_id(list_name="Work") == "id-work"

        assert graph.get_all.call_count == calls_after_first

    def test_clearing_the_cache_forces_a_lookup(self, client):
        tc, graph = client
        with patch.dict("os.environ", {}, clear=True):
            tc.resolve_list_id(list_name="Work")
            calls_after_first = graph.get_all.call_count
            tc.clear_list_cache()
            tc.resolve_list_id(list_name="Work")

        assert graph.get_all.call_count > calls_after_first

    def test_corrupt_cache_is_treated_as_a_miss(self, client, tmp_path):
        tc, _ = client
        (tmp_path / "list_cache.json").write_text("{not json")
        with patch.dict("os.environ", {}, clear=True):
            assert tc.resolve_list_id(list_name="Work") == "id-work"
