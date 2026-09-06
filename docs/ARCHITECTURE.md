# OfficeClaw Architecture

## Package Structure

```
officeclaw/
├── pyproject.toml          # Package configuration (PEP 621)
├── src/
│   └── officeclaw/
│       ├── __init__.py     # Package entry, version, lazy imports
│       ├── __main__.py     # `python -m officeclaw` support
│       ├── cli.py          # Click-based CLI
│       ├── exceptions.py   # Custom exception classes
│       ├── auth.py         # OAuth authentication & token management
│       ├── auth_flow.py    # Auth code flow (legacy fallback)
│       ├── client.py       # Base Graph API client
│       ├── mail.py         # Mail operations
│       ├── calendar.py     # Calendar operations
│       └── tasks.py        # Task operations
├── skill/
│   └── SKILL.md            # OpenClaw skill manifest
├── tests/
│   ├── conftest.py         # Fixtures and mocks
│   ├── test_cli.py         # CLI tests
│   ├── test_auth.py        # Auth tests
│   └── ...
├── docs/
│   ├── ARCHITECTURE.md     # This file
│   └── logo.png            # OfficeClaw logo
└── .github/workflows/
    ├── test.yml            # CI testing
    └── publish.yml         # PyPI publishing on v* tags
```

---

## Python Packaging (pyproject.toml)

### Why pyproject.toml?

- **PEP 621 compliant**: Modern Python standard
- **Single source of truth**: Dependencies, metadata, tools all in one file
- **Tool configurations**: pytest, ruff, black, mypy settings included
- **Build isolation**: Uses hatchling for reliable builds

### Key Sections

```toml
[project]
name = "officeclaw"
dynamic = ["version"]        # Read from officeclaw.__version__ by hatchling
requires-python = ">=3.10"

[project.scripts]
officeclaw = "officeclaw.cli:main"  # Creates `officeclaw` command

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["-v", "--cov=src/officeclaw"]
```

### CLI Entry Point

The `[project.scripts]` section creates the `officeclaw` command:

```bash
# After pip install
officeclaw --help
officeclaw mail list
officeclaw calendar list --start 2026-02-01
```

---

## Authentication Model

### Dual Auth Mode

OfficeClaw supports two authentication modes:

| Aspect | Device Code Flow (Default) | Auth Code Flow (Legacy) |
|--------|---------------------------|------------------------|
| Client Secret | Not required | Required |
| Browser | User opens manually | Opens automatically |
| Headless | ✅ Works via SSH | ❌ Needs display |
| Azure Setup | Simpler | Complex |
| Activation | Default (no secret set) | Set `OFFICECLAW_CLIENT_SECRET` |

### Default: Device Code Flow

```
┌─────────────────────────────────────────────────────────────┐
│  User runs: officeclaw auth login                           │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  CLI requests device code from Microsoft                    │
│  POST https://login.microsoftonline.com/.../devicecode      │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Microsoft returns:                                          │
│  - device_code: "ABC123..."                                  │
│  - user_code: "ABCD-1234"                                    │
│  - verification_uri: "https://microsoft.com/devicelogin"    │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  CLI displays to user:                                       │
│  "Visit https://microsoft.com/devicelogin                    │
│   and enter code: ABCD-1234"                                 │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
        ┌───────────────────┴───────────────────┐
        ↓                                       ↓
┌───────────────────┐               ┌───────────────────────┐
│ User opens browser │               │ CLI polls Microsoft   │
│ Enters code        │               │ every 5 seconds       │
│ Approves consent   │               │ Waiting for approval  │
└───────────────────┘               └───────────────────────┘
        │                                       │
        └───────────────┬───────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  Microsoft returns tokens to CLI                             │
│  - access_token                                              │
│  - refresh_token                                             │
└─────────────────────────────────────────────────────────────┘
```

### Default Client ID

