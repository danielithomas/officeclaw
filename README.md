<p align="center">
  <img src="docs/logo.png" alt="OfficeClaw" width="200">
</p>

<h1 align="center">OfficeClaw</h1>

<p align="center">
  <em>Microsoft Graph API integration for OpenClaw agents — manage email, calendar, and tasks.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/officeclaw/"><img src="https://img.shields.io/pypi/v/officeclaw.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/officeclaw/"><img src="https://img.shields.io/pypi/pyversions/officeclaw.svg" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
</p>

## Overview

**OfficeClaw** is an [OpenClaw](https://docs.openclaw.ai) skill that enables AI agents to interact with personal Microsoft accounts through the Microsoft Graph API. Agents can read/write emails, manage calendar events, and handle tasks — all through natural language commands.

- 📧 **Email** — Read inbox, send emails with attachments, search, mark read/unread, archive
- 📅 **Calendar** — View events, create meetings, update, accept/decline
- ✅ **Tasks** — Manage Microsoft To Do lists, create/complete/reopen tasks

## Quick Start

### Installation

```bash
pip install officeclaw
```

### Setup (One-Time)

> **Quick start:** OfficeClaw ships with a default app registration — just run `officeclaw auth login` and go. No Azure setup needed.
>
> **Advanced:** Want full control? Create your own Azure App Registration (free, ~5 minutes) and set `OFFICECLAW_CLIENT_ID` in your `.env`. See [Microsoft's guide](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app) or follow the steps below.

#### 1. Create an Azure App Registration

1. Go to [entra.microsoft.com](https://entra.microsoft.com) → App registrations → New registration
2. Name: `officeclaw` (or anything you like)
3. Supported account types: **Personal Microsoft accounts only**
4. Redirect URI: leave blank (not needed for device code flow)
5. Click **Register**
6. Copy the **Application (client) ID** — this is your `OFFICECLAW_CLIENT_ID`
7. Go to **Authentication** → Advanced settings → **Allow public client flows** → **Yes** → Save
8. Go to **API permissions** → Add permission → Microsoft Graph → Delegated permissions. Choose based on your needs:

   **Read-only (safest):**
   - `Mail.Read`, `Calendars.Read`, `Tasks.ReadWrite`*

   **Full access (all features including send/delete):**
   - `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`
   - `Calendars.Read`, `Calendars.ReadWrite`
   - `Tasks.ReadWrite`

   *\*Tasks.ReadWrite is the minimum available scope for Microsoft To Do — there is no read-only option.*

   > **Least privilege:** Only grant the permissions you actually need. If you only want to read emails and calendar, skip `Mail.ReadWrite`, `Mail.Send`, and `Calendars.ReadWrite`. OfficeClaw will gracefully error on commands that require missing permissions.

#### 2. Configure Environment

Create a `.env` file:

```bash
OFFICECLAW_CLIENT_ID=your-client-id-here

# Capability gates (disabled by default for safety)
# OFFICECLAW_ENABLE_SEND=true    # Allow sending/replying/forwarding emails
# OFFICECLAW_ENABLE_DELETE=true   # Allow deleting emails, events, and tasks
```

No client secret needed for device code flow. Write operations (send, delete) are **disabled by default** — enable only what you need.

#### 3. Authenticate

```bash
officeclaw auth login
```

This displays a URL and code. Open the URL in a browser, enter the code, and sign in with your Microsoft account. Tokens are stored securely in `~/.officeclaw/token_cache.json` (permissions 600).

### Usage

```bash
# List recent emails
officeclaw mail list --limit 10

# Send an email with attachment
officeclaw mail send --to user@example.com --subject "Report" --body "See attached" --attachment report.pdf

# Search emails
officeclaw mail search --query "from:boss@example.com"

# View calendar
officeclaw calendar list --start 2026-02-01 --end 2026-02-28

# Create a calendar event
officeclaw calendar create --subject "Team Meeting" --start "2026-02-15T10:00:00" --end "2026-02-15T11:00:00" --location "Conference Room"

# List task lists
officeclaw tasks list-lists

# Create a task
officeclaw tasks create --list-id <id> --title "Review report" --due-date "2026-02-20"

# JSON output (for agents)
officeclaw --json mail list
```

## For OpenClaw Agents

Install as a skill:

```bash
clawhub install officeclaw
```

Once installed, OpenClaw agents can use OfficeClaw through natural language:

```
User: "Show me today's calendar"
Agent: You have 3 events today:
       • 9:00 AM — Team standup
       • 2:00 PM — Client call
       • 4:00 PM — Project review

User: "Send an email to john@example.com about tomorrow's meeting"
Agent: Email sent to john@example.com ✓

User: "Mark 'finish report' as done"
Agent: Task completed ✓
```

See [skill/SKILL.md](skill/SKILL.md) for the full skill manifest.

## Commands

### Authentication

| Command | Description |
|---------|-------------|
| `officeclaw auth login` | Authenticate via device code flow |
| `officeclaw auth status` | Show authentication status |
| `officeclaw auth logout` | Clear stored tokens |

### Email

| Command | Description |
|---------|-------------|
| `officeclaw mail list` | List messages |
| `officeclaw mail list --unread` | List unread messages only |
| `officeclaw mail get <id>` | Get message details |
| `officeclaw mail send --to <email> --subject <subj> --body <body>` | Send email |
| `officeclaw mail send ... --attachment <file>` | Send email with attachment |
| `officeclaw mail search --query <query>` | Search emails |
| `officeclaw mail archive <id>` | Archive a message |
| `officeclaw mail mark-read <id>` | Mark as read |

### Calendar

| Command | Description |
|---------|-------------|
| `officeclaw calendar list --start <date> --end <date>` | List events |
| `officeclaw calendar get <id>` | Get event details |
| `officeclaw calendar create --subject <subj> --start <dt> --end <dt>` | Create event |
| `officeclaw calendar update <id> --subject <subj>` | Update event |
| `officeclaw calendar delete <id>` | Delete event |

### Tasks

| Command | Description |
|---------|-------------|
| `officeclaw tasks list-lists` | List task lists |
| `officeclaw tasks list --list-id <id>` | List tasks |
| `officeclaw tasks list --list-id <id> --status active` | Active tasks only |
| `officeclaw tasks create --list-id <id> --title <title>` | Create task |
| `officeclaw tasks complete --list-id <id> --task-id <id>` | Complete task |
| `officeclaw tasks reopen --list-id <id> --task-id <id>` | Reopen task |

## Configuration

Environment variables (or `.env` file):

| Variable | Required | Description |
|----------|----------|-------------|
| `OFFICECLAW_CLIENT_ID` | No | Azure app client ID (uses built-in default if not set) |
| `OFFICECLAW_CLIENT_SECRET` | No | Only for confidential client (auth code) flow. Not needed for device code flow. |
| `OFFICECLAW_TENANT_ID` | No | Tenant ID (default: `consumers`) |
| `OFFICECLAW_SCOPES` | No | Override default Graph API scopes |
| `OFFICECLAW_TOKEN_CACHE_DIR` | No | Token cache directory (default: `~/.officeclaw`) |
| `OFFICECLAW_ENABLE_SEND` | No | Set `true` to allow send/reply/forward emails (default: disabled) |
| `OFFICECLAW_ENABLE_DELETE` | No | Set `true` to allow deleting emails, events, tasks (default: disabled) |
| `OFFICECLAW_ALLOWED_RECIPIENTS` | No | Comma-separated list of allowed recipient email addresses. When set, outbound emails are restricted to these addresses only. Blocked attempts are logged. See [Recipient Allowlist](#recipient-allowlist) below. |

## Security & Privacy

- **Write operations disabled by default** — Send, reply, forward, and delete are all blocked unless explicitly enabled via `OFFICECLAW_ENABLE_SEND` and `OFFICECLAW_ENABLE_DELETE` environment variables. This prevents accidental or unauthorised write actions.

### Recipient Allowlist

When `OFFICECLAW_ENABLE_SEND` is enabled, you can restrict which email addresses OfficeClaw is permitted to send to by setting `OFFICECLAW_ALLOWED_RECIPIENTS`:

```bash
# .env
OFFICECLAW_ENABLE_SEND=true
OFFICECLAW_ALLOWED_RECIPIENTS=alice@example.com,bob@example.com,team@company.com
```

**Behaviour:**
- If `OFFICECLAW_ALLOWED_RECIPIENTS` is **set** — only listed addresses can receive email. Any attempt to send to an unlisted address is blocked, logged to `~/.openclaw/workspace/automation/logs/email-blocked.log`, and an alert file is written for monitoring.
- If `OFFICECLAW_ALLOWED_RECIPIENTS` is **not set** — a warning is displayed on each send reminding you to configure the allowlist. All addresses are permitted.
- The allowlist is checked **after** the `OFFICECLAW_ENABLE_SEND` gate — users who haven't enabled sending are unaffected.

This is especially important for AI agent workflows where an LLM controls email sending — the allowlist provides a hard, code-level boundary that cannot be bypassed by prompt injection or misconfiguration.
- **No client secret required** — Uses device code flow (public client) by default
- **Least-privilege permissions** — You choose which Graph API scopes to grant — read-only is sufficient for most use cases. See the setup guide above.
- **Tokens stored securely** — `~/.officeclaw/token_cache.json` with 600 file permissions
- **No data storage** — OfficeClaw passes data through, never stores email/calendar content
- **No telemetry** — No usage data collected
- **Your own Azure app** — Each user creates their own Azure app registration with their own client ID — no shared credentials

## Development

```bash
# Clone and install
git clone https://github.com/danielithomas/officeclaw.git
cd officeclaw
pip install -e ".[dev]"

# Run tests
pytest

# Lint & format
ruff check src/ tests/
black --check src/ tests/
```

## License

Apache License 2.0 — see [LICENSE](LICENSE)

## Links

- [PyPI](https://pypi.org/project/officeclaw/)
- [ClawHub](https://clawhub.ai/skills/officeclaw)
- [OpenClaw](https://docs.openclaw.ai)
- [Microsoft Graph API](https://docs.microsoft.com/graph/)

## Download History

[![Download History](https://skill-history.com/chart/danielithomas/officeclaw.svg)](https://skill-history.com/danielithomas/officeclaw)
