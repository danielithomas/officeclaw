"""
Tests for the Outclaw CLI.

Tests command parsing, output formatting, and error handling.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

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

    @patch("officeclaw.cli.GraphClient")
    def test_tasks_complete(self, mock_client_class, sample_task):
        """Test completing a task."""
        from officeclaw.cli import main

        mock_client = MagicMock()
        completed_task = {**sample_task, "status": "completed"}
        mock_client.patch.return_value = completed_task
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(
            main, ["tasks", "complete", "--list-id", "list-123", "--task-id", "task-123"]
        )

        assert result.exit_code == 0

    def test_tasks_list_requires_list_id(self):
        """Test tasks list requires list-id."""
        from officeclaw.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["tasks", "list"])

        assert result.exit_code != 0


class TestMailAttachmentCommands:
    """Test mail attachment-related CLI commands."""

    @patch("officeclaw.cli.GraphClient")
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

    @patch("officeclaw.cli.GraphClient")
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