OfficeClaw ships with a built-in public client ID (`1db8c9bb-eebf-4eb9-82dc-e3ec91d1ca53`) so users can authenticate immediately without creating their own Azure app registration. Users can override this by setting `OFFICECLAW_CLIENT_ID` in their `.env`.

### MSAL Implementation

```python
from msal import PublicClientApplication

app = PublicClientApplication(client_id)

# Initiate device code flow
flow = app.initiate_device_flow(scopes=["Mail.Read", ...])

print(f"Visit {flow['verification_uri']} and enter: {flow['user_code']}")

# Poll for completion (blocks until user approves or timeout)
result = app.acquire_token_by_device_flow(flow)

# Result contains access_token, refresh_token, etc.
```

---

## Capability Gates

Write operations are disabled by default for safety:

| Gate | Env Var | Commands Protected |
|------|---------|-------------------|
| Send | `OFFICECLAW_ENABLE_SEND=true` | `mail send`, `mail reply`, `mail forward` |
| Delete | `OFFICECLAW_ENABLE_DELETE=true` | `mail delete`, `calendar delete`, `tasks delete` |

Read operations (list, get, search) are always available. This ensures a compromised agent cannot send emails or delete data unless explicitly enabled.

## Outbound Policy

Beyond the gates, two opt-in allowlists constrain what may leave the mailbox. Both live in `officeclaw/policy.py` so the CLI and the Python API enforce them identically, and both log blocked attempts to `~/.openclaw/workspace/automation/logs/`.

| Control | Env Var | Applies To |
|---------|---------|------------|
| Recipients | `OFFICECLAW_ALLOWED_RECIPIENTS` | `mail send` (to/cc/bcc), `mail reply`, `mail forward`, `MailClient` |
| Attachments | `OFFICECLAW_ALLOWED_ATTACHMENT_DIRS` | `mail send --attachment` |

Reply and reply-all resolve the thread's actual recipients (`replyTo`/`from`/`to`/`cc`, minus the mailbox owner) before sending, since Graph would otherwise choose them server-side, out of reach of the check.

The attachment allowlist governs both directions: files may only be attached from those directories, and `mail attachments download` may only write into them. Names from incoming mail are reduced to a bare filename before writing, and sanitised for every platform (Windows-forbidden characters, trailing dots and spaces, reserved device names), so a shared downloads directory stays usable across machines.

Download destination resolves as: `--dest` → `OFFICECLAW_DOWNLOADS_DIR` → `officeclaw_downloads/` inside the first allowed attachment directory → `officeclaw_downloads/` inside the platform's Downloads folder. Choosing the allowlisted directory when one is configured keeps the default inside the boundary by construction, rather than defaulting to a location the allowlist would then reject.

## Cross-Platform Notes

The package supports Linux, macOS and Windows. Points where they differ:

| Concern | Handling |
|---|---|
| Downloads and config locations | `platformdirs`, so a relocated Windows Downloads folder or a localised XDG directory is found rather than assumed |
| File permissions | `os.fchmod` is POSIX-only and is called only where present; on Windows token files inherit the user profile's ACL |
| Filenames from email | Sanitised to the intersection of what all three platforms accept |
| Config file | `~/.config/officeclaw/config.toml` on any platform, plus the platform config directory (`%LOCALAPPDATA%`, `~/Library/Application Support`) when that is where the user put it |

## Configuration Precedence

`officeclaw.env` loads `.env` (found from the working directory). Ordinary settings are taken from the file; security settings compose with the process environment to the stricter value — intersection for allowlists, AND for capability gates, OR for restriction toggles, minimum for ceilings — so neither a supervising daemon nor a local file can widen what the other permits. Disagreements are warned about rather than resolved silently.


Settings resolve in this order, first match winning:

1. Command-line flag
2. Environment variable (including `.env`)
3. `~/.config/officeclaw/config.toml` (`OFFICECLAW_CONFIG` overrides the path)
4. Built-in default

