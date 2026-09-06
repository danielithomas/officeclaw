"""
Mail operations for Outclaw.

Provides email management through Microsoft Graph API.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from officeclaw import policy
from officeclaw.client import GraphClient
from officeclaw.exceptions import (
    AttachmentSecurityError,
    AttachmentSizeError,
    AttachmentTypeError,
    GraphAPIError,
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
            order_by: Sort order. Ignored when ``search`` is given, and dropped
                automatically if Graph rejects it for the chosen filter
                (``InefficientFilter``); pass None to never request ordering.
            select: Fields to return

        Returns:
            List of message objects
        """
        params: dict[str, Any] = {"$top": limit}

        # Graph rejects $search combined with $orderby (400 InefficientFilter),
        # so search results keep the service's own relevance ordering.
        if not search:
            params["$orderby"] = order_by

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

        try:
            return self._client.get_all(endpoint, params=params, limit=limit)
        except GraphAPIError as e:
            if e.code != "InefficientFilter" or "$orderby" not in params:
                raise
            # Graph will only sort a filtered collection when it has an index
            # for that pairing: "isRead eq false" sorts by receivedDateTime,
            # "hasAttachments eq true" does not. Returning unordered results
            # beats failing the whole query.
            unordered = {key: value for key, value in params.items() if key != "$orderby"}
            return self._client.get_all(endpoint, params=unordered, limit=limit)

    def get_message(self, message_id: str) -> dict[str, Any]:
        """
        Get a specific message.

        Args:
            message_id: Message ID

        Returns:
            Message object with full details
        """
        message: dict[str, Any] = self._client.get(f"/me/messages/{message_id}")
        return message

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

        policy.check_recipients([*to_list, *cc_list, *bcc_list], action="send", subject=subject)

        draft: dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": content_type,
                "content": body,
            },
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in to_list],
        }

        if cc_list:
            draft["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc_list]

        if bcc_list:
            draft["bccRecipients"] = [{"emailAddress": {"address": addr}} for addr in bcc_list]

        if attachments:
            draft["attachments"] = attachments

        self._client.post("/me/sendMail", {"message": draft, "saveToSentItems": save_to_sent})

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
        action = "reply-all" if reply_all else "reply"
        if policy.get_allowed_recipients() is not None:
            # Graph decides the recipients server-side, so resolve them here to
            # check them; skipped entirely when no allowlist is configured.
            policy.check_recipients(
                self._reply_recipients(message_id, reply_all=reply_all), action=action
            )

        endpoint = f"/me/messages/{message_id}/{'replyAll' if reply_all else 'reply'}"
        self._client.post(endpoint, {"comment": body})

    def _reply_recipients(self, message_id: str, reply_all: bool) -> list[str]:
        """
        Resolve the addresses a reply to this message would be delivered to.

        Mirrors Graph's own behaviour: replies go to replyTo when present and
        the sender otherwise; reply-all adds the original to/cc recipients,
        minus the mailbox owner.
        """
        message = self._client.get(
            f"/me/messages/{message_id}",
            params={"$select": "from,replyTo,toRecipients,ccRecipients"},
        )

        entries = list(message.get("replyTo") or [])
        if not entries and message.get("from"):
            entries.append(message["from"])
        if reply_all:
            entries.extend(message.get("toRecipients") or [])
            entries.extend(message.get("ccRecipients") or [])

        owner = self._owner_address()
        addresses = []
        for entry in entries:
            address = (entry.get("emailAddress") or {}).get("address", "")
            if not address:
                continue
            if owner and address.lower() == owner:
                continue  # A reply is never delivered to the mailbox owner.
            addresses.append(address)
        return addresses

    def _owner_address(self) -> str | None:
        """
        Address of the signed-in mailbox, when it can be determined.

        Best-effort: if it cannot be read, every recipient is checked instead,
        which only ever makes the allowlist stricter.
        """
        try:
            username = self._client.token_manager.get_account_username()
        except Exception:
            return None
        return username.lower() if username else None

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
        policy.check_recipients(to_list, action="forward")

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
        moved: dict[str, Any] = self._client.post(
            f"/me/messages/{message_id}/move",
            {"destinationId": folder_id},
        )
        return moved

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
        updated: dict[str, Any] = self._client.patch(
            f"/me/messages/{message_id}",
            {"isRead": is_read},
        )
        return updated

    def archive(self, message_id: str) -> dict[str, Any]:
        """
        Move message to Archive folder.

        Args:
            message_id: Message ID

        Returns:
            Updated message object
        """
        return self.move(message_id, "archive")

    # ------------------------------------------------------------------
    # Attachments
    # ------------------------------------------------------------------
    #
    # Downloading is gated three ways, in this order: the capability gate, the
    # sender allowlist, then size and type limits. Where the file may be
    # written is a fourth, separate question, handled by officeclaw.policy —
    # the same allowlist that governs which files may be attached to outgoing
    # mail. Bulk download runs each attachment through the identical checks.

    def list_attachments(self, message_id: str) -> list[dict[str, Any]]:
        """
        List a message's attachments, without their content.

        Args:
            message_id: Message ID

        Returns:
            Attachment metadata: id, name, contentType, size, isInline
        """
        return self._client.get_all(
            f"/me/messages/{message_id}/attachments",
            params={"$select": "id,name,contentType,size,isInline"},
        )

    def download_attachment(
        self,
        message_id: str,
        attachment_id: str,
        output_path: str | None = None,
    ) -> str:
        """
        Download one attachment to local storage, with security validation.

        Args:
            message_id: Message ID
            attachment_id: Attachment ID from list_attachments
            output_path: Destination file path (default: auto-generated)

        Returns:
            Path to the downloaded file

        Raises:
            AttachmentSecurityError: If downloading is disabled, or the sender
                is not in the safe senders list
            AttachmentSizeError: If the file exceeds the configured max size
            AttachmentTypeError: If the MIME type is not in the allowed types
            AttachmentNotAllowedError: If the destination is outside
                OFFICECLAW_ALLOWED_ATTACHMENT_DIRS
        """
        self._require_download_enabled()
        self._require_safe_sender(message_id)

        attachment_meta = self._client.get(f"/me/messages/{message_id}/attachments/{attachment_id}")
        self._require_allowed_size_and_type(attachment_meta)

        save_path = self._resolve_save_path(attachment_meta, output_path)

        # File attachments carry base64 contentBytes; anything else is a link
        # or a nested message, and its metadata is saved instead.
        if attachment_meta.get("@odata.type") == "#microsoft.graph.fileAttachment":
            save_path.write_bytes(self._attachment_bytes(message_id, attachment_meta))
        else:
            save_path = self._resolve_collision(save_path.with_suffix(".json"))
            save_path.write_text(json.dumps(attachment_meta, indent=2, default=str))

        return str(save_path)

    def download_attachments(
        self,
        message_id: str,
        dest_dir: str | Path | None = None,
        include_inline: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Save all of a message's attachments to a directory.

        Every attachment goes through the same checks as
        :meth:`download_attachment`; one that fails a size or type limit is
        reported as skipped rather than aborting the rest.

        Args:
            message_id: Message to read
            dest_dir: Directory to write into, created if absent. Defaults to
                :func:`officeclaw.policy.default_download_dir`.
            include_inline: Also save inline images

        Returns:
            One record per attachment: name, and either path or skipped reason
        """
        self._require_download_enabled()
        self._require_safe_sender(message_id)

        directory = policy.check_download_dir(
            policy.default_download_dir() if dest_dir is None else dest_dir
        )
        directory.mkdir(parents=True, exist_ok=True)

        results: list[dict[str, Any]] = []
        for attachment in self.list_attachments(message_id):
            name = attachment.get("name")

            if attachment.get("isInline") and not include_inline:
                results.append({"name": name, "skipped": "inline"})
                continue

            target = directory / policy.safe_attachment_name(name)
            try:
                path = self.download_attachment(
                    message_id, attachment["id"], output_path=str(target)
                )
            except (AttachmentSizeError, AttachmentTypeError) as e:
                results.append({"name": name, "skipped": str(e)})
                continue

            results.append({"name": name, "path": path, "size": Path(path).stat().st_size})

        return results

    # --- checks, shared by both download paths ---

    @staticmethod
    def _require_download_enabled() -> None:
        """Refuse unless OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD is set."""
        if os.environ.get("OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD", "").lower() not in (
            "true",
            "1",
            "yes",
        ):
            raise AttachmentSecurityError(
                "Attachment download is disabled. To enable, set "
                "OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD=true in your .env file."
            )

    def _require_safe_sender(self, message_id: str) -> None:
        """Refuse messages from senders outside the safe list, when enforced."""
        if os.environ.get("OFFICECLAW_SAFE_SENDERS_ONLY", "").lower() not in ("true", "1", "yes"):
            return

        message = self._client.get(f"/me/messages/{message_id}")
        sender = message.get("from", {}).get("emailAddress", {}).get("address", "").lower()

        safe_list_env = os.environ.get("OFFICECLAW_SAFE_SENDERS_LIST", "")
        safe_list = [s.strip() for s in safe_list_env.split(",") if s.strip()]
        if not self._is_safe_sender(sender, safe_list):
            raise AttachmentSecurityError(
                f'Sender "{sender}" is not in the safe senders list. '
                "To allow, add to OFFICECLAW_SAFE_SENDERS_LIST in your .env file."
            )

    def _require_allowed_size_and_type(self, attachment_meta: dict[str, Any]) -> None:
        """Apply the configured size ceiling and MIME type allowlist."""
        size = attachment_meta.get("size", 0)
        max_size_mb = int(os.environ.get("OFFICECLAW_ATTACHMENT_MAX_SIZE_MB", "25"))
        if size > max_size_mb * 1024 * 1024:
            raise AttachmentSizeError(size, max_size_mb)

        content_type = attachment_meta.get("contentType", "application/octet-stream")
        allowed_types_env = os.environ.get("OFFICECLAW_ATTACHMENT_ALLOWED_TYPES", "")
        if allowed_types_env and allowed_types_env.strip() != "*":
            allowed_types = [t.strip() for t in allowed_types_env.split(",") if t.strip()]
            if not self._is_allowed_mime_type(content_type, allowed_types):
                raise AttachmentTypeError(content_type, allowed_types)

    def _resolve_save_path(self, attachment_meta: dict[str, Any], output_path: str | None) -> Path:
        """
        Decide where to write, and confirm the directory is permitted.

        An explicit path is honoured, but its directory is checked like any
        other: an attachment must not be writable outside the configured
        directories just because a caller named the path.
        """
        if output_path:
            target = Path(output_path).expanduser()
            directory = policy.check_download_dir(target.parent)
            save_path = directory / policy.safe_attachment_name(target.name)
        else:
            directory = policy.check_download_dir(policy.default_download_dir())
            save_path = directory / policy.safe_attachment_name(
                attachment_meta.get("name"), fallback="unnamed"
            )

        directory.mkdir(parents=True, exist_ok=True)
        return self._resolve_collision(save_path)

    def _attachment_bytes(self, message_id: str, attachment: dict[str, Any]) -> bytes:
        """
        Content of one file attachment.

        Graph inlines ``contentBytes`` for most attachments; when it does not,
        the value has to be fetched from ``/$value``. Falling back beats
        writing the empty file that a missing ``contentBytes`` would produce.
        """
        content_bytes = attachment.get("contentBytes")
        if content_bytes:
            return base64.b64decode(content_bytes)

        return self._client.get_binary(
            f"/me/messages/{message_id}/attachments/{attachment['id']}/$value"
        )

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
        """Reduce a filename to a bare, portable name (see officeclaw.policy)."""
        return policy.safe_attachment_name(filename, fallback="unnamed")

    def _resolve_collision(self, save_path: Path) -> Path:
        """Handle filename collisions by appending (1), (2), etc."""
        return policy.unique_path(save_path.parent, save_path.name)

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
