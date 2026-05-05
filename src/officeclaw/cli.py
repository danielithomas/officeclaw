"""
Outclaw CLI - Command-line interface for Microsoft Graph API.

Provides mail, calendar, and task operations for OpenClaw agents.

Usage:
    outclaw mail list --limit 10
    outclaw calendar list --start 2026-02-01 --end 2026-02-28
    outclaw tasks list-lists
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from officeclaw import __version__
from officeclaw.auth import TokenManager
from officeclaw.client import GraphClient
from officeclaw.exceptions import (
    AttachmentSecurityError,
    AttachmentSizeError,
    AttachmentTypeError,
    AuthenticationError,
    GraphAPIError,
    OutclawError,
)

# Rich console for pretty output
console = Console()
error_console = Console(stderr=True)


# ============================================
# CAPABILITY GATES
# ============================================
# Write operations (send, delete, forward) are disabled by default.
# Enable them explicitly via environment variables.


_dotenv_loaded = False


def _is_enabled(env_var: str) -> bool:
    """Check if a capability is enabled via env var or .env file."""
    global _dotenv_loaded  # noqa: PLW0603
    if not _dotenv_loaded:
        from dotenv import load_dotenv

        load_dotenv()
        _dotenv_loaded = True
    return os.environ.get(env_var, "").lower() in ("true", "1", "yes")


def require_capability(env_var: str, action: str) -> None:
    """Raise an error if a capability is not enabled.

    Args:
        env_var: Environment variable that enables this capability.
        action: Human-readable description of the action (e.g., "send emails").
    """
    if not _is_enabled(env_var):
        error_console.print(f"[red]Blocked:[/red] {action} is disabled by default for safety.")
        error_console.print(f"To enable, set [bold]{env_var}=true[/bold] in your .env file.")
        sys.exit(1)


def output_json(data: Any, status: str = "success") -> None:
    """Output data as JSON."""
    response = {"status": status}
    if status == "success":
        response["data"] = data
    else:
        response["error"] = data
    click.echo(json.dumps(response, indent=2, default=str))


def handle_error(e: Exception) -> None:
    """Handle and display errors."""
    if isinstance(e, AuthenticationError):
        error_console.print(f"[red]Authentication Error:[/red] {e}")
        error_console.print("Run [bold]officeclaw auth login[/bold] to authenticate.")
    elif isinstance(e, GraphAPIError):
        error_console.print(f"[red]API Error ({e.code}):[/red] {e.message}")
    elif isinstance(e, AttachmentSecurityError):
        error_console.print(f"[red]Security Blocked:[/red] {e}")
    elif isinstance(e, AttachmentSizeError):
        error_console.print(
            f"[red]Error:[/red] Attachment size ({e.size_bytes / 1024 / 1024:.1f} MB) exceeds maximum ({e.max_size_mb} MB)"
        )
    elif isinstance(e, AttachmentTypeError):
        error_console.print(
            f"[red]Error:[/red] Attachment type '{e.content_type}' not allowed. Allowed: {', '.join(e.allowed_types)}"
        )
    elif isinstance(e, OutclawError):
        error_console.print(f"[red]Error:[/red] {e}")
    else:
        error_console.print(f"[red]Unexpected Error:[/red] {e}")
    sys.exit(1)


# ============================================
# MAIN CLI GROUP
# ============================================


@click.group()
@click.version_option(version=__version__, prog_name="officeclaw")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def main(ctx: click.Context, json_output: bool) -> None:
    """
    Outclaw - Microsoft Graph API integration for OpenClaw.

    Manage email, calendar, and tasks from your personal Microsoft account.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output


# ============================================
# AUTH COMMANDS
# ============================================


@main.group()
def auth() -> None:
    """Authentication commands."""
    pass


@auth.command()
def login() -> None:
    """Authenticate with Microsoft (opens browser)."""
    try:
        # Import here to avoid circular imports
        from officeclaw.auth_flow import run_auth_flow

        run_auth_flow()
    except ImportError:
        error_console.print("[yellow]Auth flow not yet implemented.[/yellow]")
        error_console.print("Please run the auth setup script manually.")
        sys.exit(1)
    except Exception as e:
        handle_error(e)


