"""
Tests for the Outclaw mail module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMailClient:
    """Test MailClient operations."""

    @patch("officeclaw.mail.GraphClient")
    def test_list_messages(self, mock_client_class, sample_messages):
        """Test listing messages."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_messages
        mock_client_class.return_value = mock_client

        client = MailClient()
        messages = client.list_messages(limit=10)

        assert len(messages) == 3
        mock_client.get_all.assert_called_once()
        call_args = mock_client.get_all.call_args
        assert "/me/mailFolders/inbox/messages" in call_args[0][0]

    @patch("officeclaw.mail.GraphClient")
    def test_list_messages_with_filter(self, mock_client_class, sample_messages):
        """Test listing messages with filter."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = [sample_messages[0]]
        mock_client_class.return_value = mock_client

        client = MailClient()
        messages = client.list_messages(filter_query="isRead eq false")

        assert len(messages) == 1
        call_args = mock_client.get_all.call_args
        assert "$filter" in call_args[1]["params"]

    @patch("officeclaw.mail.GraphClient")
    def test_get_message(self, mock_client_class, sample_message):
        """Test getting a specific message."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        mock_client.get.return_value = sample_message
        mock_client_class.return_value = mock_client

        client = MailClient()
        message = client.get_message("msg-123")

        assert message["subject"] == sample_message["subject"]
        mock_client.get.assert_called_with("/me/messages/msg-123")

    @patch("officeclaw.mail.GraphClient")
    def test_send_message(self, mock_client_class):
        """Test sending a message."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        mock_client.post.return_value = None
        mock_client_class.return_value = mock_client

        client = MailClient()
        client.send_message(
            to="recipient@example.com",
            subject="Test Subject",
            body="Test body",
        )

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/me/sendMail"
        assert "message" in call_args[0][1]

    @patch("officeclaw.mail.GraphClient")
    def test_send_message_multiple_recipients(self, mock_client_class):
        """Test sending to multiple recipients."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        mock_client.post.return_value = None
        mock_client_class.return_value = mock_client

        client = MailClient()
        client.send_message(
            to=["user1@example.com", "user2@example.com"],
            subject="Test",
            body="Body",
            cc="cc@example.com",
        )

        call_args = mock_client.post.call_args
        message = call_args[0][1]["message"]
        assert len(message["toRecipients"]) == 2
        assert len(message["ccRecipients"]) == 1

    @patch("officeclaw.mail.GraphClient")
    def test_mark_read(self, mock_client_class, sample_message):
        """Test marking message as read."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        updated = {**sample_message, "isRead": True}
        mock_client.patch.return_value = updated
        mock_client_class.return_value = mock_client

        client = MailClient()
        result = client.mark_read("msg-123", is_read=True)

        assert result["isRead"] is True
        mock_client.patch.assert_called_with(
            "/me/messages/msg-123",
            {"isRead": True},
        )

    @patch("officeclaw.mail.GraphClient")
    def test_delete_message(self, mock_client_class):
        """Test deleting a message."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        mock_client.delete.return_value = None
        mock_client_class.return_value = mock_client

        client = MailClient()
        client.delete("msg-123")

        mock_client.delete.assert_called_with("/me/messages/msg-123")

    @patch("officeclaw.mail.GraphClient")
    def test_reply(self, mock_client_class):
        """Test replying to a message."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        mock_client.post.return_value = None
        mock_client_class.return_value = mock_client

        client = MailClient()
        client.reply("msg-123", "Thanks for your email!")

        mock_client.post.assert_called_with(
            "/me/messages/msg-123/reply",
            {"comment": "Thanks for your email!"},
        )

    @patch("officeclaw.mail.GraphClient")
    def test_archive(self, mock_client_class, sample_message):
        """Test archiving a message."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        mock_client.post.return_value = sample_message
        mock_client_class.return_value = mock_client

        client = MailClient()
        client.archive("msg-123")

        mock_client.post.assert_called_with(
            "/me/messages/msg-123/move",
            {"destinationId": "archive"},
        )

    @patch("officeclaw.mail.GraphClient")
    def test_list_attachments(self, mock_client_class, sample_attachments):
        """Test listing attachments for a message."""
        from officeclaw.mail import MailClient

        mock_client = MagicMock()
        mock_client.get_all.return_value = sample_attachments
        mock_client_class.return_value = mock_client

        client = MailClient()
        attachments = client.list_attachments("msg-123")

        assert len(attachments) == 2
        mock_client.get_all.assert_called_with("/me/messages/msg-123/attachments")

    @patch("officeclaw.mail.GraphClient")
    def test_download_attachment_success(self, mock_client_class, sample_attachments):
        """Test successful attachment download."""
        import os
        import tempfile

        from officeclaw.mail import MailClient

        os.environ["OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD"] = "true"
        os.environ["OFFICECLAW_SAFE_SENDERS_ONLY"] = "true"
        os.environ["OFFICECLAW_SAFE_SENDERS_LIST"] = "sender@example.com"

        mock_client = MagicMock()

        def _mock_get(endpoint):
            if "attachments/AAMkAGUz" in endpoint:
                return sample_attachments[0]
            return {"from": {"emailAddress": {"address": "sender@example.com"}}}

        mock_client.get.side_effect = _mock_get
        mock_client.get_all.return_value = sample_attachments
        mock_client_class.return_value = mock_client

        client = MailClient()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = client.download_attachment(
                "msg-123", "AAMkAGUz...", output_path=f"{tmpdir}/meeting_notes.txt"
            )
            assert os.path.exists(path)
            with open(path, "rb") as f:
                content = f.read()
            assert content == b"Hello, this is test content."

        del os.environ["OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD"]
        del os.environ["OFFICECLAW_SAFE_SENDERS_ONLY"]
        del os.environ["OFFICECLAW_SAFE_SENDERS_LIST"]

    @patch("officeclaw.mail.GraphClient")
    def test_download_attachment_blocked_sender(self, mock_client_class, sample_attachments):
        """Test attachment download blocked by sender."""
        import os

        from officeclaw.exceptions import AttachmentSecurityError
        from officeclaw.mail import MailClient

        os.environ["OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD"] = "true"
        os.environ["OFFICECLAW_SAFE_SENDERS_ONLY"] = "true"
        os.environ["OFFICECLAW_SAFE_SENDERS_LIST"] = "safe@example.com"

        mock_client = MagicMock()
        mock_client.get.return_value = {
            "from": {"emailAddress": {"address": "bad@example.com"}},
        }
        mock_client_class.return_value = mock_client

        client = MailClient()
        with pytest.raises(AttachmentSecurityError):
            client.download_attachment("msg-123", "AAMkAGUz...")

        del os.environ["OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD"]
        del os.environ["OFFICECLAW_SAFE_SENDERS_ONLY"]
        del os.environ["OFFICECLAW_SAFE_SENDERS_LIST"]

    @patch("officeclaw.mail.GraphClient")
    def test_download_attachment_disabled(self, mock_client_class):
        """Test attachment download blocked when gate is disabled."""
        import os

        from officeclaw.exceptions import AttachmentSecurityError
        from officeclaw.mail import MailClient

        # Ensure gate is disabled
        os.environ.pop("OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD", None)

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        client = MailClient()
        with pytest.raises(AttachmentSecurityError):
            client.download_attachment("msg-123", "AAMkAGUz...")

    @patch("officeclaw.mail.GraphClient")
    def test_download_attachment_size_exceeded(self, mock_client_class, sample_attachments):
        """Test attachment download blocked by size limit."""
        import os

        from officeclaw.exceptions import AttachmentSizeError
        from officeclaw.mail import MailClient

        os.environ["OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD"] = "true"
        os.environ["OFFICECLAW_ATTACHMENT_MAX_SIZE_MB"] = "5"

        mock_client = MagicMock()

        def _mock_get(endpoint):
            if "attachments/AAMkAGUy" in endpoint:
                return sample_attachments[1]
            return {"from": {"emailAddress": {"address": "sender@example.com"}}}

        mock_client.get.side_effect = _mock_get
        mock_client.get_all.return_value = sample_attachments
        mock_client_class.return_value = mock_client

        client = MailClient()
        # report.pdf is 10MB which exceeds 5MB limit
        with pytest.raises(AttachmentSizeError):
            client.download_attachment("msg-123", "AAMkAGUy...")

        del os.environ["OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD"]
        del os.environ["OFFICECLAW_ATTACHMENT_MAX_SIZE_MB"]

    @patch("officeclaw.mail.GraphClient")
    def test_download_attachment_type_not_allowed(self, mock_client_class, sample_attachments):
        """Test attachment download blocked by MIME type."""
        import os

        from officeclaw.exceptions import AttachmentTypeError
        from officeclaw.mail import MailClient

        os.environ["OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD"] = "true"
        os.environ["OFFICECLAW_ATTACHMENT_ALLOWED_TYPES"] = "text/plain"

        mock_client = MagicMock()

        def _mock_get(endpoint):
            if "attachments/AAMkAGUy" in endpoint:
                return sample_attachments[1]
            return {"from": {"emailAddress": {"address": "sender@example.com"}}}

        mock_client.get.side_effect = _mock_get
        mock_client.get_all.return_value = sample_attachments
        mock_client_class.return_value = mock_client

        client = MailClient()
        # report.pdf is application/pdf which is not text/plain
        with pytest.raises(AttachmentTypeError):
            client.download_attachment("msg-123", "AAMkAGUy...")

        del os.environ["OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD"]
        del os.environ["OFFICECLAW_ATTACHMENT_ALLOWED_TYPES"]
