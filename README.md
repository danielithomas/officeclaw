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

Requires Python 3.10 or newer.

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
officeclaw mail search "from:boss@example.com"

# List attachments for a message
officeclaw mail attachments AQMkADEzN...

# Download an attachment
officeclaw mail download AQMkADEzN... report.pdf

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
| `officeclaw mail search <query>` | Search emails |
| `officeclaw mail archive <id>` | Archive a message |
| `officeclaw mail mark-read <id>` | Mark as read |
| `officeclaw mail attachments <message-id>` | List attachments for a message |
| `officeclaw mail download <message-id> <attachment-name>` | Download an attachment |

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
| `OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD` | No | Set `true` to allow downloading email attachments (default: disabled) |
| `OFFICECLAW_SAFE_SENDERS_ONLY` | No | Set `true` to restrict downloads to allowed senders only (default: disabled) |
| `OFFICECLAW_SAFE_SENDERS_LIST` | No | Comma-separated list of allowed sender addresses. Supports domain wildcards (`@example.com`) |
| `OFFICECLAW_ATTACHMENT_MAX_SIZE_MB` | No | Maximum attachment size in MB (default: 25) |
| `OFFICECLAW_ATTACHMENT_ALLOWED_TYPES` | No | Comma-separated MIME type allowlist. Use `*` to allow all (default) |
| `OFFICECLAW_ALLOWED_ATTACHMENT_DIRS` | No | Comma-separated list of directories attachments may be read from and downloaded to. See [Attachment Directories](#attachment-directories) below. |
| `OFFICECLAW_DOWNLOADS_DIR` | No | Where downloads are saved when no path is given. See [Attachment Directories](#attachment-directories) |
| `OFFICECLAW_DEFAULT_TASK_LIST_NAME` | No | Task list used when a command is given neither `--list-id` nor `--list-name` |
| `OFFICECLAW_DEFAULT_TASK_LIST_ID` | No | As above, by ID; takes precedence over the name |
| `OFFICECLAW_TIMEZONE` | No | Timezone used to decide what "today" means for `tasks list --overdue` (default: system timezone) |
| `OFFICECLAW_CONFIG` | No | Config file location (default: `~/.config/officeclaw/config.toml`) |

### Working With Tasks

Task commands take `--list-name` instead of an opaque ID, and fall back to your built-in **Tasks** list when given neither:

```bash
officeclaw tasks list                                  # Default list
officeclaw tasks list --list-name "🛒 Groceries"
officeclaw tasks list --overdue --json                 # Everything late, machine-readable

officeclaw tasks create \
  --title "Call accountant" \
  --body "Ask about GST registration" \
  --due-date 2026-09-15 --importance high \
  --reminder "2026-09-15T08:00:00" \
  --category "finance,admin"
```

Due-date filters (`--due-before`, `--due-after`, `--due-on`, `--overdue`) are applied **client-side**: Microsoft To Do cannot filter on due dates server-side, so the list is fetched and filtered locally. Dates are compared by calendar date, since To Do drops the time portion of a due date.

`--overdue` means "due before today **where you are**". A To Do due date has no timezone, so comparing it against UTC would be wrong for hours every day east of Greenwich — at 9am in Melbourne it is still yesterday in UTC. Set `OFFICECLAW_TIMEZONE` (or `timezone` in the config file) to pin the zone; otherwise the system timezone is used.

### JSON Output

`--json` works before or after the subcommand, and covers failures as well as successes:

```bash
officeclaw tasks list --overdue --json     # {"status": "success", "data": [...]}
officeclaw auth refresh --json             # exits 1 if an interactive login is needed
```

Objects inside `data` are Microsoft Graph objects passed through unchanged. Errors return `{"status": "error", "error": {"code": ..., "message": ...}}` with exit status 1, so scripts can branch on `error.code`.

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
- Every outbound path is covered: `mail send` (including cc and bcc), `mail forward`, `mail reply`/`--reply-all`, and the Python API. Reply-all resolves the thread's real recipients before sending, so a single outside address on the thread blocks the reply.

This is especially important for AI agent workflows where an LLM controls email sending — the allowlist provides a hard, code-level boundary that cannot be bypassed by prompt injection or misconfiguration.

### Attachment Download Security

When `OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD` is enabled, additional security controls protect against malicious attachments:

| Setting | Default | Purpose |
|---------|---------|---------|
| `OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD` | `false` | Master switch — disabled by default |
| `OFFICECLAW_SAFE_SENDERS_ONLY` | `false` | If `true`, only downloads from allowed senders |
| `OFFICECLAW_SAFE_SENDERS_LIST` | `[]` | Allowed sender emails. Supports exact match (`user@example.com`) or domain wildcards (`@example.com`) |
| `OFFICECLAW_ATTACHMENT_MAX_SIZE_MB` | `25` | Maximum file size. Fails fast on oversized attachments |
| `OFFICECLAW_ATTACHMENT_ALLOWED_TYPES` | `*` | MIME type allowlist. E.g.: `text/plain,image/png,application/pdf` |
| `OFFICECLAW_DOWNLOADS_DIR` | platform Downloads folder | Where files are saved when no path is given (was `OFFICECLAW_ATTACHMENT_DOWNLOAD_PATH` in 1.0.5, still honoured with a warning) |
| `OFFICECLAW_ALLOWED_ATTACHMENT_DIRS` | unrestricted | Directories downloads may be written to, and attachments read from |

**Example — Restricted environment:**

```bash
# .env
OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD=true
OFFICECLAW_SAFE_SENDERS_ONLY=true
OFFICECLAW_SAFE_SENDERS_LIST="danielithomas@hotmail.com,dan@theenquiringmind.com,@focalleap.com"
OFFICECLAW_ATTACHMENT_MAX_SIZE_MB=10
OFFICECLAW_ATTACHMENT_ALLOWED_TYPES="text/plain,text/markdown,image/svg+xml,image/png,image/jpeg,application/pdf"
```

**Safe sender matching logic:**
- Exact email: `sender@example.com`
- Domain wildcard: `@theenquiringmind.com` matches any address from that domain
- Display name is **never** used for matching (spoofable)

**Output file handling:**
- Path traversal is blocked (`../`, `~/.bashrc`)
- Download directory is auto-created if missing
- Filename collisions auto-resolved: `file.pdf` → `file (1).pdf`
- Filenames are also made legal on Windows and macOS, not just Linux

### Attachment Directories

`mail send --attachment` will read any file the process can read, so an agent that can be talked into sending mail can also be talked into attaching `~/.ssh/id_rsa`. `OFFICECLAW_ALLOWED_ATTACHMENT_DIRS` limits where attachments may come from — and, for `mail attachments download`, where they may be written to:

```bash
# .env
OFFICECLAW_ALLOWED_ATTACHMENT_DIRS=~/.openclaw/workspace/wip
```

**Behaviour:**
- If **set** — only files inside those directories (at any depth) can be attached. Symlinks are resolved before the check, so a link inside an allowed directory cannot reach outside it. Blocked attempts are logged alongside blocked sends.
- If **not set** — a warning is displayed whenever a send carries an attachment. Any readable file may be attached.
- Downloads are covered by the same list. Filenames from incoming mail are reduced to a bare name before writing, so a message cannot steer a write with a name like `../../.ssh/authorized_keys`, and an existing file is never overwritten.

**Where downloads go.** `mail download-all` writes to `--dest` if given (and `mail download` to its optional path argument), otherwise:

1. `OFFICECLAW_DOWNLOADS_DIR`, used exactly as set;
2. `officeclaw_downloads/` inside the **first** allowed attachment directory, when an allowlist is configured — so the default is inside your boundary rather than failing the check;
3. `officeclaw_downloads/` inside your platform's Downloads folder otherwise — `~/Downloads` on macOS, the XDG download directory on Linux (so a localised folder name is honoured), and the Downloads known folder on Windows (looked up rather than assumed, since it can be relocated).

Saved filenames are made portable across all three platforms: characters Windows forbids are dropped, trailing dots and spaces trimmed, and reserved device names such as `CON` prefixed — so a downloads directory synced between machines stays usable.

The recommended pattern is a dedicated working directory — `~/.openclaw/workspace/wip` — that you copy files into when you want them sent. It is not a sandbox: anything the agent can write to that directory it can also mail out. What it buys you is that reading a sensitive file is no longer enough; the file has to be moved somewhere deliberate first.
- **No client secret required** — Uses device code flow (public client) by default
- **Least-privilege permissions** — You choose which Graph API scopes to grant — read-only is sufficient for most use cases. See the setup guide above.
- **Tokens stored securely** — `~/.officeclaw/token_cache.json`, created with 600 permissions (never written world-readable, even briefly)
- **No data storage** — OfficeClaw passes data through, never stores email/calendar content
- **No telemetry** — No usage data collected
- **Your own Azure app** — Each user creates their own Azure app registration with their own client ID — no shared credentials

### Where Settings Come From

Two sources configure OfficeClaw: the process environment (which a supervising process such as the OpenClaw gateway daemon can inject into) and the `.env` file, located from your working directory.

For ordinary settings **`.env` wins** — if you edit it, it takes effect.

For security settings the two **compose to the stricter value**, so neither source can widen what the other permits:

| Setting type | Rule | Example |
|---|---|---|
| Allowlists (`ALLOWED_RECIPIENTS`, `ALLOWED_ATTACHMENT_DIRS`, `SAFE_SENDERS_LIST`, `ATTACHMENT_ALLOWED_TYPES`) | intersection | env allows 2 addresses, `.env` lists 3 → the 2 in common |
| Capability gates (`ENABLE_SEND`, `ENABLE_DELETE`, `ENABLE_ATTACHMENT_DOWNLOAD`) | both must enable | env `false` + `.env` `true` → disabled |
| Restriction toggles (`SAFE_SENDERS_ONLY`) | either can enable | env `true` + `.env` `false` → enforced |
| Ceilings (`ATTACHMENT_MAX_SIZE_MB`) | lower wins | env `10` + `.env` `100` → 10 |

A value that does not take effect is **reported with a warning** naming it, so a setting is never silently ignored. If an address in your `.env` is being dropped, the injected environment is the place to add it.

### Configuration File

Persistent preferences can live in `~/.config/officeclaw/config.toml` (override the path with `OFFICECLAW_CONFIG`):

```toml
default_task_list_name = "Tasks"
default_output = "json"
timezone = "Australia/Melbourne"
```

Precedence is **command-line flag → environment variable → config file → built-in default**.

Security settings are deliberately not readable from this file. `enable_send`, `enable_delete`, `allowed_recipients`, `allowed_attachment_dirs`, `client_id` and `client_secret` are ignored (with a warning) if they appear there, and must come from the environment — otherwise anything able to write a file in your config directory could grant itself the ability to send mail.

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
