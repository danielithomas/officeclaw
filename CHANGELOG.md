# Changelog

All notable changes to OfficeClaw are documented here.

## [1.1.1] — 2026-09-06

### Security

- **Calendar attendees are now checked against the recipient allowlist.** 1.1.0
  added `calendar create --attendee` without it, and Graph emails an invitation
  to every attendee — so an agent blocked from mailing an address could invite
  it instead. The check now lives in `CalendarClient`, covering the Python API
  as well as the CLI, and blocked invitations are logged like blocked sends
  (`action=calendar-invite`). Raised in PR #8 by danbryant201.

### Added

- `calendar update --attendee` — replace an event's attendees, subject to the
  same allowlist (PR #8, danbryant201).
- **Repeating tasks:** `tasks create --repeat` and `tasks update --repeat` /
  `--no-repeat`, accepting `daily`, `daily:3`, `weekly`, `weekly:MON,WED`,
  `fortnightly`, `weekdays`, `monthly`, `monthly:15` and `yearly` (PR #9,
  danbryant201). The shorthand now backs `calendar create --recurrence` too, so
  both commands share one syntax and one parser (`officeclaw.recurrence`).
- **Task steps:** `tasks steps list|add|complete|delete` for checklist items
  within a task (PR #9, danbryant201).
- `tasks update --no-reminder` as a clearer way to remove a reminder than the
  previous `--reminder ""` (PR #9, danbryant201).

### Fixed

- **OpenClaw skill manifest**, which the 1.1.0 sdist shipped with stale
  metadata: it advertised `version: "1.0.4"` and `Requires Python 3.9+`. The
  Python claim was the consequential one — 1.1.0 requires 3.10, so a host
  trusting the manifest could install the skill where it cannot run. The
  installation section now pins `officeclaw>=1.1.0` and lists the commands that
  need it.
- `docs/ARCHITECTURE.md` still showed `requires-python = ">=3.9"` and a Python
  3.9 CI matrix.
- Documented `mail search --query` — the argument is positional, so the example
  as written failed.

### Notes

- `tests/test_version_consistency.py` now fails the build if the skill manifest,
  README, classifiers, CI matrix or ARCHITECTURE drift from `__version__` and
  `requires-python`; `CLAUDE.md` carries the matching release checklist.
- PR #9's `--add-to-my-day` is **not** included: Microsoft Graph has no My Day
  property, and the flag set `startDateTime`, which is a different thing. The
  underlying capability may return later under an honest name.

## [1.1.0] — 2026-09-05

This release combines the security fixes from the 1.1.0 audit with the
enhancement programme described in `docs/ENHANCEMENT-PLAN-1.1.0.md`, and merges
the unreleased 1.0.5 attachment work from `develop`.

### Added

- **`--json` on subcommands.** The flag previously worked only before the
  subcommand (`officeclaw --json tasks list`); `officeclaw tasks list --json`
  now works too, on every command.
- **JSON errors.** In JSON mode a failure returns
  `{"status": "error", "error": {"code": ..., "message": ...}}` on stdout with
  exit status 1, so scripts can branch on `error.code` instead of parsing prose.
- **`--list-name` on every task command**, as an alternative to the opaque list
  ID. Names resolve case-insensitively; an ambiguous name is refused rather than
  guessed at. Resolved names are cached in `~/.officeclaw/list_cache.json`.
- **Default task list.** With neither `--list-id` nor `--list-name`, commands use
  `OFFICECLAW_DEFAULT_TASK_LIST_ID`/`_NAME`, or the account's built-in Tasks list
  (identified by `wellknownListName`, which survives localisation).
- **`tasks create` metadata:** `--body`, `--importance`, `--reminder` and
  `--category`, so a task no longer needs a second command to be complete.
  `tasks update` gains `--reminder` (empty string clears it) and `--category`.
- **Due-date filters on `tasks list`:** `--due-before`, `--due-after`, `--due-on`,
  `--overdue`, plus `--limit`. Applied client-side — Microsoft To Do cannot filter
  on due dates server-side — and compared by calendar date, since To Do drops the
  time portion of a due date.
- **`mail attachments list` and `mail attachments download`.** Filenames from
  incoming mail are reduced to a bare name before writing, existing files are
  never overwritten, and the destination is subject to
  `OFFICECLAW_ALLOWED_ATTACHMENT_DIRS`. Item and reference attachments are
  reported as skipped rather than silently dropped.
- **`mail download-all`** — bulk download, applying the same capability gate,
  sender allowlist and size/type limits as `mail download` (1.0.5), plus a
  destination confined to `OFFICECLAW_ALLOWED_ATTACHMENT_DIRS`.
- `OFFICECLAW_ATTACHMENT_DOWNLOAD_PATH` (1.0.5) is still honoured as a
  deprecated alias for `OFFICECLAW_DOWNLOADS_DIR`, so an existing `.env` keeps
  working instead of silently sending downloads elsewhere.
- **`OFFICECLAW_DOWNLOADS_DIR`** and a sensible default destination: with no
  `--dest`, downloads go to that variable if set, else `officeclaw_downloads/`
  inside the first allowed attachment directory, else inside the platform's
  Downloads folder (`~/Downloads` on macOS, the XDG download directory on
  Linux, the Downloads known folder on Windows). Saved filenames are made legal
  on all three platforms — forbidden characters dropped, trailing dots and
  spaces trimmed, reserved device names such as `CON` prefixed.
- Config file is also looked for in the platform's own config directory
  (`%LOCALAPPDATA%` on Windows, `~/Library/Application Support` on macOS) when
  `~/.config/officeclaw/config.toml` is absent.
- **Recurring events:** `calendar create --recurrence
  [daily|weekly|fortnightly|weekdays|monthly|yearly]` with
  `--recurrence-until` or `--recurrence-count`.
- **`calendar create` flags the library already supported:** `--body`,
  `--attendee`, `--timezone`, `--all-day`, `--online-meeting`; and
  `calendar list --timezone`.
- **`auth refresh`** — refresh the token without an interactive login, exiting 1
  when one is required, so a scheduled job can detect it early.
- **`OFFICECLAW_TIMEZONE`** (and `timezone` in the config file) — the zone used
  to decide what "today" means for `--overdue`.
- **Config file** at `~/.config/officeclaw/config.toml` (TOML, override with
  `OFFICECLAW_CONFIG`) for `default_task_list_name`, `default_task_list_id`,
  `default_output` and `timezone`. Precedence: flag → environment → file →
  default. Capability gates, allowlists and credentials are **ignored** if
  placed there, and must come from the environment.
- `GraphClient.get_binary()` for endpoints that return bytes rather than JSON.

### Changed — .env precedence

`load_dotenv(override=True)` (1.0.5, develop) made `.env` override the process
environment for *every* setting, including security ones — so a file in the
working directory could widen an allowlist that the OpenClaw gateway daemon had
deliberately narrowed, or enable a capability the daemon disabled.

Loading now composes the two sources instead of picking a winner
(`officeclaw.env`): ordinary settings still come from `.env`, so an edited file
is never silently ignored, while security settings resolve to the **stricter**
of the two — allowlists intersect, capability gates must be enabled in both,
restriction toggles apply if either sets them, and size ceilings take the lower
value. Any entry that does not take effect is reported with a warning naming it,
which is what the original silent-ignore bug lacked.

`.env` is now also located from the working directory (`usecwd=True`); before,
python-dotenv searched from the package's own location, so an installed
OfficeClaw could miss the user's file entirely.

### Security
- **Recipient allowlist now covers every send path.** `OFFICECLAW_ALLOWED_RECIPIENTS` was only enforced by `mail send`; `mail forward`, `mail reply --reply-all` and the Python API (`MailClient.send_message`, including cc and bcc) could all reach unlisted addresses. The check moved into a new `officeclaw.policy` module that all of them share. Reply and reply-all resolve the thread's real recipients before sending.
- **Attachment directory allowlist** (`OFFICECLAW_ALLOWED_ATTACHMENT_DIRS`) — `mail send --attachment` would read any file the process could read. When set, attachments must come from a configured directory; symlinks are resolved before the check. A warning is shown when an attachment is sent with no allowlist configured.
- **Token files are created with 0600** instead of being written and then chmod-ed, closing the window where another local user could read them. A pre-existing `~/.officeclaw` is tightened to 0700.
- **OAuth callback server binds to 127.0.0.1** (was all interfaces, which accepted the authorization code from anyone on the network) and no longer inherits `SimpleHTTPRequestHandler`, whose un-overridden methods served the working directory.
- **CSRF `state` parameter** added to the authorization code flow, compared with a constant-time check on callback.
- **Callback error page escapes** the `error_description` it echoes back.
- **CI security audit actually runs.** `pip-audit` was invoked with `|| true` *and* `continue-on-error`, and without the project installed, so it audited nothing and never failed. It now installs the project and fails the build. `trufflehog` is pinned to a commit SHA instead of `@main`, and `mypy` is no longer `continue-on-error`.

### Changed
- **Requires Python 3.10+** (was 3.9). Patched releases of `requests`, `urllib3`, `click` and `python-dotenv` all require 3.10, so on 3.9 the resolver was pinned to versions with published advisories. Python 3.9 reached end of life in October 2025.
- **Dependency floors raised to patched releases**: `requests>=2.33.0`, `click>=8.3.3`, `python-dotenv>=1.2.2`, `msal>=1.34.0`, `keyring>=25.7.0`, `python-dateutil>=2.9.0`, `rich>=14.0.0`; dev: `pytest>=9.0.3`, `black>=26.3.1`, `pip-audit>=2.10.1`. `uv.lock` refreshed — `pip-audit` reports no known vulnerabilities.
- Tokens stored under the pre-rename keyring services (`outclaw`, `out-claw`) are found and migrated again; the rename to `officeclaw` had collapsed both names, silently breaking the migration. Logout clears them too.
- Package version is now single-sourced from `officeclaw.__version__`, so `officeclaw --version` and the package metadata cannot disagree.
- Coverage gate raised from 40% to 50%.

### Fixed
- `officeclaw --version` reported 1.0.2 while the package was 1.0.4.
- `CalendarClient.list_events(timezone=...)` was silently ignored; it now sends the `Prefer: outlook.timezone` header. `GraphClient.get_all`/`get_paginated` accept headers to make this possible.
- `MailClient.list_messages(search=...)` sent `$search` together with `$orderby`, which Graph rejects with a 400. Ordering is now dropped for searches.
- `Retry-After` headers in HTTP-date form raised `ValueError` while handling a 429; both forms are accepted.
- `TasksClient.list_tasks(status=...)` interpolated the status straight into an OData `$filter`. Unknown values now raise `ValueError`.
- `GraphClient` no longer reaches into `TokenManager._cached_tokens` (which does not exist in public client mode, making the post-401 retry a no-op there); `TokenManager.invalidate_cache()` replaces it.
- A corrupt token cache is reported instead of silently reading as "not authenticated".
- `TasksClient` was listed twice in `officeclaw.__all__`.
- All 23 outstanding mypy errors resolved; `mypy src/officeclaw/` is clean and enforced in CI.
## [1.0.5] — 2026-05-06

### Added
- **Attachment Download Support** — securely download email attachments via Microsoft Graph API.
  - New commands: `officeclaw mail attachments <message_id>` and `officeclaw mail download <message_id> <attachment_name>`.
  - Security-first design: disabled by default (`OFFICECLAW_ENABLE_ATTACHMENT_DOWNLOAD`), optional sender allowlist (`OFFICECLAW_SAFE_SENDERS_LIST`), MIME type filtering, and size limits.
  - Domain wildcard support in safe senders list (`@example.com`).
  - Path sanitisation and filename collision handling.
  - New exceptions: `AttachmentSecurityError`, `AttachmentSizeError`, `AttachmentTypeError`.

## [1.0.4] — 2026-04-04

### Added
- **Recipient Allowlist** (`OFFICECLAW_ALLOWED_RECIPIENTS`) — restrict outbound email to a configurable list of allowed addresses. Blocked attempts are logged and trigger alerts. Critical for AI agent workflows where LLMs control email sending.
- **Runtime warning** when `OFFICECLAW_ENABLE_SEND` is enabled but no recipient allowlist is configured.
- **Blocked email logging** — unauthorized send attempts are written to `email-blocked.log` and an `email-alert.json` file for monitoring integration.

## [1.0.3] — 2026-04-01

### Added
- `--html` flag on `mail send` for sending HTML-formatted email bodies (content type `text/html`).
- Capability gates now load `.env` file before checking environment variables.

## [1.0.2] — 2026-03-16

### Added
- Initial public release on PyPI.
- Email operations: list, get, search, send, reply, forward, archive, move, delete, mark-read.
- Calendar operations: list events, create, update, delete.
- Task operations: list, create, complete.
- Device code OAuth flow (no client secret required).
- Write operations disabled by default (`OFFICECLAW_ENABLE_SEND`, `OFFICECLAW_ENABLE_DELETE`).
- JSON output mode (`--json`).
- OpenClaw skill integration.
