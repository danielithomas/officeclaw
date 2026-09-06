"""
Tests for outbound recipient allowlist enforcement.

Covers the policy helpers and every send path that has to honour them:
send (including cc/bcc), forward, reply and reply-all.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from officeclaw import policy
from officeclaw.exceptions import AttachmentNotAllowedError, RecipientNotAllowedError

ALLOWLIST = {"OFFICECLAW_ALLOWED_RECIPIENTS": "alice@example.com, Bob@Example.com"}


@pytest.fixture(autouse=True)
def _no_block_logging(tmp_path):
    """Keep blocked-attempt logs out of the developer's home directory."""
    with (
        patch.object(policy, "LOG_DIR", tmp_path),
        patch.object(policy, "BLOCK_LOG", tmp_path / "email-blocked.log"),
        patch.object(policy, "ALERT_FILE", tmp_path / "email-alert.json"),
    ):
        yield


@pytest.fixture
def mail_client():
    """MailClient backed by a mock GraphClient."""
    with patch("officeclaw.mail.GraphClient") as mock_class:
        from officeclaw.mail import MailClient

        graph = MagicMock()
        graph.token_manager.get_account_username.return_value = "me@example.com"
        mock_class.return_value = graph
        yield MailClient(), graph


class TestAllowlistParsing:
    def test_unset_allowlist_permits_everything(self):
        with patch.dict("os.environ", {"OFFICECLAW_ALLOWED_RECIPIENTS": ""}):
            assert policy.get_allowed_recipients() is None
            policy.check_recipients(["anyone@anywhere.com"], action="send")

    def test_entries_are_normalized(self):
        with patch.dict("os.environ", ALLOWLIST):
            assert policy.get_allowed_recipients() == {"alice@example.com", "bob@example.com"}

    def test_display_name_form_is_matched_on_the_address(self):
        with patch.dict("os.environ", ALLOWLIST):
            policy.check_recipients(["Alice <ALICE@example.com>"], action="send")

    def test_unparseable_address_is_blocked(self):
        with patch.dict("os.environ", ALLOWLIST), pytest.raises(RecipientNotAllowedError):
            policy.check_recipients(["not an address"], action="send")

    def test_blocked_attempt_is_logged(self, tmp_path):
        with patch.dict("os.environ", ALLOWLIST), pytest.raises(RecipientNotAllowedError):
            policy.check_recipients(["mallory@evil.com"], action="send", subject="hi")

        logged = (tmp_path / "email-blocked.log").read_text()
        assert "BLOCKED" in logged
        assert "mallory@evil.com" in logged
        assert (tmp_path / "email-alert.json").exists()


class TestSendEnforcement:
    def test_send_to_allowed_recipient(self, mail_client):
        client, graph = mail_client
        with patch.dict("os.environ", ALLOWLIST):
            client.send_message("alice@example.com", "Subject", "Body")
        graph.post.assert_called_once()

    def test_send_to_blocked_recipient(self, mail_client):
        client, graph = mail_client
        with patch.dict("os.environ", ALLOWLIST), pytest.raises(RecipientNotAllowedError):
            client.send_message("mallory@evil.com", "Subject", "Body")
        graph.post.assert_not_called()

    def test_blocked_cc_stops_the_send(self, mail_client):
        client, graph = mail_client
        with patch.dict("os.environ", ALLOWLIST), pytest.raises(RecipientNotAllowedError):
            client.send_message("alice@example.com", "S", "B", cc="mallory@evil.com")
        graph.post.assert_not_called()

    def test_blocked_bcc_stops_the_send(self, mail_client):
        client, graph = mail_client
        with patch.dict("os.environ", ALLOWLIST), pytest.raises(RecipientNotAllowedError):
            client.send_message("alice@example.com", "S", "B", bcc="mallory@evil.com")
        graph.post.assert_not_called()


class TestForwardEnforcement:
    def test_forward_to_blocked_recipient(self, mail_client):
        client, graph = mail_client
        with patch.dict("os.environ", ALLOWLIST), pytest.raises(RecipientNotAllowedError):
            client.forward("msg-123", "mallory@evil.com")
        graph.post.assert_not_called()

    def test_forward_to_allowed_recipient(self, mail_client):
        client, graph = mail_client
        with patch.dict("os.environ", ALLOWLIST):
            client.forward("msg-123", "bob@example.com")
        graph.post.assert_called_once()