`officeclaw/config.py` refuses to read security settings from the file — capability gates, both allowlists, and credentials come from the environment alone. A process able to write the user's config directory therefore cannot grant itself send rights.

## Task List Resolution

`TasksClient.resolve_list_id()` is the single entry point: explicit `--list-id`, then `--list-name`, then `OFFICECLAW_DEFAULT_TASK_LIST_ID`/`_NAME`, then the list whose `wellknownListName` is `defaultList`. Name lookups are cached in `~/.officeclaw/list_cache.json` (0600) and fall back to a live lookup on a miss, so renaming a list in To Do self-heals.

Due-date filtering happens client-side: `todoTask.dueDateTime.dateTime` is an `Edm.String`, so Graph rejects date comparisons against it.

---

## CI/CD Pipeline

### test.yml - Continuous Integration

**Triggers:**
- Push to `main` or `develop`
- Pull requests to `main`

**Jobs:**

1. **Lint & Format**
   - Black (formatting)
   - Ruff (linting)
   - Mypy (type checking)

2. **Security Audit**
   - pip-audit (dependency vulnerabilities)
   - Bandit (code security)
   - TruffleHog (secret scanning)

3. **Test Matrix**
   - Python 3.10, 3.11, 3.12, 3.13
   - pytest with coverage
   - Upload to Codecov

4. **Build Verification**
   - Build wheel and sdist
   - Verify with twine

### publish.yml - Release Publishing

**Triggers:**
- Push tag matching `v*` (e.g. `v1.0.2`)
- Manual dispatch (for testing)

**Flow:**
```
Build → PyPI (via Trusted Publishing) → Verify Installation
```

Uses **Trusted Publishing** (no API tokens needed):
- PyPI verifies GitHub Actions identity
- More secure than storing tokens

---

## Unit Testing Strategy

### Testing Principles

1. **Mock external dependencies**: Never call real APIs in unit tests
2. **Test behavior, not implementation**: Focus on inputs/outputs
3. **Use fixtures**: Consistent test data
4. **Fast by default**: Integration tests are opt-in

### Test Organization

```
tests/
├── conftest.py           # Shared fixtures
│   ├── mock_graph_api    # responses library mock
│   ├── mock_keyring      # Keyring mock
│   ├── sample_*          # Sample data fixtures
├── test_cli.py           # CLI command tests (incl. capability gates)
├── test_auth.py          # Token management tests
├── test_mail.py          # Mail client tests
├── test_calendar.py      # Calendar client tests
└── test_tasks.py         # Tasks client tests
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src/officeclaw --cov-report=html

# Specific test file
pytest tests/test_cli.py

# Skip slow/integration tests
pytest -m "not slow and not integration"

# Only integration tests (requires real credentials)
OFFICECLAW_CLIENT_ID=... pytest -m integration
```

---

## Security Model

### Token Storage

```
┌─────────────────────────────────────────┐
│           Token Storage                  │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │  Primary: MSAL Token Cache        │  │
│  │  - Location: ~/.officeclaw/       │  │
│  │  - File: token_cache.json         │  │
│  │  - Permissions: 600               │  │
│  │  ✅ Serialized by MSAL            │  │
│  └───────────────────────────────────┘  │
│                  │                       │
│                  ↓ (legacy fallback)     │
│  ┌───────────────────────────────────┐  │
│  │  System Keyring                   │  │
│  │  - macOS: Keychain                │  │
│  │  - Windows: Credential Manager    │  │
│  │  - Linux: Secret Service          │  │
│  │  ✅ Encrypted at rest             │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### Credential Protection

- **.gitignore**: Comprehensive exclusion of sensitive files
- **No hardcoded secrets**: All credentials from environment/.env
- **Default client ID**: Public client only (no secret, no risk if exposed)
- **Token rotation**: Refresh tokens auto-rotate on use
- **Capability gates**: Write operations require explicit opt-in
- **CI secrets**: Stored in GitHub Secrets, never in code
