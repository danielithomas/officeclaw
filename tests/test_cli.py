"""
Tests for the Outclaw CLI.

Tests command parsing, output formatting, and error handling.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


class TestCliHelp:
    """Test CLI help and version commands."""

    def test_help_shows_commands(self):
        """Test that --help shows available commands."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "mail" in result.output.lower()
        assert "calendar" in result.output.lower()
        assert "tasks" in result.output.lower()
        assert "auth" in result.output.lower()

    def test_version_shows_version(self):
        """Test that --version shows version number."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "1." in result.output or "officeclaw" in result.output.lower()

    def test_mail_help(self):
        """Test mail subcommand help."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mail", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output
        assert "get" in result.output
        assert "send" in result.output

    def test_calendar_help(self):
        """Test calendar subcommand help."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["calendar", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output
        assert "create" in result.output

    def test_tasks_help(self):
        """Test tasks subcommand help."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["tasks", "--help"])

        assert result.exit_code == 0
        assert "list-lists" in result.output
        assert "list" in result.output
        assert "create" in result.output
        assert "complete" in result.output

    def test_auth_help(self):
        """Test auth subcommand help."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["auth", "--help"])

        assert result.exit_code == 0
        assert "login" in result.output
        assert "logout" in result.output
        assert "status" in result.output


class TestMailCommands:
    """Test mail-related CLI commands."""

    @patch("officeclaw.cli.GraphClient")
    def test_mail_list_success(self, mock_client_class, sample_messages):
        """Test successful mail list command."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_messages
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(main, ["mail", "list", "--limit", "10"])

        assert result.exit_code == 0

    @patch("officeclaw.cli.GraphClient")
    def test_mail_list_json_output(self, mock_client_class, sample_messages):
        """Test mail list outputs valid JSON."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_messages
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(main, ["--json", "mail", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "status" in data
        assert data["status"] == "success"

    def test_mail_get_requires_message_id(self):
        """Test mail get requires message-id argument."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mail", "get"])

        assert result.exit_code != 0

    def test_mail_send_requires_options(self):
        """Test mail send requires all options."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mail", "send"])

        assert result.exit_code != 0


class TestCalendarCommands:
    """Test calendar-related CLI commands."""

    @patch("officeclaw.cli.GraphClient")
    def test_calendar_list_with_dates(self, mock_client_class, sample_events):
        """Test calendar list with date range."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_events
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(
            main, ["calendar", "list", "--start", "2026-02-01", "--end", "2026-02-28"]
        )

        assert result.exit_code == 0

    def test_calendar_list_requires_dates(self):
        """Test calendar list requires start and end dates."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["calendar", "list"])

        assert result.exit_code != 0

    def test_calendar_create_requires_options(self):
        """Test calendar create requires subject, start, end."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["calendar", "create"])

        assert result.exit_code != 0