class TestReplyEnforcement:
    def test_reply_to_outside_sender_is_blocked(self, mail_client):
        client, graph = mail_client
        graph.get.return_value = {
            "from": {"emailAddress": {"address": "mallory@evil.com"}},
            "toRecipients": [{"emailAddress": {"address": "me@example.com"}}],
        }
        with patch.dict("os.environ", ALLOWLIST), pytest.raises(RecipientNotAllowedError):
            client.reply("msg-123", "sure thing")
        graph.post.assert_not_called()

    def test_reply_honours_reply_to_header(self, mail_client):
        client, graph = mail_client
        graph.get.return_value = {
            "from": {"emailAddress": {"address": "alice@example.com"}},
            "replyTo": [{"emailAddress": {"address": "mallory@evil.com"}}],
        }
        with patch.dict("os.environ", ALLOWLIST), pytest.raises(RecipientNotAllowedError):
            client.reply("msg-123", "sure thing")
        graph.post.assert_not_called()

    def test_reply_to_allowed_sender(self, mail_client):
        client, graph = mail_client
        graph.get.return_value = {"from": {"emailAddress": {"address": "alice@example.com"}}}
        with patch.dict("os.environ", ALLOWLIST):
            client.reply("msg-123", "thanks")
        graph.post.assert_called_once_with("/me/messages/msg-123/reply", {"comment": "thanks"})

    def test_reply_all_blocked_by_a_single_outside_cc(self, mail_client):
        client, graph = mail_client
        graph.get.return_value = {
            "from": {"emailAddress": {"address": "alice@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "me@example.com"}}],
            "ccRecipients": [{"emailAddress": {"address": "mallory@evil.com"}}],
        }
        with patch.dict("os.environ", ALLOWLIST), pytest.raises(RecipientNotAllowedError):
            client.reply("msg-123", "thanks", reply_all=True)
        graph.post.assert_not_called()

    def test_reply_all_ignores_the_mailbox_owner(self, mail_client):
        client, graph = mail_client
        graph.get.return_value = {
            "from": {"emailAddress": {"address": "alice@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "ME@example.com"}}],
        }
        with patch.dict("os.environ", ALLOWLIST):
            client.reply("msg-123", "thanks", reply_all=True)
        graph.post.assert_called_once()

    def test_no_lookup_when_no_allowlist_configured(self, mail_client):
        client, graph = mail_client
        with patch.dict("os.environ", {"OFFICECLAW_ALLOWED_RECIPIENTS": ""}):
            client.reply("msg-123", "thanks")
        graph.get.assert_not_called()
        graph.post.assert_called_once()


class TestAttachmentDirectories:
    """OFFICECLAW_ALLOWED_ATTACHMENT_DIRS restricts what can be attached."""

    def test_unset_permits_any_file(self, tmp_path):
        target = tmp_path / "notes.txt"
        target.write_text("hello")
        with patch.dict("os.environ", {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": ""}):
            assert policy.get_allowed_attachment_dirs() is None
            assert policy.check_attachment_path(target) == target.resolve()

    def test_file_inside_allowed_dir(self, tmp_path):
        wip = tmp_path / "wip"
        wip.mkdir()
        target = wip / "report.pdf"
        target.write_text("pdf")
        with patch.dict("os.environ", {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip)}):
            assert policy.check_attachment_path(target) == target.resolve()

    def test_file_in_nested_subdirectory_is_allowed(self, tmp_path):
        wip = tmp_path / "wip"
        (wip / "sub").mkdir(parents=True)
        target = wip / "sub" / "report.pdf"
        target.write_text("pdf")
        with patch.dict("os.environ", {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip)}):
            assert policy.check_attachment_path(target) == target.resolve()

    def test_file_outside_allowed_dir_is_blocked(self, tmp_path):
        wip = tmp_path / "wip"
        wip.mkdir()
        secret = tmp_path / "id_rsa"
        secret.write_text("PRIVATE KEY")
        with (
            patch.dict("os.environ", {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip)}),
            pytest.raises(AttachmentNotAllowedError),
        ):
            policy.check_attachment_path(secret)

    def test_traversal_out_of_allowed_dir_is_blocked(self, tmp_path):
        wip = tmp_path / "wip"
        wip.mkdir()
        secret = tmp_path / "id_rsa"
        secret.write_text("PRIVATE KEY")
        with (
            patch.dict("os.environ", {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip)}),
            pytest.raises(AttachmentNotAllowedError),
        ):
            policy.check_attachment_path(wip / ".." / "id_rsa")

    def test_symlink_escaping_allowed_dir_is_blocked(self, tmp_path):
        wip = tmp_path / "wip"
        wip.mkdir()
        secret = tmp_path / "id_rsa"
        secret.write_text("PRIVATE KEY")
        link = wip / "innocent.txt"
        link.symlink_to(secret)
        with (
            patch.dict("os.environ", {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip)}),
            pytest.raises(AttachmentNotAllowedError),
        ):
            policy.check_attachment_path(link)

    def test_multiple_directories_are_honoured(self, tmp_path):
        first, second = tmp_path / "a", tmp_path / "b"
        first.mkdir()
        second.mkdir()
        target = second / "file.txt"
        target.write_text("x")
        env = {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": f"{first}, {second}"}
        with patch.dict("os.environ", env):
            assert policy.check_attachment_path(target) == target.resolve()

    def test_blocked_attachment_is_logged(self, tmp_path):
        wip = tmp_path / "wip"
        wip.mkdir()
        secret = tmp_path / "id_rsa"
        secret.write_text("PRIVATE KEY")
        with (
            patch.dict("os.environ", {"OFFICECLAW_ALLOWED_ATTACHMENT_DIRS": str(wip)}),
            pytest.raises(AttachmentNotAllowedError),
        ):
            policy.check_attachment_path(secret)

        assert "action=attachment" in (tmp_path / "email-blocked.log").read_text()
