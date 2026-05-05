"""
Mail operations for Outclaw.

Provides email management through Microsoft Graph API.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any

from officeclaw.client import GraphClient
from officeclaw.exceptions import (
    AttachmentSecurityError,
    AttachmentSizeError,
    AttachmentTypeError,
)

class MailClient:
    """
    Client for Microsoft Graph Mail API.

    Example:
        client = MailClient()
        messages = client.list_messages(limit=10)
        client.send_message("user@example.com", "Subject", "Body")
    """

    def __init__(self, graph_client: GraphClient | None = None) -> None:
        """Initialize mail client."""
        self._client = graph_client or GraphClient()
        self._owns_client = graph_client is None

    def list_messages(
        self,
        folder: str = "inbox",
        limit: int = 10,
        filter_query: str | None = None,
        search: str | None = None,
        order_by: str = "receivedDateTime desc",
        select: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List email messages.

        Args:
            folder: Mail folder (inbox, sentItems, drafts, etc.)
            limit: Maximum messages to return
            filter_query: OData filter expression
            search: Search query
            order_by: Sort order
            select: Fields to return

        Returns:
            List of message objects
        """
        params: dict[str, Any] = {
            "$top": limit,
            "$orderby": order_by,
        }

        if select:
            params["$select"] = select
        else:
            params["$select"] = (
                "id,subject,from,toRecipients,receivedDateTime,isRead,importance,hasAttachments,bodyPreview"
            )

        if filter_query:
            params["$filter"] = filter_query

        if search:
            params["$search"] = f'"{search}"'

        endpoint = f"/me/mailFolders/{folder}/messages"
        return self._client.get_all(endpoint, params=params, limit=limit)

    def get_message(self, message_id: str) -> dict[str, Any]:
        """
        Get a specific message.

        Args:
            message_id: Message ID

        Returns:
            Message object with full details
        """
        return self._client.get(f"/me/messages/{message_id}")

    def send_message(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        content_type: str = "Text",
        save_to_sent: bool = True,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Send an email message.

        Args:
            to: Recipient email(s)
            subject: Email subject
            body: Email body
            cc: CC recipient(s)
            bcc: BCC recipient(s)
            content_type: "Text" or "HTML"
            save_to_sent: Save copy to Sent Items
            attachments: List of attachment dicts with @odata.type, name,
                contentType, and contentBytes (base64-encoded)
        """
        # Normalize recipients to lists
        to_list = [to] if isinstance(to, str) else to
        cc_list = [cc] if isinstance(cc, str) else (cc or [])
        bcc_list = [bcc] if isinstance(bcc, str) else (bcc or [])

        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": content_type,
                    "content": body,
                },
                "toRecipients": [{"emailAddress": {"address": addr}} for addr in to_list],
            },
            "saveToSentItems": save_to_sent,
        }

        if cc_list:
            message["message"]["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc_list
            ]

        if bcc_list:
            message["message"]["bccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in bcc_list
            ]

        if attachments:
            message["message"]["attachments"] = attachments

        self._client.post("/me/sendMail", message)

    def reply(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
    ) -> None:
        """
        Reply to a message.

        Args:
            message_id: Original message ID
            body: Reply body
            reply_all: Reply to all recipients
        """
        endpoint = f"/me/messages/{message_id}/{'replyAll' if reply_all else 'reply'}"
        self._client.post(endpoint, {"comment": body})

    def forward(
        self,
        message_id: str,
        to: str | list[str],
        comment: str = "",
    ) -> None:
        """
        Forward a message.

        Args:
            message_id: Message ID to forward
            to: Recipient email(s)
            comment: Optional comment
        """
        to_list = [to] if isinstance(to, str) else to
        data = {
            "comment": comment,
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in to_list],
        }
        self._client.post(f"/me/messages/{message_id}/forward", data)

    def move(self, message_id: str, folder: str) -> dict[str, Any]:
        """
        Move message to a folder.

        Args:
            message_id: Message ID
            folder: Destination folder name or ID

        Returns:
            Updated message object
        """
        # Get folder ID if name provided
        folder_id = self._get_folder_id(folder)
        return self._client.post(
            f"/me/messages/{message_id}/move",
            {"destinationId": folder_id},
        )

    def delete(self, message_id: str) -> None:
        """Delete a message."""
        self._client.delete(f"/me/messages/{message_id}")

    def mark_read(self, message_id: str, is_read: bool = True) -> dict[str, Any]:
        """
        Mark message as read or unread.

        Args:
            message_id: Message ID
            is_read: True for read, False for unread

        Returns:
            Updated message object
        """
        return self._client.patch(
            f"/me/messages/{message_id}",
            {"isRead": is_read},
        )

    def archive(self, message_id: str) -> dict[str, Any]:
        """
        Move message to Archive folder.

        Args:
            message_id: Message ID

        Returns:
            Updated message object
        """
        return self.move(message_id, "archive")

    def list_attachments(self, message_id: str) -> list[dict[str, Any]]:
        """
        List all attachments for a message.

        Args:
            message_id: Message ID

        Returns:
            List of attachment metadata (id, name, contentType, size, isInline)
        """
        return self._client.get_all(f"/me/messages/{message_id}/attachments")

    def download_attachment(
        self,
        message_id: str,
        attachment_id: str,
        output_path: str | None = None,
    ) -> str:
        """
        Download an attachment to local storage with security validation.

        Args:
            message_id: Message ID
            attachment_id: Attachment ID from list_attachments
            output_path: Destination path (default: auto-generated)

        Returns:
            Path to downloaded file

        Raises:
            AttachmentSecurityError: If sender not in safe senders list
            AttachmentSizeError: If file exceeds configured max size
            AttachmentTypeError: If MIME type not in allowed types
        """
        # 1. Check master capability gate
        if os.environ.get("OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD", "").lower() not in (
            "true",
            "1",
            "yes",
        ):
            raise AttachmentSecurityError(
                "Attachment download is disabled. To enable, set OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD=true in your .env file."
            )

        # 2. Fetch message metadata to check sender
        message = self._client.get(f"/me/messages/{message_id}")
        sender_email = (
            message.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        )

        # 3. Validate safe senders if enabled
        safe_senders_only = (
            os.environ.get("OFFICECLAW_SAFE_SENDERS_ONLY", "").lower() in ("true", "1", "yes")
        )
        if safe_senders_only:
            safe_list_env = os.environ.get("OFFICECLAW_SAFE_SENDERS_LIST", "")
            safe_list = [s.strip() for s in safe_list_env.split(",") if s.strip()]
            if not self._is_safe_sender(sender_email, safe_list):
                raise AttachmentSecurityError(
                    f'Sender "{sender_email}" is not in the safe senders list. '
                    f"To allow, add to OFFICECLAW_SAFE_SENDERS_LIST in your .env file."
                )

        # 4. Fetch attachment metadata to check size/type
        attachment_meta = self._client.get(
            f"/me/messages/{message_id}/attachments/{attachment_id}"
        )
        attachment_size = attachment_meta.get("size", 0)
        content_type = attachment_meta.get("contentType", "application/octet-stream")
        attachment_name = attachment_meta.get("name", "unnamed")

        # 5. Validate max size
        max_size_mb = int(os.environ.get("OFFICECLAW_ATTACHMENT_MAX_SIZE_MB", "25"))
        max_size_bytes = max_size_mb * 1024 * 1024
        if attachment_size > max_size_bytes:
            raise AttachmentSizeError(attachment_size, max_size_mb)

        # 6. Validate MIME type
        allowed_types_env = os.environ.get("OFFICECLAW_ATTACHMENT_ALLOWED_TYPES", "")
        if allowed_types_env and allowed_types_env.strip() != "*":
            allowed_types = [t.strip() for t in allowed_types_env.split(",") if t.strip()]
            if not self._is_allowed_mime_type(content_type, allowed_types):
                raise AttachmentTypeError(content_type, allowed_types)

        # 7. Determine output path
        if output_path:
            save_path = Path(output_path)
        else:
            download_dir_env = os.environ.get(
                "OFFICECLAW_ATTACHMENT_DOWNLOAD_PATH", "./downloads"
            )
            download_dir = Path(download_dir_env).expanduser()
            download_dir.mkdir(parents=True, exist_ok=True)
            save_path = download_dir / self._sanitize_filename(attachment_name)

        # Handle filename collisions
        save_path = self._resolve_collision(save_path)

        # 8. Extract and save content
        # File attachments contain base64 contentBytes
        if attachment_meta.get("@odata.type") == "#microsoft.graph.fileAttachment":
            content_bytes_b64 = attachment_meta.get("contentBytes", "")
            if content_bytes_b64:
                content_bytes = base64.b64decode(content_bytes_b64)
                save_path.write_bytes(content_bytes)
            else:
                save_path.write_bytes(b"")
        else:
            # itemAttachment or referenceAttachment — write metadata instead
            import json

            save_path = save_path.with_suffix(".json")
            save_path = self._resolve_collision(save_path)
            save_path.write_text(json.dumps(attachment_meta, indent=2, default=str))

        return str(save_path)

    def _is_safe_sender(self, from_address: str, safe_list: list[str]) -> bool:
        """Check if sender is in the safe senders list."""
        for pattern in safe_list:
            pattern = pattern.lower()
            if pattern.startswith("@"):
                if from_address.endswith(pattern):
                    return True
            elif from_address == pattern:
                return True
        return False

    def _is_allowed_mime_type(self, content_type: str, allowed_types: list[str]) -> bool:
        """Check if MIME type matches allowed patterns (supports wildcards like image/*)."""
        for allowed in allowed_types:
            allowed = allowed.lower()
            if allowed.endswith("/*"):
                prefix = allowed.rstrip("/*")
                if content_type.lower().startswith(prefix + "/"):
                    return True
            elif content_type.lower() == allowed:
                return True
        return False

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitise filename to prevent path traversal."""
        # Remove path traversal components
        filename = os.path.basename(filename)
        # Remove potentially dangerous characters while preserving common filename chars
        filename = re.sub(r'[^\w\s\.\-\(\)\[\]_]', "_", filename)
        # Prevent empty names
        if not filename or filename in (".", ".."):
            filename = "unnamed"
        return filename

    def _resolve_collision(self, save_path: Path) -> Path:
        """Handle filename collisions by appending (1), (2), etc."""
        if not save_path.exists():
            return save_path
        stem = save_path.stem
        suffix = save_path.suffix
        parent = save_path.parent
        counter = 1
        while True:
            new_path = parent / f"{stem}({counter}){suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

    def search(
        self,
        query: str,
        folder: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """
        Search for messages.

        Args:
            query: Search query string
            folder: Specific folder to search (None = all folders)
            limit: Maximum results

        Returns:
            List of matching messages
        """
        params: dict[str, Any] = {
            "$search": f'"{query}"',
            "$top": limit,
            "$select": (
                "id,subject,from,toRecipients,receivedDateTime,isRead,importance,bodyPreview"
            ),
        }

        if folder:
            folder_id = self._get_folder_id(folder)
            endpoint = f"/me/mailFolders/{folder_id}/messages"
        else:
            endpoint = "/me/messages"

        return self._client.get_all(endpoint, params=params, limit=limit)

    def _get_folder_id(self, folder: str) -> str:
        """Get folder ID from name or return as-is if already an ID."""
        # Well-known folder names
        well_known = {
            "inbox": "inbox",
            "drafts": "drafts",
            "sentitems": "sentItems",
            "sent": "sentItems",
            "deleteditems": "deletedItems",
            "deleted": "deletedItems",
            "trash": "deletedItems",
            "archive": "archive",
            "junkemail": "junkemail",
            "junk": "junkemail",
            "spam": "junkemail",
        }

        folder_lower = folder.lower()
        if folder_lower in well_known:
            return well_known[folder_lower]

        # Assume it's already an ID
        return folder

    def list_folders(self) -> list[dict[str, Any]]:
        """List all mail folders."""
        return self._client.get_all("/me/mailFolders")

    def close(self) -> None:
        """Close the client."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> MailClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
