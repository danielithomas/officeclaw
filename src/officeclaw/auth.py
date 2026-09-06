"""
Authentication and token management for Outclaw.

Handles OAuth 2.0 token storage, retrieval, and refresh using MSAL.
Supports both public client (device code flow) and confidential client modes.

Public client (default): No client secret needed. Uses device code flow for login
and MSAL's built-in token cache with automatic refresh.

Confidential client (legacy): Requires OFFICECLAW_CLIENT_SECRET. Uses authorization
code flow with manual token refresh.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from msal import ConfidentialClientApplication, PublicClientApplication, SerializableTokenCache

from officeclaw.env import load_environment
from officeclaw.exceptions import AuthenticationError, ConfigurationError, TokenStorageError

# Optional keyring support (legacy mode only)
try:
    import keyring

    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False


# Cache file location
CACHE_DIR = Path.home() / ".officeclaw"
CACHE_FILE = CACHE_DIR / "token_cache.json"


def _load_msal_cache() -> SerializableTokenCache:
    """
    Load the MSAL serializable token cache from disk.

    An unreadable or corrupt cache is not fatal — the user can log in again —
    but it is reported, since silently starting from an empty cache is
    indistinguishable from never having authenticated.
    """
    cache = SerializableTokenCache()
    if CACHE_FILE.exists():
        try:
            cache.deserialize(CACHE_FILE.read_text())
        except (OSError, ValueError, KeyError) as e:
            warnings.warn(
                f"Ignoring unreadable token cache at {CACHE_FILE} ({e}). "
                "Run 'officeclaw auth login' to re-authenticate.",
                stacklevel=2,
            )
    return cache


def _write_private_file(path: Path, content: str) -> None:
    """
    Write a file that only the owner can read.

    Creates with 0600 rather than writing and chmod-ing afterwards: the latter
    leaves the tokens readable by other local users for the width of that
    window. Existing files are re-chmod-ed, since O_CREAT does not apply the
    mode to a file that already exists.

    On Windows there is no fchmod and POSIX modes are not the access control
    anyway; the file inherits the ACL of the user's profile directory, which
    is already private to that account.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, "w")
    except BaseException:
        os.close(fd)
        raise
    # From here the file object owns the descriptor and closes it.
    with handle:
        handle.write(content)


def _save_msal_cache(cache: SerializableTokenCache) -> None:
    """Save the MSAL token cache to disk with secure permissions."""
    if cache.has_state_changed:
        try:
            CACHE_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
            _write_private_file(CACHE_FILE, cache.serialize())
        except OSError as e:
            raise TokenStorageError(f"Failed to save token cache: {e}") from e


def _is_public_client_mode() -> bool:
    """Check whether to use public client (no secret) or confidential client."""
    return not os.getenv("OFFICECLAW_CLIENT_SECRET")