class TestTasksCommands:
    """Test tasks-related CLI commands."""

    @patch("officeclaw.cli.GraphClient")
    def test_tasks_list_lists(self, mock_client_class, sample_task_list):
        """Test listing task lists."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = [sample_task_list]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(main, ["tasks", "list-lists"])

        assert result.exit_code == 0

    @patch("officeclaw.tasks.GraphClient")
    def test_tasks_complete(self, mock_client_class, sample_task):
        """Test completing a task."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        completed_task = {**sample_task, "status": "completed"}
        mock_client.patch.return_value = completed_task
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(
            main, ["tasks", "complete", "--list-id", "list-123", "--task-id", "task-123"]
        )

        assert result.exit_code == 0

    @patch("officeclaw.tasks.GraphClient")
    def test_tasks_list_falls_back_to_default_list(self, mock_client_class, sample_task_list):
        """With no list argument, the built-in Tasks list is resolved."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.side_effect = [
            [{**sample_task_list, "id": "default-123", "wellknownListName": "defaultList"}],
            [],
        ]
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        with patch("officeclaw.tasks.TasksClient._read_cache", return_value={}):
            result = runner.invoke(main, ["tasks", "list"])

        assert result.exit_code == 0
        assert "default-123" in mock_client.get_all.call_args[0][0]

    @patch("officeclaw.tasks.GraphClient")
    def test_unknown_list_name_is_reported(self, mock_client_class, sample_task_list):
        """An unresolvable --list-name fails with a usable message."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = [{**sample_task_list, "displayName": "Tasks"}]
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        with patch("officeclaw.tasks.TasksClient._read_cache", return_value={}):
            result = runner.invoke(main, ["tasks", "list", "--list-name", "Nope", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["status"] == "error"
        assert payload["error"]["code"] == "TaskListError"


class TestMailAttachmentCommands:
    """Test mail attachment-related CLI commands."""

    @patch("officeclaw.mail.GraphClient")
    def test_mail_attachments_success(self, mock_client_class, sample_attachments):
        """Test successful mail attachments listing."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_attachments
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(main, ["mail", "attachments", "msg-123"])

        assert result.exit_code == 0
        assert "meeting_notes.txt" in result.output
        assert "report.pdf" in result.output

    @patch("officeclaw.mail.GraphClient")
    def test_mail_attachments_json(self, mock_client_class, sample_attachments):
        """Test mail attachments outputs valid JSON."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_attachments
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(main, ["--json", "mail", "attachments", "msg-123"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert len(data["data"]) == 2

    def test_mail_attachments_requires_message_id(self):
        """Test mail attachments requires message-id argument."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mail", "attachments"])

        assert result.exit_code != 0

    def test_mail_download_disabled(self):
        """Test mail download blocked when capability disabled."""
        import os

        from officeclaw.cli import main

        os.environ.pop("OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD", None)

        runner = CliRunner()
        result = runner.invoke(main, ["mail", "download", "msg-123", "file.txt"])

        assert result.exit_code == 1
        assert "disabled" in result.output.lower()


class TestAuthCommands:
    """Test authentication-related CLI commands."""

    @patch("officeclaw.cli.TokenManager")
    def test_auth_status_not_authenticated(self, mock_token_manager):
        """Test auth status when not authenticated."""
        from officeclaw.cli import main

        mock_manager = MagicMock()
        mock_manager.get_token_info.return_value = None
        mock_token_manager.return_value = mock_manager

        runner = CliRunner()
        result = runner.invoke(main, ["auth", "status"])

        assert "not" in result.output.lower() or "authenticated" in result.output.lower()

    @patch("officeclaw.cli.TokenManager")
    def test_auth_logout(self, mock_token_manager):
        """Test auth logout clears tokens."""
        from officeclaw.cli import main

        mock_manager = MagicMock()
        mock_token_manager.return_value = mock_manager

        runner = CliRunner()
        result = runner.invoke(main, ["auth", "logout"])

        assert result.exit_code == 0
        mock_manager.clear_tokens.assert_called_once()


class TestJsonOutput:
    """Test JSON output mode."""

    @patch("officeclaw.cli.GraphClient")
    def test_json_flag_affects_output(self, mock_client_class, sample_messages):
        """Test that --json flag produces JSON output."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_messages
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(main, ["--json", "mail", "list"])

        # Should be valid JSON
        data = json.loads(result.output)
        assert "status" in data

    @patch("officeclaw.cli.GraphClient")
    def test_json_output_structure(self, mock_client_class, sample_task_list):
        """Test JSON output has correct structure."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = [sample_task_list]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(main, ["--json", "tasks", "list-lists"])

        data = json.loads(result.output)
        assert data["status"] == "success"
        assert "data" in data
        assert isinstance(data["data"], list)


class TestCapabilityGates:
    """Test that write operations are gated by env vars."""

    def setup_method(self):
        """Reset dotenv loaded flag before each test."""
        import officeclaw.cli

        officeclaw.cli._dotenv_loaded = True  # Prevent load_dotenv from loading .env

    def test_mail_send_blocked_by_default(self):
        """mail send should fail when OFFICECLAW_ENABLE_SEND is not set."""
        from officeclaw.cli import main

        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(
                main, ["mail", "send", "--to", "x@x.com", "--subject", "t", "--body", "b"]
            )
            assert result.exit_code != 0
            assert "OFFICECLAW_ENABLE_SEND" in result.output

    def test_mail_send_allowed_when_enabled(self):
        """mail send should proceed when OFFICECLAW_ENABLE_SEND=true."""
        from officeclaw.cli import main

        runner = CliRunner()
        with (
            patch.dict(
                "os.environ",
                {
                    "OFFICECLAW_ENABLE_SEND": "true",
                    "OFFICECLAW_ALLOWED_RECIPIENTS": "x@x.com",
                },
            ),
            patch("officeclaw.cli.GraphClient") as mock_gc,
        ):
            mock_client = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)
            result = runner.invoke(
                main, ["mail", "send", "--to", "x@x.com", "--subject", "t", "--body", "b"]
            )
            assert result.exit_code == 0

    def test_mail_delete_blocked_by_default(self):
        """mail delete should fail when OFFICECLAW_ENABLE_DELETE is not set."""
        from officeclaw.cli import main

        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(main, ["mail", "delete", "msg-123"])
            assert result.exit_code != 0
            assert "OFFICECLAW_ENABLE_DELETE" in result.output

    def test_mail_reply_blocked_by_default(self):
        """mail reply should fail when OFFICECLAW_ENABLE_SEND is not set."""
        from officeclaw.cli import main

        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(main, ["mail", "reply", "msg-123", "--body", "thanks"])
            assert result.exit_code != 0
            assert "OFFICECLAW_ENABLE_SEND" in result.output

    def test_mail_forward_blocked_by_default(self):
        """mail forward should fail when OFFICECLAW_ENABLE_SEND is not set."""
        from officeclaw.cli import main

        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(main, ["mail", "forward", "msg-123", "--to", "x@x.com"])
            assert result.exit_code != 0
            assert "OFFICECLAW_ENABLE_SEND" in result.output

    def test_calendar_delete_blocked_by_default(self):
        """calendar delete should fail when OFFICECLAW_ENABLE_DELETE is not set."""
        from officeclaw.cli import main

        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(main, ["calendar", "delete", "evt-123"])
            assert result.exit_code != 0
            assert "OFFICECLAW_ENABLE_DELETE" in result.output

    def test_tasks_delete_blocked_by_default(self):
        """tasks delete should fail when OFFICECLAW_ENABLE_DELETE is not set."""
        from officeclaw.cli import main

        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(main, ["tasks", "delete", "--list-id", "l1", "--task-id", "t1"])
            assert result.exit_code != 0
            assert "OFFICECLAW_ENABLE_DELETE" in result.output


class TestRecipientAllowlist:
    """mail send honours OFFICECLAW_ALLOWED_RECIPIENTS."""

    def setup_method(self):
        import officeclaw.cli

        officeclaw.cli._dotenv_loaded = True  # Prevent load_dotenv from loading .env

    @staticmethod
    def _run(to, tmp_path, env):
        from officeclaw import policy
        from officeclaw.cli import main

        runner = CliRunner()
        with (
            patch.dict("os.environ", env, clear=True),
            patch.object(policy, "LOG_DIR", tmp_path),
            patch.object(policy, "BLOCK_LOG", tmp_path / "email-blocked.log"),
            patch.object(policy, "ALERT_FILE", tmp_path / "email-alert.json"),
            patch("officeclaw.cli.GraphClient") as mock_gc,
        ):
            mock_client = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)
            result = runner.invoke(
                main, ["mail", "send", "--to", to, "--subject", "t", "--body", "b"]
            )
            return result, mock_client

    def test_send_to_unlisted_address_is_blocked(self, tmp_path):
        result, mock_client = self._run(
            "mallory@evil.com",
            tmp_path,
            {
                "OFFICECLAW_ENABLE_SEND": "true",
                "OFFICECLAW_ALLOWED_RECIPIENTS": "alice@example.com",
            },
        )

        assert result.exit_code == 1
        assert "Blocked" in result.output
        mock_client.post.assert_not_called()
        assert "mallory@evil.com" in (tmp_path / "email-blocked.log").read_text()

    def test_send_to_listed_address_proceeds(self, tmp_path):
        result, mock_client = self._run(
            "alice@example.com",
            tmp_path,
            {
                "OFFICECLAW_ENABLE_SEND": "true",
                "OFFICECLAW_ALLOWED_RECIPIENTS": "alice@example.com",
            },
        )

        assert result.exit_code == 0
        mock_client.post.assert_called_once()

    def test_warning_when_no_allowlist_configured(self, tmp_path):
        result, mock_client = self._run(
            "anyone@anywhere.com", tmp_path, {"OFFICECLAW_ENABLE_SEND": "true"}
        )

        assert result.exit_code == 0
        assert "No recipient allowlist configured" in result.output
        mock_client.post.assert_called_once()


class TestAttachmentAllowlist:
    """mail send honours OFFICECLAW_ALLOWED_ATTACHMENT_DIRS."""

    def setup_method(self):
        import officeclaw.cli

        officeclaw.cli._dotenv_loaded = True  # Prevent load_dotenv from loading .env

    @staticmethod
    def _run(attachment, tmp_path, env):
        from officeclaw import policy
        from officeclaw.cli import main

        runner = CliRunner()
        with (
            patch.dict("os.environ", env, clear=True),
            patch.object(policy, "LOG_DIR", tmp_path / "logs"),
            patch.object(policy, "BLOCK_LOG", tmp_path / "logs" / "email-blocked.log"),
            patch.object(policy, "ALERT_FILE", tmp_path / "logs" / "email-alert.json"),
            patch("officeclaw.cli.GraphClient") as mock_gc,
        ):
            mock_client = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)
            result = runner.invoke(
                main,
                [
                    "mail",
                    "send",
                    "--to",
                    "alice@example.com",
                    "--subject",
                    "t",
                    "--body",
                    "b",
                    "--attachment",
                    str(attachment),
                ],
            )
            return result, mock_client

    def test_attachment_outside_allowed_dir_is_blocked(self, tmp_path):
        wip = tmp_path / "wip"
        wip.mkdir()
        secret = tmp_path / "id_rsa"
        secret.write_text("PRIVATE KEY")

        result, mock_client = self._run(
            secret,
            tmp_path,
            {
                "OFFICECLAW_ENABLE_SEND": "true",
                "OFFICECLAW_ALLOWED_RECIPIENTS": "alice@example.com",
                "OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip),
            },
        )

        assert result.exit_code == 1
        assert "Blocked" in result.output
        mock_client.post.assert_not_called()

    def test_attachment_inside_allowed_dir_is_sent(self, tmp_path):
        wip = tmp_path / "wip"
        wip.mkdir()
        report = wip / "report.txt"
        report.write_text("quarterly numbers")

        result, mock_client = self._run(
            report,
            tmp_path,
            {
                "OFFICECLAW_ENABLE_SEND": "true",
                "OFFICECLAW_ALLOWED_RECIPIENTS": "alice@example.com",
                "OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip),
            },
        )

        assert result.exit_code == 0
        payload = mock_client.post.call_args[0][1]
        assert payload["message"]["attachments"][0]["name"] == "report.txt"

    def test_warning_when_no_attachment_allowlist(self, tmp_path):
        report = tmp_path / "report.txt"
        report.write_text("quarterly numbers")

        result, _ = self._run(
            report,
            tmp_path,
            {
                "OFFICECLAW_ENABLE_SEND": "true",
                "OFFICECLAW_ALLOWED_RECIPIENTS": "alice@example.com",
            },
        )

        assert result.exit_code == 0
        assert "No attachment directory allowlist configured" in result.output


class TestJSONContract:
    """--json works in both positions, and covers failures as well as success."""

    def setup_method(self):
        import officeclaw.cli

        officeclaw.cli._dotenv_loaded = True

    @patch("officeclaw.tasks.GraphClient")
    def test_flag_after_the_subcommand(self, mock_client_class, sample_task):
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = [sample_task]
        mock_client_class.return_value = mock_client

        result = CliRunner().invoke(main, ["tasks", "list", "--list-id", "l1", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.output)["status"] == "success"

    @patch("officeclaw.tasks.GraphClient")
    def test_flag_before_the_subcommand_still_works(self, mock_client_class, sample_task):
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.get_all.return_value = [sample_task]
        mock_client_class.return_value = mock_client

        result = CliRunner().invoke(main, ["--json", "tasks", "list", "--list-id", "l1"])

        assert result.exit_code == 0
        assert json.loads(result.output)["status"] == "success"

    @patch("officeclaw.tasks.GraphClient")
    def test_errors_are_json_in_json_mode(self, mock_client_class):
        from officeclaw.cli import main
        from officeclaw.exceptions import GraphAPIError

        mock_client = MagicMock()
        mock_client.get_all.side_effect = GraphAPIError("ResourceNotFound", "Not found", 404)
        mock_client_class.return_value = mock_client

        result = CliRunner().invoke(main, ["tasks", "list", "--list-id", "l1", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["status"] == "error"
        assert payload["error"]["code"] == "ResourceNotFound"

    def test_capability_refusal_is_json(self):
        from officeclaw.cli import main

        with patch.dict("os.environ", {}, clear=True):
            result = CliRunner().invoke(main, ["mail", "delete", "msg-1", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["error"]["code"] == "CapabilityDisabled"
        assert "OFFICECLAW_ENABLE_DELETE" in payload["error"]["message"]

    def test_human_output_is_unchanged_without_the_flag(self):
        from officeclaw.cli import main

        with patch.dict("os.environ", {}, clear=True):
            result = CliRunner().invoke(main, ["mail", "delete", "msg-1"])

        assert result.exit_code == 1
        assert "OFFICECLAW_ENABLE_DELETE" in result.output
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.output)


class TestTaskCreateFlags:
    """tasks create exposes the metadata the library already supported."""

    @patch("officeclaw.tasks.GraphClient")
    def test_full_metadata_in_one_command(self, mock_client_class, sample_task):
        from officeclaw.cli import main

        mock_client = MagicMock()
        mock_client.post.return_value = sample_task
        mock_client_class.return_value = mock_client

        result = CliRunner().invoke(
            main,
            [
                "tasks",
                "create",
                "--list-id",
                "l1",
                "--title",
                "Call accountant",
                "--body",
                "About GST registration",
                "--due-date",
                "2026-09-15",
                "--importance",
                "high",
                "--reminder",
                "2026-09-15T08:00:00",
                "--category",
                "finance,admin",
            ],
        )

        assert result.exit_code == 0
        payload = mock_client.post.call_args[0][1]
        assert payload["title"] == "Call accountant"
        assert payload["body"]["content"] == "About GST registration"
        assert payload["importance"] == "high"
        assert payload["isReminderOn"] is True
        assert payload["categories"] == ["finance", "admin"]


class TestAuthRefreshCommand:
    @patch("officeclaw.cli.TokenManager")
    def test_refresh_reports_json(self, mock_manager):
        from officeclaw.cli import main

        mock_manager.return_value.refresh.return_value = {"time_until_expiry_seconds": 3600}

        result = CliRunner().invoke(main, ["auth", "refresh", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["time_until_expiry_seconds"] == 3600

    @patch("officeclaw.cli.TokenManager")
    def test_refresh_exits_nonzero_when_login_needed(self, mock_manager):
        from officeclaw.cli import main
        from officeclaw.exceptions import AuthenticationError

        mock_manager.return_value.refresh.side_effect = AuthenticationError("login required")

        result = CliRunner().invoke(main, ["auth", "refresh", "--json"])

        assert result.exit_code == 1
        assert json.loads(result.output)["error"]["code"] == "AuthenticationError"
