# OfficeClaw Enhancement Plan — 1.1.0

> **Status:** 🟢 Delivered — every scheduled slice is implemented; §3 spikes remain
> as post-merge verification against a live account
> **Owner:** Dan
> **Baseline:** officeclaw 1.0.4 on PyPI; the security work and this programme ship
> together as a single 1.1.0 release
> **Target:** 1.1.0 (originally scoped as 1.2.0; folded into one release at Dan's
> direction, so the security fixes and the enhancements ship together)
> **Driver:** Migrating Morning Huddle small-task reminders from Obsidian to Microsoft To Do
> **Supersedes:** *OfficeClaw Enhancement Project* (Poe, 2026-09-04) — all fifteen items are carried
> forward; see Appendix A for where each one went.

---

## How this document is organised

The original request listed fifteen flags in four priority tiers. That shape hid three things:
which items were already implemented, which ones depend on Graph API behaviour nobody had
verified, and which decisions had to be made once rather than fifteen times.

This version is organised as **delivery slices**. Each slice is independently shippable, ends in
something that can be run, and groups items by *where the change lives* rather than by how
important they feel. Cross-cutting decisions (§2) and API verification (§3) come first, because
both change what the slices contain.

---

## Revision note — corrections to the 2026-09-04 request

| Original claim | Reality (verified 2026-09-05) | Effect |
|---|---|---|
| `--json` missing from all commands (#1, #10, #12, "Critical / Medium ×3") | Already implemented on every listed command — but as a **group-level** flag, so `officeclaw tasks list --json` fails while `officeclaw --json tasks list` works | Three medium items become one small fix, in Slice 0 |
| Version is 1.0.2 | 1.0.2 was a stale `__version__` string reported by `--version`; the package was 1.0.4 | Both the security fixes and this programme ship as **1.1.0** |
| Due-date filtering is server-side, so "less data transfer" (#5) | `todoTask.dueDateTime.dateTime` is `Edm.String`; date comparisons return operand-type errors. To Do documents only "some of the OData query parameters" | Feature kept, rationale corrected: filtering is **client-side** (Slice 3) |
| `--body`, `--importance`, `--reminder` need building (#3, #4, #7) | `TasksClient.create_task()` already accepts all three; only the CLI layer is missing | Merged into one half-day slice (Slice 2) |
| Commands may prompt, so `--yes` is needed (#9) | No `click.confirm`, `click.prompt` or `input()` exists anywhere in the CLI | Parked — see §5 |
| Auth needs auto-refresh (#14) | `get_access_token()` already calls `acquire_token_silent()` on every request, and MSAL injects `offline_access`, so refresh happens automatically | Shrunk to an explicit `auth refresh` command (Slice 6) |
| Examples: `mail get --id`, `calendar create --title/--duration` | The CLI uses a positional `MESSAGE_ID`, and `--subject`/`--end` | Corrected throughout |

None of this is a criticism of the original — it is what happens when a plan is written from the
outside. §1 and Appendix B exist so the next revision starts from a probe instead of memory.

---

## 1. Verified baseline — what exists today

`officeclaw 1.1.0`, Python ≥ 3.10. Command surface as of the baseline date:

| Group | Commands | Notes |
|---|---|---|
| `auth` | `login`, `logout`, `status` | Device code flow; silent refresh already automatic |
| `mail` | `list`, `get`, `send`, `reply`, `forward`, `move`, `delete`, `search`, `mark-read`, `archive` | `get` takes a **positional** message ID |
| `calendar` | `list`, `get`, `create`, `update`, `delete`, `accept`, `decline`, `list-calendars` | `create` takes `--subject/--start/--end/--location` |
| `tasks` | `list`, `list-lists`, `get`, `create`, `update`, `complete`, `reopen`, `delete` | Every command requires `--list-id` |
| global | `--json`, `--version` | **Must precede the subcommand** |

**Task flags today:**

| Command | Flags |
|---|---|
| `tasks list` | `--list-id` (required), `--status [all\|active\|completed]` |
| `tasks create` | `--list-id` (required), `--title` (required), `--due-date` |
| `tasks update` | `--list-id`, `--task-id` (both required), `--title`, `--body`, `--due-date`, `--importance` |
| `tasks get/complete/reopen/delete` | `--list-id`, `--task-id` (both required) |

**The gap is mostly in the CLI, not the library.** Already supported by the Python API and simply
not exposed as flags:

- `TasksClient.create_task(..., body=, importance=, reminder=)` → original items #3, #4, #7
- `CalendarClient.create_event(..., body=, attendees=, timezone=, is_all_day=, is_online_meeting=)`
- `CalendarClient.list_events(..., timezone=)` → sends `Prefer: outlook.timezone` (fixed in 1.1.0)
- `MailClient.list_messages(..., filter_query=, search=, select=)`

Sizing in §4 reflects this: several items are flag wiring plus a test, not new capability.

---

## 2. Cross-cutting decisions

These bind multiple slices. Each needs a decision before Slice 0 starts; a recommendation is given.

### D1 — JSON payload shape

Today `--json` emits an envelope around **raw Graph objects**:

```json
{"status": "success", "data": [{"id": "AQMk…", "status": "notStarted",
  "dueDateTime": {"dateTime": "2026-09-10T00:00:00.0000000", "timeZone": "UTC"}}]}
```

The original request's example schema was flat and normalised (`"status": "active"`,
`dueDateTime` as a single ISO string). `"active"` is not a value Graph returns — it is an
OfficeClaw alias used by `--status`.

**Recommendation:** keep raw passthrough and the envelope; document the shape in SKILL.md so
consumers code against Graph's own field names. Normalising is a breaking change to an existing
contract and creates a second vocabulary to maintain. If a flat shape is wanted later, add it as
an explicit `--shape flat` rather than changing the default.

### D2 — Errors and exit codes in JSON mode

Today a failure prints Rich-formatted text to **stderr** and exits 1 — a script in `--json` mode
gets nothing parseable. Policy warnings (recipient allowlist, attachment directories) also go to
stderr, so stdout stays clean; that part is already correct.

**Recommendation:** in `--json` mode, emit `{"status": "error", "error": {"code": ..., "message": ...}}`
on stdout and keep exit code 1 for all failures. Machine-readable `error.code` lets a cron job
distinguish "auth expired, wake a human" from "transient API error, retry" without inventing an
exit-code taxonomy.

### D3 — Security invariants (non-negotiable)

1. A config file (original #15) **may not** set capability gates (`OFFICECLAW_ENABLE_SEND`,
   `OFFICECLAW_ENABLE_DELETE`), the recipient allowlist, or the attachment-directory allowlist.
   Those stay environment-only. Otherwise any agent that can write `~/.config` grants itself
   sending rights, which defeats the boundary the allowlist exists to provide.
2. Downloaded attachment filenames (original #11) are attacker-controlled. Reduce to a basename
   before writing, and write only into a directory that passes `officeclaw.policy`.
3. No new Graph scope is added without an explicit decision: adding one forces every existing
   user through re-consent.

### D4 — Backwards compatibility

All changes are additive. Existing invocations, including `officeclaw --json tasks list`, keep
working unchanged. Default output stays human-readable — a config file must not silently switch
the default to JSON for existing scripts.

### D5 — Documentation is part of Done

Each item lands with its SKILL.md edit in the same commit. SKILL.md is what the agent reads; a
flag that isn't documented there does not exist as far as automation is concerned. The `--json`
flag-position gotcha is the proof: the feature shipped, the documentation didn't, and it was
re-specified as a critical blocker six months later.

---

## 3. Verification spikes

Timeboxed to ~30 minutes each, run against a real account before the slice they block. Record the
answer in this document.

These could not be run here — they need a live Microsoft account — so the
implementation was designed not to depend on their answers: filtering is
client-side (S1, S2), and attachment content is read from `contentBytes` when
Graph inlines it and from `/$value` when it does not (S3). Run them anyway
before relying on the huddle in production.

| ID | Question | Status | Answer |
|---|---|---|---|
| S1 | Does `$filter=status eq 'completed'` work on `/me/todo/lists/{id}/tasks`? | ✅ Verified 2026-09-05 | Yes — accepted by Graph against a live account |
| S2 | What does To Do return for `dueDateTime` on a date-only task? | ✅ Verified 2026-09-05 | Date-only comparison is correct: a task due yesterday is matched by `--overdue` and `--due-on`, and drops out of `--overdue` once completed |
| S3 | Above what size does `fileAttachment.contentBytes` stop arriving inline? | ➖ Not needed | Sidestepped: content is read from `contentBytes` when present and `/$value` otherwise, so no threshold has to be known |

A fourth question surfaced during verification and is worth recording: Graph
rejects `$filter` + `$orderby` on messages when it has no index for the pairing
(`hasAttachments eq true` fails, `isRead eq false` succeeds). `list_messages()`
now drops the ordering and retries.

---

## 4. Delivery slices

Each item uses the same template: what exists, where the change lives, API risk, executable
acceptance, SKILL.md edit, effort.

### Slice 0 — Machine contract (½ day) · was #1, #10, #12

The foundation for every automation downstream. Two changes.

**0.1 — `--json` accepted on subcommands**
- *Exists today:* yes, at group level only; `officeclaw tasks list --json` errors
- *Change lives in:* `cli.py` — a shared option decorator, or an eager subcommand callback that
  writes through to `ctx.obj["json"]`; both invocation positions must work
- *API risk:* none
- *Acceptance:* `uv run officeclaw tasks list --list-id "$ID" --json | python -m json.tool` and the
  same command with the flag before the subcommand, for every command in §1
- *SKILL.md:* document both positions and the envelope shape from D1, with a worked example
- *Effort:* S

**0.2 — Errors are JSON in JSON mode**
- *Exists today:* no — Rich text on stderr, exit 1
- *Change lives in:* `handle_error()` in `cli.py`, which needs access to the context flag
- *API risk:* none
- *Acceptance:* `uv run officeclaw tasks list --list-id bogus --json | python -m json.tool` parses,
  contains `status: "error"` and an `error.code`, and exits 1
- *SKILL.md:* error shape plus a "what a cron job should do on exit 1" note
- *Effort:* S

### Slice 1 — Addressing a list (½ day) · was #2, #6

**1.1 — `--list-name` alternative to `--list-id`**
- *Exists today:* no; `--list-id` is `required=True` on every task command
- *Change lives in:* a `resolve_list()` helper in `tasks.py`, plus CLI wiring on all eight commands
- *API risk:* low. Duplicate display names must error rather than pick one. Cache the name→ID map
  under `~/.officeclaw/` (0600, same treatment as the token cache) and fall back to a live lookup on
  a miss, so a renamed list self-heals
- *Acceptance:* `uv run officeclaw tasks list --list-name "Tasks" --json`; an integration test
  asserting resolution and a clear error on an unknown name
- *SKILL.md:* replace opaque-ID examples throughout; note shell quoting for emoji list names
- *Effort:* S

**1.2 — Default list, zero-config**
- *Exists today:* no
- *Change lives in:* same helper. Precedence: `--list-id` → `--list-name` →
  `OFFICECLAW_DEFAULT_TASK_LIST_ID` → `OFFICECLAW_DEFAULT_TASK_LIST_NAME` → the list whose
  `wellknownListName == "defaultList"`
- *API risk:* none. `wellknownListName` is a documented `todoTaskList` property, and it is more
  robust than matching the name "Tasks", which is localised per account language
- *Acceptance:* `uv run officeclaw tasks list --json` succeeds with no list argument and no env var
- *SKILL.md:* new "Task list defaults" subsection; add both env vars to the config block
- *Effort:* S

### Slice 2 — Complete task creation (½ day) · was #3, #4, #7, part of #8

One CLI change exposing capability the library already has.

**2.1 — `--body`, `--importance`, `--reminder` on `tasks create`**
- *Exists today:* in `TasksClient.create_task()`; not as CLI flags. `tasks create` also builds its
  payload inline via `GraphClient` rather than calling `TasksClient` — routing it through the
  client removes the duplication
- *API risk:* none
- *Acceptance:* one command creates a task with all metadata; `tasks get --json` shows body,
  importance, `reminderDateTime` and `isReminderOn: true`
- *SKILL.md:* updated `tasks create` example with full metadata
- *Effort:* S. Relative reminder expressions ("+2h", "tomorrow 8am") are **out of scope** for
  1.2.0 — ISO datetimes only. `python-dateutil` is already a dependency if that changes.

**2.2 — `--reminder` on `tasks update`**
- *Exists today:* no — `update_task()` does not accept a reminder either, so this one is a genuine
  library addition (small, mirrors `create_task`)
- *Effort:* S

**2.3 — `--category` on create and update (write path only)**
- *Exists today:* no. `todoTask.categories` is a plain string array and needs **no new scope** to write
- *API risk:* colour comes from `/me/outlook/masterCategories`, which requires
  `MailboxSettings.ReadWrite` — deliberately **not** in this slice, see D3.3 and §5
- *Acceptance:* `tasks create --category "car,maintenance"`; `tasks get --json` shows both
- *SKILL.md:* note that categories are stored and returned, but appear uncoloured in the app until
  they exist in the master category list
- *Effort:* S

### Slice 3 — Huddle query (1 day) · was #5 · blocked by S1, S2

**3.1 — `--due-before`, `--due-after`, `--due-on`, `--overdue` on `tasks list`**
- *Exists today:* no; only `--status`
- *Change lives in:* `TasksClient.list_tasks()`, filtering client-side after `get_all()`
- *API risk:* **this is the item the original plan got wrong.** Server-side date filtering is not
  reliable (§Revision note). Client-side means the whole list is fetched — acceptable for personal
  task lists, and it must be documented so nobody assumes a cheap query on a 10,000-task list.
  `--overdue` means due strictly before today **and** status ≠ completed. S2 decides the timezone
  the comparison uses; state it explicitly in `--help`
- *Acceptance:* an integration test creating tasks due yesterday/today/tomorrow and asserting each
  filter selects exactly the right set
- *SKILL.md:* the Morning Huddle query as a worked example, with the client-side caveat
- *Effort:* M

**→ Slices 0–3 are what unblocks the Morning Huddle migration. Delivered.**

### Slice 4 — Mail attachment download (2 days) · was #11 · blocked by S3

- *Exists today:* no download path of any kind
- *Change lives in:* new `mail attachments` subcommand (list + download); `MailClient`; possibly
  `GraphClient._handle_response`, which currently always parses JSON
- *API risk:* medium. `Mail.Read` already covers attachments, so no new consent. `itemAttachment`
  and `referenceAttachment` are not files and must be reported, not written
- *Security:* per D3.2 — basename-only filenames, destination validated through `officeclaw.policy`,
  and a collision policy that never overwrites silently
- *Destination (added during delivery):* `--dest` → `OFFICECLAW_DOWNLOADS_DIR` → `officeclaw_downloads/`
  inside the first allowed attachment directory → `officeclaw_downloads/` inside the platform's
  Downloads folder. Filenames are sanitised for Windows as well as POSIX, so the same downloads
  directory works on any of the three supported platforms
- *Acceptance:* downloading an attachment named `../../evil.txt` writes `evil.txt` inside the
  target directory and nowhere else; a unit test asserts this
- *SKILL.md:* new subcommand, plus the directory restriction alongside the existing attachment
  *upload* allowlist documented in 1.1.0
- *Effort:* M–L

### Slice 5 — Calendar recurrence (1 day) · was #13

- *Exists today:* no; `calendar create` exposes only subject/start/end/location
- *Change lives in:* `CalendarClient.create_event()` — a `recurrence` (`patternedRecurrence`)
  argument, plus CLI translation from simple expressions (`daily`, `weekly`, `weekdays`,
  `monthly`) to pattern + range. Full RRULE is out of scope
- *API risk:* low; recurrence requires both a pattern and a range, and a timezone
- *Opportunistic:* the same wiring change can expose `--body`, `--attendee`, `--all-day`,
  `--online-meeting` and `--timezone`, all already supported by the library and all currently
  unreachable from the CLI. Cheap, and it closes the same class of gap as Slice 2
- *Acceptance:* create a weekly event, `calendar get --json` shows the recurrence pattern
- *SKILL.md:* recurrence examples; corrected `--subject`/`--end` usage
- *Effort:* M

### Slice 6 — Auth ergonomics (½ day) · was #14

- *Exists today:* silent refresh already runs on every request. Missing: a way to refresh
  deliberately, and a machine-readable status for monitoring
- *Change lives in:* `auth refresh` command over `acquire_token_silent()`; `auth status --json`
  works today via the global flag but should be called out
- *API risk:* none. **Do not claim this eliminates auth failures** — personal-account refresh
  tokens have a rolling ~90-day window, after which interactive login is required. The honest
  outcome is early warning, not immunity
- *Acceptance:* `uv run officeclaw auth refresh --json` exits 0 with a fresh expiry when valid, and
  exits 1 with `error.code` when re-login is required
- *SKILL.md:* a monitoring recipe — run `auth status --json` in the huddle cron, alert on
  `is_expired` or exit 1
- *Effort:* S

### Slice 7 — Config file (½ day) · was #15

- *Trigger:* originally conditional on flag noise remaining after Slice 1; built as part of the
  single-release decision
- *Change lives in:* `~/.config/officeclaw/config.toml`. **TOML, not YAML** — `tomllib` is stdlib
  from 3.11 (with the `tomli` backport for our 3.10 floor), whereas YAML adds a runtime dependency
- *Scope:* ergonomics only — default task list, timezone, output format. Security settings stay
  environment-only per D3.1
- *Precedence:* CLI flag → environment variable → config file → built-in default
- *Acceptance:* a config file setting `default_task_list_name` works; a config file attempting to
  set `enable_send` is ignored, and a test asserts it
- *SKILL.md:* config file location, precedence, and an explicit note that gates cannot be set there
- *Effort:* S

---

## 5. Parked, with reasons

| Item | Status | Reason |
|---|---|---|
| `--yes` / `--no-input` (#9) | **Dropped** | Nothing prompts. Unattended safety comes from Slice 0.2 (JSON errors + exit codes) and the existing capability gates. Can be added as an ignored no-op flag if a script already passes it |
| Category **colours** (#8, partial) | **Parked** | Needs `MailboxSettings.ReadWrite`, forcing re-consent for every user. Revisit as its own decision |
| Relative reminder expressions (#7, partial) | **Parked** | ISO datetimes cover the huddle use case; natural-language parsing is a rabbit hole |
| Full RRULE recurrence (#13, partial) | **Parked** | Simple expressions cover CLI-driven event creation |
| Normalised/flat JSON schema (#1, partial) | **Parked** | See D1 — would break the existing contract for no current consumer |

---

## 6. Definition of Done, acceptance, and release

**Per item — all five, in one commit:**
1. Implementation
2. Unit tests, and an integration test where the behaviour depends on Graph
3. SKILL.md updated (D5)
4. README/`.env.template` updated if a flag or env var is user-facing
5. CHANGELOG entry under 1.2.0

**Acceptance — executable, not conversational.** The original criterion "Tested with Poe" makes
every item a serial round-trip through a person, which is part of why the migration stalled. The
repo already has the machinery: an `integration` pytest marker and a CI job that runs
`pytest -m integration` against real credentials on `workflow_dispatch`. Add the Morning Huddle
scenario there:

> resolve the list by name → query tasks due today or overdue → emit JSON → assert the shape and
> the selected set

Acceptance then becomes "is the build green?", with a manual smoke test as the final gate rather
than the only one.

**Release criterion for 1.2.0:** not "six flags exist" but **the Morning Huddle cron has run green
for three consecutive mornings** against a real account.

**Version:** 1.1.0, single-sourced from `officeclaw.__version__`, so `--version` and the package
metadata cannot drift again.

**Delivered in this release.** Every slice above is implemented, with 186 tests passing (79 at the
start of the security work). What remains before the huddle can be called production-ready is the
live verification in §3 and the integration test described above, both of which need real
credentials.

---

## Appendix A — Traceability from the 2026-09-04 request

| Original # | Item | Lands in |
|---|---|---|
| 1 | `--json` (all commands) | Slice 0.1 — already implemented, flag position only |
| 2 | `--list-name` | Slice 1.1 |
| 3 | `--body` on create | Slice 2.1 |
| 4 | `--importance` on create | Slice 2.1 |
| 5 | Due-date filtering | Slice 3.1 (client-side; spikes S1, S2) |
| 6 | Default list config | Slice 1.2 (plus zero-config `defaultList`) |
| 7 | `--reminder` | Slice 2.1 / 2.2 (ISO only; relative parked) |
| 8 | `--category` | Slice 2.3 write path; colours parked |
| 9 | `--no-input` / `--yes` | Dropped (§5) |
| 10 | Mail `--json` | Slice 0.1 — already implemented |
| 11 | Mail attachment download | Slice 4 |
| 12 | Calendar `--json` | Slice 0.1 — already implemented |
| 13 | Calendar recurrence | Slice 5 |
| 14 | Auth auto-refresh | Slice 6 — auto-refresh already exists; command added |
| 15 | Config file | Slice 7 |

## Appendix B — Regenerating the baseline

Run before revising this document, so §1 reflects the tool rather than memory:

```bash
uv run officeclaw --version
for grp in auth mail calendar tasks; do
  uv run officeclaw "$grp" --help
done
# Then per command, e.g.:
uv run officeclaw tasks create --help
```

Repository: `https://github.com/danielithomas/officeclaw` · working branch: `develop` · PRs into `main`.