class TokenManager:
    """
    Manages OAuth tokens for Microsoft Graph API access.

    Automatically selects between public client (device code flow) and
    confidential client (authorization code flow) based on whether
    OFFICECLAW_CLIENT_SECRET is set.

    Public client mode (default):
        - Uses MSAL's SerializableTokenCache for persistence
        - Token refresh is handled automatically by acquire_token_silent()
        - Login via device code flow: ``officeclaw auth login``

    Confidential client mode (legacy):
        - Requires OFFICECLAW_CLIENT_SECRET
        - Uses keyring or file-based token storage
        - Manual token refresh via refresh_token

    Example:
        manager = TokenManager()
        token = manager.get_access_token()
    """

    KEYRING_SERVICE = "officeclaw"
    # Service names used before the project was renamed. Tokens stored under
    # them are migrated to KEYRING_SERVICE on first read.
    LEGACY_KEYRING_SERVICES = ("outclaw", "out-claw")
    KEYRING_USERNAME = "microsoft-graph-tokens"

    # Default public client ID — registered by OfficeClaw project.
    # Users can override with OFFICECLAW_CLIENT_ID in .env.
    DEFAULT_CLIENT_ID = "1db8c9bb-eebf-4eb9-82dc-e3ec91d1ca53"

    DEFAULT_SCOPES = [
        "Mail.Read",
        "Mail.ReadWrite",
        "Mail.Send",
        "Calendars.Read",
        "Calendars.ReadWrite",
        "Tasks.ReadWrite",
    ]

    def __init__(self) -> None:
        """Initialize token manager with configuration from environment."""
        load_environment()

        # Load configuration
        self.client_id = os.getenv("OFFICECLAW_CLIENT_ID") or self.DEFAULT_CLIENT_ID
        self.client_secret = os.getenv("OFFICECLAW_CLIENT_SECRET")
        self.tenant_id = os.getenv("OFFICECLAW_TENANT_ID", "consumers")
        self.redirect_uri = os.getenv("OFFICECLAW_REDIRECT_URI", "http://localhost:8000/callback")

        scopes_str = os.getenv("OFFICECLAW_SCOPES")
        self.scopes = scopes_str.split() if scopes_str else self.DEFAULT_SCOPES

        self.use_keyring = os.getenv("OFFICECLAW_USE_KEYRING", "true").lower() == "true"
        self.token_refresh_threshold = int(os.getenv("OFFICECLAW_TOKEN_REFRESH_THRESHOLD", "300"))

        # Determine mode
        self.public_client_mode = _is_public_client_mode()

        if self.public_client_mode:
            self._init_public_client()
        else:
            self._init_confidential_client()

    def _init_public_client(self) -> None:
        """Initialize for public client (device code) mode."""
        authority_base = os.getenv("OFFICECLAW_AUTHORITY", "https://login.microsoftonline.com")
        self.authority = f"{authority_base}/{self.tenant_id}"

        self._cache = _load_msal_cache()
        self._app = PublicClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            token_cache=self._cache,
        )

    def _init_confidential_client(self) -> None:
        """Initialize for confidential client (legacy) mode."""
        # Token storage directory
        cache_dir = os.getenv("OFFICECLAW_TOKEN_CACHE_DIR", ".officeclaw")
        self.token_dir = Path.home() / cache_dir
        self.token_dir.mkdir(mode=0o700, exist_ok=True)
        with contextlib.suppress(OSError):
            # mkdir's mode applies only on creation; tighten a pre-existing dir.
            os.chmod(self.token_dir, 0o700)

        cache_file = os.getenv("OFFICECLAW_TOKEN_CACHE_FILE", "token_cache.json")
        self.token_file = self.token_dir / cache_file

        # Build authority URL
        authority_base = os.getenv("OFFICECLAW_AUTHORITY", "https://login.microsoftonline.com")
        self.authority = f"{authority_base}/{self.tenant_id}"

        # Initialize MSAL app
        self._app = ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority,
        )

        # In-memory cache
        self._cached_tokens: dict[str, Any] | None = None
        self._cache_time: float | None = None

    def get_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            Valid access token string

        Raises:
            AuthenticationError: If no tokens found or refresh fails
        """
        if self.public_client_mode:
            return self._get_access_token_public()
        return self._get_access_token_confidential()

    def _get_access_token_public(self) -> str:
        """Get access token using public client with MSAL cache."""
        accounts = self._app.get_accounts()
        if not accounts:
            raise AuthenticationError(
                "No authentication tokens found. " "Run 'officeclaw auth login' to authenticate."
            )

        result = self._app.acquire_token_silent(
            scopes=self.scopes,
            account=accounts[0],
        )

        if not result:
            raise AuthenticationError(
                "Token refresh failed. " "Run 'officeclaw auth login' to re-authenticate."
            )

        if "error" in result:
            error_desc = result.get("error_description", result["error"])
            raise AuthenticationError(
                f"Token refresh failed: {error_desc}. "
                "Run 'officeclaw auth login' to re-authenticate."
            )

        if "access_token" not in result:
            raise AuthenticationError(
                "No access token in response. " "Run 'officeclaw auth login' to re-authenticate."
            )

        # Persist cache if tokens were refreshed
        _save_msal_cache(self._cache)

        access_token: str = result["access_token"]
        return access_token

    def _get_access_token_confidential(self) -> str:
        """Get access token using confidential client (legacy mode)."""
        tokens = self.get_tokens()

        if not tokens:
            raise AuthenticationError(
                "No authentication tokens found. " "Run 'officeclaw auth login' to authenticate."
            )

        if self._needs_refresh(tokens):
            tokens = self._refresh_tokens(tokens)

        access_token: str = tokens["access_token"]
        return access_token

    # ------------------------------------------------------------------
    # Public client helpers
    # ------------------------------------------------------------------

    def get_msal_app(self) -> PublicClientApplication:
        """
        Get the MSAL PublicClientApplication instance.

        Only available in public client mode. Used by auth_flow for login.

        Returns:
            PublicClientApplication instance

        Raises:
            ConfigurationError: If not in public client mode
        """
        if not self.public_client_mode:
            raise ConfigurationError("get_msal_app() is only available in public client mode.")
        return self._app

    def get_msal_cache(self) -> SerializableTokenCache:
        """
        Get the MSAL token cache.

        Only available in public client mode.

        Returns:
            SerializableTokenCache instance
        """
        if not self.public_client_mode:
            raise ConfigurationError("get_msal_cache() is only available in public client mode.")
        return self._cache

    # ------------------------------------------------------------------
    # Confidential client (legacy) token storage
    # ------------------------------------------------------------------

    def save_tokens(self, tokens: dict[str, Any]) -> None:
        """
        Save tokens securely (confidential client mode only).

        Args:
            tokens: Token dictionary from MSAL
        """
        token_data = {
            **tokens,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "scopes": self.scopes,
        }

        # Try keyring first
        if self.use_keyring and KEYRING_AVAILABLE:
            try:
                keyring.set_password(
                    self.KEYRING_SERVICE,
                    self.KEYRING_USERNAME,
                    json.dumps(token_data),
                )
                self._update_cache(token_data)
                return
            except Exception:  # noqa: S110
                pass  # Fall through to file storage

        # File fallback
        self._save_to_file(token_data)
        self._update_cache(token_data)

    def _save_to_file(self, tokens: dict[str, Any]) -> None:
        """Save tokens to file with secure permissions."""
        try:
            _write_private_file(self.token_file, json.dumps(tokens, indent=2))
        except OSError as e:
            raise TokenStorageError(f"Failed to save tokens: {e}") from e

    def _update_cache(self, tokens: dict[str, Any]) -> None:
        """Update in-memory token cache."""
        self._cached_tokens = tokens
        self._cache_time = time.time()

    def get_tokens(self) -> dict[str, Any] | None:
        """
        Retrieve stored tokens (confidential client mode).

        Returns:
            Token dictionary or None if no tokens found
        """
        # Check in-memory cache (valid for 60 seconds)
        if self._cached_tokens and self._cache_time and time.time() - self._cache_time < 60:
            return self._cached_tokens

        # Try keyring (current service name, then legacy "officeclaw" fallback)
        if self.use_keyring and KEYRING_AVAILABLE:
            for service in (self.KEYRING_SERVICE, *self.LEGACY_KEYRING_SERVICES):
                try:
                    token_json = keyring.get_password(
                        service,
                        self.KEYRING_USERNAME,
                    )
                    if token_json:
                        tokens: dict[str, Any] = json.loads(token_json)
                        # Migrate legacy tokens to new service name
                        if service != self.KEYRING_SERVICE:
                            self.save_tokens(tokens)
                        else:
                            self._update_cache(tokens)
                        return tokens
                except Exception:  # noqa: S110, S112
                    continue

        # Try file storage
        if self.token_file.exists():
            try:
                with open(self.token_file) as f:
                    stored: dict[str, Any] = json.load(f)
                self._update_cache(stored)
                return stored
            except Exception as e:
                raise TokenStorageError(f"Failed to read tokens: {e}") from e

        return None

    def _needs_refresh(self, tokens: dict[str, Any]) -> bool:
        """Check if access token needs to be refreshed."""
        if "expires_in" not in tokens or "saved_at" not in tokens:
            return True

        saved_at = datetime.fromisoformat(tokens["saved_at"].replace("Z", "+00:00"))
        expires_in = tokens["expires_in"]
        expires_at = saved_at + timedelta(seconds=expires_in)

        threshold = timedelta(seconds=self.token_refresh_threshold)
        return datetime.now(timezone.utc) >= (expires_at - threshold)

    def _refresh_tokens(self, tokens: dict[str, Any]) -> dict[str, Any]:
        """
        Refresh access token using refresh token (confidential client mode).

        Args:
            tokens: Current token dictionary

        Returns:
            New token dictionary

        Raises:
            AuthenticationError: If refresh fails
        """
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise AuthenticationError(
                "No refresh token available. " "Run 'officeclaw auth login' to re-authenticate."
            )

        try:
            result: dict[str, Any] = self._app.acquire_token_by_refresh_token(
                refresh_token=refresh_token,
                scopes=self.scopes,
            )

            if "error" in result:
                error_desc = result.get("error_description", result["error"])
                raise AuthenticationError(f"Token refresh failed: {error_desc}")

            if "access_token" not in result:
                raise AuthenticationError("No access token in refresh response")

            self.save_tokens(result)
            return result

        except AuthenticationError:
            raise
        except Exception as e:
            raise AuthenticationError(f"Failed to refresh token: {e}") from e

    # ------------------------------------------------------------------
    # Shared operations
    # ------------------------------------------------------------------

    def clear_tokens(self) -> None:
        """Clear all stored tokens (logout)."""
        if self.public_client_mode:
            # Remove MSAL cache file
            if CACHE_FILE.exists():
                with contextlib.suppress(Exception):
                    CACHE_FILE.unlink()
            # Reset in-memory cache
            self._cache = SerializableTokenCache()
            self._app = PublicClientApplication(
                client_id=self.client_id,
                authority=self.authority,
                token_cache=self._cache,
            )
        else:
            # Clear keyring
            if self.use_keyring and KEYRING_AVAILABLE:
                for service in (self.KEYRING_SERVICE, *self.LEGACY_KEYRING_SERVICES):
                    with contextlib.suppress(Exception):
                        keyring.delete_password(service, self.KEYRING_USERNAME)

            # Clear file
            if self.token_file.exists():
                with contextlib.suppress(Exception):
                    self.token_file.unlink()

            # Clear cache
            self._cached_tokens = None
            self._cache_time = None

    def get_token_info(self) -> dict[str, Any] | None:
        """
        Get information about stored tokens (for status display).

        Returns:
            Token metadata (no sensitive values) or None
        """
        if self.public_client_mode:
            return self._get_token_info_public()
        return self._get_token_info_confidential()

    def _get_token_info_public(self) -> dict[str, Any] | None:
        """Get token info for public client mode."""
        accounts = self._app.get_accounts()
        if not accounts:
            return None

        account = accounts[0]

        # Try a silent acquisition to check validity
        result = self._app.acquire_token_silent(
            scopes=self.scopes,
            account=account,
        )

        _save_msal_cache(self._cache)

        if result and "access_token" in result:
            expires_in = result.get("expires_in", 0)
            return {
                "account": account.get("username", "Unknown"),
                "is_expired": False,
                "needs_refresh": False,
                "expires_in_seconds": expires_in,
                "time_until_expiry_seconds": expires_in,
                "scopes": self.scopes,
                "storage_location": str(CACHE_FILE),
                "mode": "public_client (device code flow)",
            }

        # Tokens exist but can't be refreshed
        return {
            "account": account.get("username", "Unknown"),
            "is_expired": True,
            "needs_refresh": True,
            "expires_in_seconds": 0,
            "time_until_expiry_seconds": 0,
            "scopes": self.scopes,
            "storage_location": str(CACHE_FILE),
            "mode": "public_client (device code flow)",
        }

    def _get_token_info_confidential(self) -> dict[str, Any] | None:
        """Get token info for confidential client mode."""
        tokens = self.get_tokens()
        if not tokens:
            return None

        saved_at_str = tokens.get("saved_at", "1970-01-01T00:00:00+00:00")
        saved_at = datetime.fromisoformat(saved_at_str.replace("Z", "+00:00"))
        if saved_at.tzinfo is None:
            saved_at = saved_at.replace(tzinfo=timezone.utc)
        expires_in = tokens.get("expires_in", 0)
        expires_at = saved_at + timedelta(seconds=expires_in)
        time_until_expiry = expires_at - datetime.now(timezone.utc)

        storage_location = (
            f"System keyring ({self.KEYRING_SERVICE})"
            if self.use_keyring and KEYRING_AVAILABLE
            else str(self.token_file)
        )

        return {
            "saved_at": saved_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "expires_in_seconds": expires_in,
            "time_until_expiry_seconds": int(time_until_expiry.total_seconds()),
            "is_expired": time_until_expiry.total_seconds() <= 0,
            "needs_refresh": self._needs_refresh(tokens),
            "scopes": tokens.get("scope", "").split() if tokens.get("scope") else [],
            "storage_location": storage_location,
            "mode": "confidential_client (authorization code flow)",
        }

    def refresh(self) -> dict[str, Any]:
        """
        Refresh the access token without an interactive login.

        Uses the cached refresh token. This is what happens automatically on
        every request; the value of doing it deliberately is finding out *now*
        whether the credentials still work, rather than when a cron job runs.

        Returns:
            Token metadata, as returned by get_token_info()

        Raises:
            AuthenticationError: If refresh fails and a login is required.
        """
        self.invalidate_cache()
        self.get_access_token()

        info = self.get_token_info()
        if info is None:
            raise AuthenticationError(
                "No authentication tokens found. Run 'officeclaw auth login' to authenticate."
            )
        return info

    def invalidate_cache(self) -> None:
        """
        Drop the in-memory token cache so the next read hits storage.

        A no-op in public client mode, where MSAL owns the cache.
        """
        if not self.public_client_mode:
            self._cached_tokens = None
            self._cache_time = None

    def get_account_username(self) -> str | None:
        """
        Address of the signed-in account, if known.

        Reads what is already cached locally — no network call — so callers can
        use it on hot paths. Returns None when it cannot be determined.
        """
        if self.public_client_mode:
            accounts = self._app.get_accounts()
            if not accounts:
                return None
            username = accounts[0].get("username")
        else:
            tokens = self.get_tokens() or {}
            username = tokens.get("id_token_claims", {}).get("preferred_username")

        return username if isinstance(username, str) and "@" in username else None

    @property
    def is_authenticated(self) -> bool:
        """Check if valid tokens exist."""
        if self.public_client_mode:
            return bool(self._app.get_accounts())
        tokens = self.get_tokens()
        return tokens is not None and "access_token" in tokens