@auth.command()
def logout() -> None:
    """Clear stored authentication tokens."""
    try:
        manager = TokenManager()
        manager.clear_tokens()
        console.print("[green]✓[/green] Logged out successfully.")
    except Exception as e:
        handle_error(e)


@auth.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show authentication status."""
    try:
        manager = TokenManager()
        info = manager.get_token_info()

        if ctx.obj.get("json"):
            output_json(info)
            return

        if not info:
            console.print("[yellow]Not authenticated.[/yellow]")
            console.print("Run [bold]officeclaw auth login[/bold] to authenticate.")
            return

        table = Table(title="Authentication Status")
        table.add_column("Property", style="cyan")
        table.add_column("Value")

        status_emoji = "🔴" if info["is_expired"] else "🟢"
        table.add_row("Status", f"{status_emoji} {'Expired' if info['is_expired'] else 'Valid'}")
        if "account" in info:
            table.add_row("Account", info["account"])
        if "mode" in info:
            table.add_row("Mode", info["mode"])
        if "expires_at" in info:
            table.add_row("Expires", info["expires_at"])
        table.add_row("Time Left", f"{info['time_until_expiry_seconds']}s")
        table.add_row("Needs Refresh", "Yes" if info["needs_refresh"] else "No")
        table.add_row("Storage", info["storage_location"])
        scopes = info.get("scopes", [])
        table.add_row("Scopes", ", ".join(scopes[:3]) + ("..." if len(scopes) > 3 else ""))

        console.print(table)

    except Exception as e:
        handle_error(e)


# ============================================
# MAIL COMMANDS
# ============================================


@main.group()
def mail() -> None:
    """Email operations."""
    pass


@mail.command("list")
@click.option("--limit", default=10, help="Number of messages to return")
@click.option("--folder", default="inbox", help="Mail folder")
@click.option("--unread", is_flag=True, help="Only unread messages")
@click.pass_context
def mail_list(ctx: click.Context, limit: int, folder: str, unread: bool) -> None:
    """List email messages."""
    try:
        with GraphClient() as client:
            params: dict[str, Any] = {
                "$top": limit,
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,receivedDateTime,isRead,importance",
            }
            if unread:
                params["$filter"] = "isRead eq false"

            endpoint = f"/me/mailFolders/{folder}/messages"
            messages = client.get_all(endpoint, params=params, limit=limit)

            if ctx.obj.get("json"):
                output_json(messages)
                return

            if not messages:
                console.print("[yellow]No messages found.[/yellow]")
                return

            table = Table(title=f"Messages ({folder})")
            table.add_column("From", style="cyan", max_width=25)
            table.add_column("Subject", max_width=40)
            table.add_column("Date", style="dim")
            table.add_column("Read")

            for msg in messages:
                from_addr = msg.get("from", {}).get("emailAddress", {})
                from_name = from_addr.get("name", from_addr.get("address", "Unknown"))
                subject = msg.get("subject", "(No subject)")[:40]
                date = msg.get("receivedDateTime", "")[:10]
                is_read = "✓" if msg.get("isRead") else "•"

                table.add_row(from_name[:25], subject, date, is_read)

            console.print(table)

    except Exception as e:
        handle_error(e)


@mail.command("get")
@click.argument("message_id")
@click.pass_context
def mail_get(ctx: click.Context, message_id: str) -> None:
    """Get a specific email message."""
    try:
        with GraphClient() as client:
            message = client.get(f"/me/messages/{message_id}")

            if ctx.obj.get("json"):
                output_json(message)
                return

            console.print(f"[bold]Subject:[/bold] {message.get('subject')}")
            console.print(
                f"[bold]From:[/bold] {message.get('from', {}).get('emailAddress', {}).get('address')}"
            )
            console.print(f"[bold]Date:[/bold] {message.get('receivedDateTime')}")
            console.print()
            console.print(message.get("bodyPreview", ""))

    except Exception as e:
        handle_error(e)


@mail.command("send")
@click.option("--to", required=True, help="Recipient email address")
@click.option("--subject", required=True, help="Email subject")
@click.option("--body", required=True, help="Email body")
@click.option("--html", is_flag=True, default=False, help="Send body as HTML instead of plain text")
@click.option("--attachment", multiple=True, help="File path to attach (repeatable)")
@click.pass_context
def mail_send(
    ctx: click.Context, to: str, subject: str, body: str, html: bool, attachment: tuple[str, ...]
) -> None:
    """Send an email message.

    Requires OFFICECLAW_ENABLE_SEND=true in .env (disabled by default for safety).
    """
    require_capability("OFFICECLAW_ENABLE_SEND", "Sending emails")
    import base64
    import mimetypes
    from pathlib import Path

    # Recipient allowlist enforcement
    allowed_recipients_env = os.environ.get("OFFICECLAW_ALLOWED_RECIPIENTS", "")
    if not allowed_recipients_env:
        error_console.print(
            "[yellow]⚠️  No recipient allowlist configured. All addresses are permitted.[/yellow]\n"
            "[yellow]   Set OFFICECLAW_ALLOWED_RECIPIENTS in .env to restrict outbound email.[/yellow]\n"
            "[yellow]   Example: OFFICECLAW_ALLOWED_RECIPIENTS=alice@example.com,bob@example.com[/yellow]"
        )
    if allowed_recipients_env:
        allowed = {
            addr.strip().lower() for addr in allowed_recipients_env.split(",") if addr.strip()
        }
        if to.strip().lower() not in allowed:
            from datetime import datetime, timezone

            block_msg = (
                f"Blocked: {to} is not in the allowed recipients list.\n"
                f"Subject: {subject}\n"
                f"Allowed: {', '.join(sorted(allowed))}"
            )
            error_console.print(f"[red]{block_msg}[/red]")

            # Log the blocked attempt
            log_dir = Path.home() / ".openclaw" / "workspace" / "automation" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "email-blocked.log"
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            with open(log_file, "a") as f:
                f.write(f"[{ts}] BLOCKED | to={to} | subject={subject}\n")

            # Alert: write a machine-readable alert file for external monitoring
            alert_file = log_dir / "email-alert.json"
            import json as _json

            alert = {
                "type": "email_blocked",
                "timestamp": ts,
                "to": to,
                "subject": subject,
                "allowed_recipients": sorted(allowed),
            }
            with open(alert_file, "w") as f:
                _json.dump(alert, f, indent=2)

            sys.exit(1)

    try:
        attachments = []
        for file_path in attachment:
            p = Path(file_path)
            if not p.exists():
                error_console.print(f"[red]File not found:[/red] {file_path}")
                sys.exit(1)
            content_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            content_bytes = base64.b64encode(p.read_bytes()).decode("utf-8")
            attachments.append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": p.name,
                    "contentType": content_type,
                    "contentBytes": content_bytes,
                }
            )

        with GraphClient() as client:
            message: dict[str, Any] = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML" if html else "Text", "content": body},
                    "toRecipients": [{"emailAddress": {"address": to}}],
                },
                "saveToSentItems": True,
            }
            if attachments:
                message["message"]["attachments"] = attachments
            client.post("/me/sendMail", message)

            if ctx.obj.get("json"):
                output_json({"sent": True, "to": to, "subject": subject})
            else:
                console.print(f"[green]✓[/green] Email sent to {to}")

    except Exception as e:
        handle_error(e)


@mail.command("reply")
@click.argument("message_id")
@click.option("--body", required=True, help="Reply body")
@click.option("--reply-all", is_flag=True, help="Reply to all recipients")
@click.pass_context
def mail_reply(ctx: click.Context, message_id: str, body: str, reply_all: bool) -> None:
    """Reply to an email message.

    Requires OFFICECLAW_ENABLE_SEND=true in .env (disabled by default for safety).
    """
    require_capability("OFFICECLAW_ENABLE_SEND", "Sending emails")
    try:
        from officeclaw.mail import MailClient

        with MailClient() as mc:
            mc.reply(message_id, body, reply_all=reply_all)

        if ctx.obj.get("json"):
            output_json({"replied": True, "message_id": message_id, "reply_all": reply_all})
        else:
            action = "Reply-all" if reply_all else "Reply"
            console.print(f"[green]✓[/green] {action} sent.")
    except Exception as e:
        handle_error(e)


@mail.command("forward")
@click.argument("message_id")
@click.option("--to", required=True, help="Recipient email address")
@click.option("--comment", default="", help="Optional comment")
@click.pass_context
def mail_forward(ctx: click.Context, message_id: str, to: str, comment: str) -> None:
    """Forward an email message.

    Requires OFFICECLAW_ENABLE_SEND=true in .env (disabled by default for safety).
    """
    require_capability("OFFICECLAW_ENABLE_SEND", "Sending emails")
    try:
        from officeclaw.mail import MailClient

        with MailClient() as mc:
            mc.forward(message_id, to, comment=comment)

        if ctx.obj.get("json"):
            output_json({"forwarded": True, "message_id": message_id, "to": to})
        else:
            console.print(f"[green]✓[/green] Message forwarded to {to}")
    except Exception as e:
        handle_error(e)


@mail.command("move")
@click.argument("message_id")
@click.option("--folder", required=True, help="Destination folder name or ID")
@click.pass_context
def mail_move(ctx: click.Context, message_id: str, folder: str) -> None:
    """Move a message to a folder."""
    try:
        from officeclaw.mail import MailClient

        with MailClient() as mc:
            result = mc.move(message_id, folder)

        if ctx.obj.get("json"):
            output_json(result)
        else:
            console.print(f"[green]✓[/green] Message moved to {folder}")
    except Exception as e:
        handle_error(e)


@mail.command("delete")
@click.argument("message_id")
@click.pass_context
def mail_delete(ctx: click.Context, message_id: str) -> None:
    """Delete an email message.

    Requires OFFICECLAW_ENABLE_DELETE=true in .env (disabled by default for safety).
    """
    require_capability("OFFICECLAW_ENABLE_DELETE", "Deleting emails")
    try:
        from officeclaw.mail import MailClient

        with MailClient() as mc:
            mc.delete(message_id)

        if ctx.obj.get("json"):
            output_json({"deleted": True, "message_id": message_id})
        else:
            console.print("[green]✓[/green] Message deleted.")
    except Exception as e:
        handle_error(e)


@mail.command("search")
@click.argument("query")
@click.option("--folder", default=None, help="Folder to search (default: all)")
@click.option("--limit", default=25, help="Maximum results")
@click.pass_context
def mail_search(ctx: click.Context, query: str, folder: str | None, limit: int) -> None:
    """Search email messages."""
    try:
        from officeclaw.mail import MailClient

        with MailClient() as mc:
            messages = mc.search(query, folder=folder, limit=limit)

        if ctx.obj.get("json"):
            output_json(messages)
            return

        if not messages:
            console.print("[yellow]No messages found.[/yellow]")
            return

        table = Table(title=f'Search: "{query}"')
        table.add_column("From", style="cyan", max_width=25)
        table.add_column("Subject", max_width=40)
        table.add_column("Date", style="dim")

        for msg in messages:
            from_addr = msg.get("from", {}).get("emailAddress", {})
            from_name = from_addr.get("name", from_addr.get("address", "Unknown"))
            subject = msg.get("subject", "(No subject)")[:40]
            date = msg.get("receivedDateTime", "")[:10]
            table.add_row(from_name[:25], subject, date)

        console.print(table)
    except Exception as e:
        handle_error(e)


@mail.command("mark-read")
@click.argument("message_id")
@click.option("--unread", is_flag=True, help="Mark as unread instead")
@click.pass_context
def mail_mark_read(ctx: click.Context, message_id: str, unread: bool) -> None:
    """Mark a message as read (or unread with --unread)."""
    try:
        from officeclaw.mail import MailClient

        with MailClient() as mc:
            result = mc.mark_read(message_id, is_read=not unread)

        if ctx.obj.get("json"):
            output_json(result)
        else:
            status = "unread" if unread else "read"
            console.print(f"[green]✓[/green] Message marked as {status}.")
    except Exception as e:
        handle_error(e)


@mail.command("archive")
@click.argument("message_id")
@click.pass_context
def mail_archive(ctx: click.Context, message_id: str) -> None:
    """Archive a message (move to Archive folder)."""
    try:
        from officeclaw.mail import MailClient

        with MailClient() as mc:
            result = mc.archive(message_id)

        if ctx.obj.get("json"):
            output_json(result)
        else:
            console.print("[green]✓[/green] Message archived.")
    except Exception as e:
        handle_error(e)


@mail.command("attachments")
@click.argument("message_id")
@click.pass_context
def mail_attachments(ctx: click.Context, message_id: str) -> None:
    """List attachments for a message."""
    try:
        with GraphClient() as client:
            attachments = client.get_all(f"/me/messages/{message_id}/attachments")

        if ctx.obj.get("json"):
            output_json(attachments)
            return

        if not attachments:
            console.print("[yellow]No attachments found.[/yellow]")
            return

        table = Table(title=f"Attachments ({message_id[:20]}...)")
        table.add_column("Name", style="cyan", max_width=40)
        table.add_column("Type")
        table.add_column("Size", justify="right")
        table.add_column("Inline")

        for att in attachments:
            name = att.get("name", "(unnamed)")
            content_type = att.get("contentType", "unknown")
            size = att.get("size", 0)
            is_inline = "Yes" if att.get("isInline") else "No"
            size_str = f"{size / 1024:.1f} KB" if size else "0 B"

            table.add_row(name, content_type, size_str, is_inline)

        console.print(table)
    except Exception as e:
        handle_error(e)


@mail.command("download")
@click.argument("message_id")
@click.argument("attachment_name")
@click.argument("output_path", required=False, default=None)
@click.pass_context
def mail_download(ctx: click.Context, message_id: str, attachment_name: str, output_path: str | None) -> None:
    """Download an attachment from a message.

    Requires OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD=true in .env (disabled by default for safety).
    """
    require_capability("OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD", "Downloading attachments")
    try:
        from officeclaw.mail import MailClient

        with MailClient() as mc:
            attachments = mc.list_attachments(message_id)

            # Find attachment by name
            attachment_id = None
            for att in attachments:
                if att.get("name", "").lower() == attachment_name.lower():
                    attachment_id = att.get("id")
                    break

            if not attachment_id:
                error_console.print(
                    f"[red]Attachment not found:[/red] '{attachment_name}' on message {message_id}"
                )
                error_console.print(
                    f"Run [bold]officeclaw mail attachments {message_id}[/bold] to list available attachments."
                )
                sys.exit(1)

            downloaded_path = mc.download_attachment(
                message_id, attachment_id, output_path=output_path
            )

        if ctx.obj.get("json"):
            output_json({"downloaded": True, "path": downloaded_path})
        else:
            console.print(f"[green]✓[/green] Downloaded: {downloaded_path}")
    except Exception as e:
        handle_error(e)


# ============================================
# CALENDAR COMMANDS
# ============================================


@main.group()
def calendar() -> None:
    """Calendar operations."""
    pass


@calendar.command("list")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", required=True, help="End date (YYYY-MM-DD)")
@click.option("--limit", default=50, help="Maximum events")
@click.pass_context
def calendar_list(ctx: click.Context, start: str, end: str, limit: int) -> None:
    """List calendar events in date range."""
    try:
        with GraphClient() as client:
            params = {
                "startDateTime": f"{start}T00:00:00Z",
                "endDateTime": f"{end}T23:59:59Z",
                "$top": limit,
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,location,isAllDay",
            }
            events = client.get_all("/me/calendarView", params=params, limit=limit)

            if ctx.obj.get("json"):
                output_json(events)
                return

            if not events:
                console.print("[yellow]No events found.[/yellow]")
                return

            table = Table(title=f"Events ({start} to {end})")
            table.add_column("Date", style="cyan")
            table.add_column("Time")
            table.add_column("Subject", max_width=35)
            table.add_column("Location", max_width=20)

            for event in events:
                start_dt = event.get("start", {}).get("dateTime", "")
                date = start_dt[:10] if start_dt else ""
                time_str = start_dt[11:16] if start_dt else ""
                subject = event.get("subject", "")[:35]
                location = (event.get("location", {}).get("displayName", "") or "")[:20]

                table.add_row(date, time_str, subject, location)

            console.print(table)

    except Exception as e:
        handle_error(e)


@calendar.command("get")
@click.argument("event_id")
@click.pass_context
def calendar_get(ctx: click.Context, event_id: str) -> None:
    """Get a specific calendar event."""
    try:
        from officeclaw.calendar import CalendarClient

        with CalendarClient() as cc:
            event = cc.get_event(event_id)

        if ctx.obj.get("json"):
            output_json(event)
            return

        console.print(f"[bold]Subject:[/bold] {event.get('subject')}")
        start = event.get("start", {})
        console.print(f"[bold]Start:[/bold] {start.get('dateTime')} ({start.get('timeZone')})")
        end = event.get("end", {})
        console.print(f"[bold]End:[/bold] {end.get('dateTime')} ({end.get('timeZone')})")
        location = event.get("location", {}).get("displayName", "")
        if location:
            console.print(f"[bold]Location:[/bold] {location}")
        body_preview = event.get("bodyPreview", "")
        if body_preview:
            console.print()
            console.print(body_preview)
    except Exception as e:
        handle_error(e)


@calendar.command("create")
@click.option("--subject", required=True, help="Event subject")
@click.option("--start", required=True, help="Start datetime (YYYY-MM-DDTHH:MM:SS)")
@click.option("--end", required=True, help="End datetime (YYYY-MM-DDTHH:MM:SS)")
@click.option("--location", default="", help="Event location")
@click.pass_context
def calendar_create(ctx: click.Context, subject: str, start: str, end: str, location: str) -> None:
    """Create a calendar event."""
    try:
        with GraphClient() as client:
            event = {
                "subject": subject,
                "start": {"dateTime": start, "timeZone": "UTC"},
                "end": {"dateTime": end, "timeZone": "UTC"},
            }
            if location:
                event["location"] = {"displayName": location}

            result = client.post("/me/events", event)

            if ctx.obj.get("json"):
                output_json(result)
            else:
                console.print(f"[green]✓[/green] Event created: {subject}")

    except Exception as e:
        handle_error(e)


@calendar.command("update")
@click.argument("event_id")
@click.option("--subject", default=None, help="New subject")
@click.option("--start", default=None, help="New start datetime")
@click.option("--end", default=None, help="New end datetime")
@click.option("--location", default=None, help="New location")
@click.option("--body", default=None, help="New description")
@click.pass_context
def calendar_update(
    ctx: click.Context,
    event_id: str,
    subject: str | None,
    start: str | None,
    end: str | None,
    location: str | None,
    body: str | None,
) -> None:
    """Update a calendar event."""
    try:
        from officeclaw.calendar import CalendarClient

        with CalendarClient() as cc:
            result = cc.update_event(
                event_id,
                subject=subject,
                start=start,
                end=end,
                location=location,
                body=body,
            )

        if ctx.obj.get("json"):
            output_json(result)
        else:
            console.print(f"[green]✓[/green] Event updated: {result.get('subject', event_id)}")
    except Exception as e:
        handle_error(e)


@calendar.command("delete")
@click.argument("event_id")
@click.pass_context
def calendar_delete(ctx: click.Context, event_id: str) -> None:
    """Delete a calendar event.

    Requires OFFICECLAW_ENABLE_DELETE=true in .env (disabled by default for safety).
    """
    require_capability("OFFICECLAW_ENABLE_DELETE", "Deleting calendar events")
    try:
        from officeclaw.calendar import CalendarClient

        with CalendarClient() as cc:
            cc.delete_event(event_id)

        if ctx.obj.get("json"):
            output_json({"deleted": True, "event_id": event_id})
        else:
            console.print("[green]✓[/green] Event deleted.")
    except Exception as e:
        handle_error(e)


@calendar.command("accept")
@click.argument("event_id")
@click.option("--comment", default="", help="Response comment")
@click.pass_context
def calendar_accept(ctx: click.Context, event_id: str, comment: str) -> None:
    """Accept a meeting invitation."""
    try:
        from officeclaw.calendar import CalendarClient

        with CalendarClient() as cc:
            cc.accept_event(event_id, comment=comment)

        if ctx.obj.get("json"):
            output_json({"accepted": True, "event_id": event_id})
        else:
            console.print("[green]✓[/green] Meeting accepted.")
    except Exception as e:
        handle_error(e)


@calendar.command("decline")
@click.argument("event_id")
@click.option("--comment", default="", help="Response comment")
@click.pass_context
def calendar_decline(ctx: click.Context, event_id: str, comment: str) -> None:
    """Decline a meeting invitation."""
    try:
        from officeclaw.calendar import CalendarClient

        with CalendarClient() as cc:
            cc.decline_event(event_id, comment=comment)

        if ctx.obj.get("json"):
            output_json({"declined": True, "event_id": event_id})
        else:
            console.print("[green]✓[/green] Meeting declined.")
    except Exception as e:
        handle_error(e)


@calendar.command("list-calendars")
@click.pass_context
def calendar_list_calendars(ctx: click.Context) -> None:
    """List all calendars."""
    try:
        from officeclaw.calendar import CalendarClient

        with CalendarClient() as cc:
            calendars = cc.list_calendars()

        if ctx.obj.get("json"):
            output_json(calendars)
            return

        if not calendars:
            console.print("[yellow]No calendars found.[/yellow]")
            return

        table = Table(title="Calendars")
        table.add_column("Name", style="cyan")
        table.add_column("ID", style="dim", max_width=20)

        for cal in calendars:
            name = cal.get("name", "")
            cal_id = cal.get("id", "")[:20]
            table.add_row(name, cal_id + "...")

        console.print(table)
    except Exception as e:
        handle_error(e)


# ============================================
# TASKS COMMANDS
# ============================================


@main.group()
def tasks() -> None:
    """Task operations (Microsoft To Do)."""
    pass


@tasks.command("list-lists")
@click.pass_context
def tasks_list_lists(ctx: click.Context) -> None:
    """List all task lists."""
    try:
        with GraphClient() as client:
            lists = client.get_all("/me/todo/lists")

            if ctx.obj.get("json"):
                output_json(lists)
                return

            if not lists:
                console.print("[yellow]No task lists found.[/yellow]")
                return

            table = Table(title="Task Lists")
            table.add_column("Name", style="cyan")
            table.add_column("ID", style="dim", max_width=20)

            for lst in lists:
                name = lst.get("displayName", "")
                list_id = lst.get("id", "")[:20]
                table.add_row(name, list_id + "...")

            console.print(table)

    except Exception as e:
        handle_error(e)


@tasks.command("list")
@click.option("--list-id", required=True, help="Task list ID")
@click.option("--status", type=click.Choice(["all", "active", "completed"]), default="all")
@click.pass_context
def tasks_list(ctx: click.Context, list_id: str, status: str) -> None:
    """List tasks in a task list."""
    try:
        with GraphClient() as client:
            params: dict[str, Any] = {}
            if status == "active":
                params["$filter"] = "status ne 'completed'"
            elif status == "completed":
                params["$filter"] = "status eq 'completed'"

            tasks_list = client.get_all(f"/me/todo/lists/{list_id}/tasks", params=params or None)

            if ctx.obj.get("json"):
                output_json(tasks_list)
                return

            if not tasks_list:
                console.print("[yellow]No tasks found.[/yellow]")
                return

            table = Table(title="Tasks")
            table.add_column("Status")
            table.add_column("Title", max_width=40)
            table.add_column("Due", style="dim")

            for task in tasks_list:
                task_status = "✓" if task.get("status") == "completed" else "○"
                title = task.get("title", "")[:40]
                due = (
                    task.get("dueDateTime", {}).get("dateTime", "")[:10]
                    if task.get("dueDateTime")
                    else ""
                )

                table.add_row(task_status, title, due)

            console.print(table)

    except Exception as e:
        handle_error(e)


@tasks.command("create")
@click.option("--list-id", required=True, help="Task list ID")
@click.option("--title", required=True, help="Task title")
@click.option("--due-date", default=None, help="Due date (YYYY-MM-DD)")
@click.pass_context
def tasks_create(ctx: click.Context, list_id: str, title: str, due_date: str | None) -> None:
    """Create a new task."""
    try:
        with GraphClient() as client:
            task: dict[str, Any] = {"title": title}
            if due_date:
                task["dueDateTime"] = {
                    "dateTime": f"{due_date}T00:00:00.0000000",
                    "timeZone": "UTC",
                }

            result = client.post(f"/me/todo/lists/{list_id}/tasks", task)

            if ctx.obj.get("json"):
                output_json(result)
            else:
                console.print(f"[green]✓[/green] Task created: {title}")

    except Exception as e:
        handle_error(e)


@tasks.command("complete")
@click.option("--list-id", required=True, help="Task list ID")
@click.option("--task-id", required=True, help="Task ID")
@click.pass_context
def tasks_complete(ctx: click.Context, list_id: str, task_id: str) -> None:
    """Mark a task as completed."""
    try:
        from datetime import datetime, timezone

        with GraphClient() as client:
            completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
            data = {
                "status": "completed",
                "completedDateTime": {
                    "dateTime": completed_at,
                    "timeZone": "UTC",
                },
            }
            result = client.patch(f"/me/todo/lists/{list_id}/tasks/{task_id}", data)

            if ctx.obj.get("json"):
                output_json(result)
            else:
                console.print("[green]✓[/green] Task marked as completed.")

    except Exception as e:
        handle_error(e)


@tasks.command("reopen")
@click.option("--list-id", required=True, help="Task list ID")
@click.option("--task-id", required=True, help="Task ID")
@click.pass_context
def tasks_reopen(ctx: click.Context, list_id: str, task_id: str) -> None:
    """Reopen a completed task."""
    try:
        with GraphClient() as client:
            data = {
                "status": "notStarted",
                "completedDateTime": None,
            }
            result = client.patch(f"/me/todo/lists/{list_id}/tasks/{task_id}", data)

            if ctx.obj.get("json"):
                output_json(result)
            else:
                console.print("[green]✓[/green] Task reopened.")

    except Exception as e:
        handle_error(e)


@tasks.command("get")
@click.option("--list-id", required=True, help="Task list ID")
@click.option("--task-id", required=True, help="Task ID")
@click.pass_context
def tasks_get(ctx: click.Context, list_id: str, task_id: str) -> None:
    """Get a specific task."""
    try:
        from officeclaw.tasks import TasksClient

        with TasksClient() as tc:
            task = tc.get_task(list_id, task_id)

        if ctx.obj.get("json"):
            output_json(task)
            return

        console.print(f"[bold]Title:[/bold] {task.get('title')}")
        console.print(f"[bold]Status:[/bold] {task.get('status')}")
        console.print(f"[bold]Importance:[/bold] {task.get('importance')}")
        due = task.get("dueDateTime")
        if due:
            console.print(f"[bold]Due:[/bold] {due.get('dateTime', '')[:10]}")
        body = task.get("body", {}).get("content", "")
        if body:
            console.print()
            console.print(body)
    except Exception as e:
        handle_error(e)


@tasks.command("update")
@click.option("--list-id", required=True, help="Task list ID")
@click.option("--task-id", required=True, help="Task ID")
@click.option("--title", default=None, help="New title")
@click.option("--body", default=None, help="New description")
@click.option("--due-date", default=None, help="New due date (YYYY-MM-DD)")
@click.option(
    "--importance", type=click.Choice(["low", "normal", "high"]), default=None, help="Importance"
)
@click.pass_context
def tasks_update(
    ctx: click.Context,
    list_id: str,
    task_id: str,
    title: str | None,
    body: str | None,
    due_date: str | None,
    importance: str | None,
) -> None:
    """Update a task."""
    try:
        from officeclaw.tasks import TasksClient

        with TasksClient() as tc:
            result = tc.update_task(
                list_id,
                task_id,
                title=title,
                body=body,
                due_date=due_date,
                importance=importance,
            )

        if ctx.obj.get("json"):
            output_json(result)
        else:
            console.print(f"[green]✓[/green] Task updated: {result.get('title', task_id)}")
    except Exception as e:
        handle_error(e)


@tasks.command("delete")
@click.option("--list-id", required=True, help="Task list ID")
@click.option("--task-id", required=True, help="Task ID")
@click.pass_context
def tasks_delete(ctx: click.Context, list_id: str, task_id: str) -> None:
    """Delete a task.

    Requires OFFICECLAW_ENABLE_DELETE=true in .env (disabled by default for safety).
    """
    require_capability("OFFICECLAW_ENABLE_DELETE", "Deleting tasks")
    try:
        from officeclaw.tasks import TasksClient

        with TasksClient() as tc:
            tc.delete_task(list_id, task_id)

        if ctx.obj.get("json"):
            output_json({"deleted": True, "task_id": task_id})
        else:
            console.print("[green]✓[/green] Task deleted.")
    except Exception as e:
        handle_error(e)


if __name__ == "__main__":
    main()
