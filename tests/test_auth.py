"""
Tests for the Outclaw auth module.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from officeclaw.exceptions import AuthenticationError


class TestTokenManagerPublicClient:
    """Test TokenManager in public client (device code) mode."""

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-client-id"}, clear=True)
    def test_init_public_client(self, mock_cache, mock_app, mock_env_loader):
        """Test initialization in public client mode (no secret)."""
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()

        manager = TokenManager()

        assert manager.client_id == "test-client-id"
        assert manager.public_client_mode is True
        mock_app.assert_called_once()

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {}, clear=True)
    def test_init_uses_default_client_id_when_not_set(self, mock_cache, mock_pca, mock_env_loader):
        """Test initialization uses default client ID when env var is not set."""
        from officeclaw.auth import TokenManager

        mock_cache.return_value = None
        mock_pca.return_value = MagicMock()
        tm = TokenManager()
        assert tm.client_id == TokenManager.DEFAULT_CLIENT_ID

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-id"}, clear=True)
    def test_get_access_token_no_accounts(self, mock_cache, mock_app_class, mock_env_loader):
        """Test getting access token when not authenticated."""
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = []
        mock_app_class.return_value = mock_app

        manager = TokenManager()

        with pytest.raises(AuthenticationError) as exc_info:
            manager.get_access_token()

        assert "No authentication tokens" in str(exc_info.value)

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth._save_msal_cache")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-id"}, clear=True)
    def test_get_access_token_success(self, mock_cache, mock_app_class, mock_save, mock_env_loader):
        """Test successful token acquisition via silent flow."""
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@outlook.com"}]
        mock_app.acquire_token_silent.return_value = {
            "access_token": "test-access-token",
            "expires_in": 3600,
        }
        mock_app_class.return_value = mock_app

        manager = TokenManager()
        token = manager.get_access_token()

        assert token == "test-access-token"  # noqa: S105
        mock_app.acquire_token_silent.assert_called_once()

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-id"}, clear=True)
    def test_get_access_token_silent_fails(self, mock_cache, mock_app_class, mock_env_loader):
        """Test error when silent acquisition fails."""
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@outlook.com"}]
        mock_app.acquire_token_silent.return_value = None
        mock_app_class.return_value = mock_app

        manager = TokenManager()

        with pytest.raises(AuthenticationError) as exc_info:
            manager.get_access_token()

        assert "officeclaw auth login" in str(exc_info.value)

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-id"}, clear=True)
    def test_is_authenticated_true(self, mock_cache, mock_app_class, mock_env_loader):
        """Test is_authenticated returns True when accounts exist."""
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@outlook.com"}]
        mock_app_class.return_value = mock_app

        manager = TokenManager()
        assert manager.is_authenticated is True

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-id"}, clear=True)
    def test_is_authenticated_false(self, mock_cache, mock_app_class, mock_env_loader):
        """Test is_authenticated returns False when no accounts."""
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = []
        mock_app_class.return_value = mock_app

        manager = TokenManager()
        assert manager.is_authenticated is False

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.CACHE_FILE")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-id"}, clear=True)
    def test_clear_tokens(self, mock_cache, mock_app_class, mock_cache_file, mock_env_loader):
        """Test clearing tokens in public client mode."""
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()
        mock_app_class.return_value = MagicMock()
        mock_cache_file.exists.return_value = True

        manager = TokenManager()
        manager.clear_tokens()

        mock_cache_file.unlink.assert_called_once()


class TestTokenManagerConfidentialClient:
    """Test TokenManager in confidential client (legacy) mode."""

    @patch.dict(
        "os.environ",
        {
            "OFFICECLAW_CLIENT_ID": "test-client-id",
            "OFFICECLAW_CLIENT_SECRET": "test-client-secret",
        },
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_init_confidential_client(self, mock_app):
        """Test initialization in confidential client mode."""
        from officeclaw.auth import TokenManager

        manager = TokenManager()

        assert manager.client_id == "test-client-id"
        assert manager.client_secret == "test-client-secret"  # noqa: S105
        assert manager.public_client_mode is False

    @patch.dict(
        "os.environ",
        {
            "OFFICECLAW_CLIENT_ID": "test-id",
            "OFFICECLAW_CLIENT_SECRET": "test-secret",
        },
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    @patch("officeclaw.auth.KEYRING_AVAILABLE", False)
    def test_save_tokens_to_file(self, mock_app, tmp_path):
        """Test saving tokens to file when keyring unavailable."""
        from officeclaw.auth import TokenManager

        manager = TokenManager()
        manager.token_dir = tmp_path
        manager.token_file = tmp_path / "tokens.json"

        tokens = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "expires_in": 3600,
        }

        manager.save_tokens(tokens)

        assert manager.token_file.exists()

        with open(manager.token_file) as f:
            saved = json.load(f)

        assert saved["access_token"] == "test-access-token"  # noqa: S105
        assert "saved_at" in saved

    @patch.dict(
        "os.environ",
        {
            "OFFICECLAW_CLIENT_ID": "test-id",
            "OFFICECLAW_CLIENT_SECRET": "test-secret",
        },
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    @patch("officeclaw.auth.KEYRING_AVAILABLE", False)
    def test_get_tokens_from_file(self, mock_app, tmp_path):
        """Test retrieving tokens from file."""
        from officeclaw.auth import TokenManager

        token_file = tmp_path / "tokens.json"
        tokens = {
            "access_token": "test-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(token_file, "w") as f:
            json.dump(tokens, f)

        manager = TokenManager()
        manager.token_file = token_file
        manager._cached_tokens = None

        result = manager.get_tokens()

        assert result["access_token"] == "test-token"  # noqa: S105

    @patch.dict(
        "os.environ",
        {
            "OFFICECLAW_CLIENT_ID": "test-id",
            "OFFICECLAW_CLIENT_SECRET": "test-secret",
        },
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_get_access_token_no_tokens(self, mock_app):
        """Test getting access token when not authenticated."""
        from officeclaw.auth import TokenManager

        manager = TokenManager()
        manager._cached_tokens = None

        with patch.object(manager, "get_tokens", return_value=None):
            with pytest.raises(AuthenticationError) as exc_info:
                manager.get_access_token()

            assert "No authentication tokens" in str(exc_info.value)

    @patch.dict(
        "os.environ",
        {
            "OFFICECLAW_CLIENT_ID": "test-id",
            "OFFICECLAW_CLIENT_SECRET": "test-secret",
        },
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_needs_refresh_no_expiry_info(self, mock_app):
        """Test needs_refresh returns True when no expiry info."""
        from officeclaw.auth import TokenManager

        manager = TokenManager()

        tokens = {"access_token": "token"}
        assert manager._needs_refresh(tokens) is True

    @patch.dict(
        "os.environ",
        {
            "OFFICECLAW_CLIENT_ID": "test-id",
            "OFFICECLAW_CLIENT_SECRET": "test-secret",
        },
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_needs_refresh_expired(self, mock_app):
        """Test needs_refresh returns True for expired tokens."""
        from officeclaw.auth import TokenManager

        manager = TokenManager()

        saved_at = datetime.now(timezone.utc) - timedelta(hours=2)
        tokens = {
            "access_token": "token",
            "expires_in": 3600,
            "saved_at": saved_at.isoformat(),
        }

        assert manager._needs_refresh(tokens) is True

    @patch.dict(
        "os.environ",
        {
            "OFFICECLAW_CLIENT_ID": "test-id",
            "OFFICECLAW_CLIENT_SECRET": "test-secret",
        },
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_needs_refresh_valid(self, mock_app):
        """Test needs_refresh returns False for valid tokens."""
        from officeclaw.auth import TokenManager

        manager = TokenManager()

        saved_at = datetime.now(timezone.utc)
        tokens = {
            "access_token": "token",
            "expires_in": 3600,
            "saved_at": saved_at.isoformat(),
        }

        assert manager._needs_refresh(tokens) is False

    @patch.dict(
        "os.environ",
        {
            "OFFICECLAW_CLIENT_ID": "test-id",
            "OFFICECLAW_CLIENT_SECRET": "test-secret",
        },
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_clear_tokens(self, mock_app, tmp_path):
        """Test clearing tokens."""
        from officeclaw.auth import TokenManager

        token_file = tmp_path / "tokens.json"
        token_file.write_text('{"access_token": "test"}')

        manager = TokenManager()
        manager.token_dir = tmp_path
        manager.token_file = token_file
        manager._cached_tokens = {"test": "data"}

        manager.clear_tokens()

        assert not token_file.exists()
        assert manager._cached_tokens is None

    @patch.dict(
        "os.environ",
        {
            "OFFICECLAW_CLIENT_ID": "test-id",
            "OFFICECLAW_CLIENT_SECRET": "test-secret",
        },
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_get_token_info(self, mock_app):
        """Test getting token info for status display."""
        from officeclaw.auth import TokenManager

        manager = TokenManager()

        saved_at = datetime.now(timezone.utc)
        tokens = {
            "access_token": "token",
            "expires_in": 3600,
            "saved_at": saved_at.isoformat(),
            "scope": "Mail.Read Calendars.Read",
        }

        with patch.object(manager, "get_tokens", return_value=tokens):
            info = manager.get_token_info()

            assert info is not None
            assert "expires_at" in info
            assert "is_expired" in info
            assert info["is_expired"] is False
            assert "scopes" in info
            assert "Mail.Read" in info["scopes"]
            assert info["mode"] == "confidential_client (authorization code flow)"


class TestLegacyKeyringMigration:
    """Tokens stored under the pre-rename service names are still found."""

    @patch.dict(
        "os.environ",
        {"OFFICECLAW_CLIENT_ID": "test-id", "OFFICECLAW_CLIENT_SECRET": "test-secret"},
        clear=True,
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_tokens_are_read_and_migrated_from_legacy_service(self, mock_app):
        from officeclaw.auth import TokenManager

        stored = {"access_token": "legacy-token", "expires_in": 3600}
        manager = TokenManager()
        manager._cached_tokens = None

        def fake_get_password(service, username):
            return json.dumps(stored) if service == "outclaw" else None

        with patch("officeclaw.auth.keyring") as mock_keyring:
            mock_keyring.get_password.side_effect = fake_get_password
            tokens = manager.get_tokens()

            assert tokens["access_token"] == "legacy-token"  # noqa: S105
            # Re-saved under the current service name.
            saved_services = [call.args[0] for call in mock_keyring.set_password.call_args_list]
            assert TokenManager.KEYRING_SERVICE in saved_services

    @patch.dict(
        "os.environ",
        {"OFFICECLAW_CLIENT_ID": "test-id", "OFFICECLAW_CLIENT_SECRET": "test-secret"},
        clear=True,
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_logout_clears_legacy_services_too(self, mock_app, tmp_path):
        from officeclaw.auth import TokenManager

        manager = TokenManager()
        # Never let a logout test reach a real token file.
        manager.token_dir = tmp_path
        manager.token_file = tmp_path / "tokens.json"

        with patch("officeclaw.auth.keyring") as mock_keyring:
            manager.clear_tokens()

            deleted = {call.args[0] for call in mock_keyring.delete_password.call_args_list}
            assert deleted == {TokenManager.KEYRING_SERVICE, *TokenManager.LEGACY_KEYRING_SERVICES}


class TestInvalidateCache:
    """invalidate_cache replaces GraphClient reaching into private state."""

    @patch.dict(
        "os.environ",
        {"OFFICECLAW_CLIENT_ID": "test-id", "OFFICECLAW_CLIENT_SECRET": "test-secret"},
        clear=True,
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_clears_in_memory_tokens(self, mock_app):
        from officeclaw.auth import TokenManager

        manager = TokenManager()
        manager._update_cache({"access_token": "cached"})

        manager.invalidate_cache()

        assert manager._cached_tokens is None
        assert manager._cache_time is None

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-id"}, clear=True)
    def test_public_client_mode_is_a_no_op(self, mock_cache, mock_app, mock_env_loader):
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()
        TokenManager().invalidate_cache()  # must not raise


class TestRefresh:
    """auth refresh proves the credentials still work, without a login."""

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-id"}, clear=True)
    def test_refresh_returns_token_info(self, mock_cache, mock_app, mock_env_loader):
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()
        manager = TokenManager()

        with (
            patch.object(manager, "get_access_token", return_value="token") as get_token,
            patch.object(manager, "get_token_info", return_value={"is_expired": False}),
        ):
            info = manager.refresh()

        get_token.assert_called_once()
        assert info == {"is_expired": False}

    @patch("officeclaw.auth.load_environment")
    @patch("officeclaw.auth.PublicClientApplication")
    @patch("officeclaw.auth._load_msal_cache")
    @patch.dict("os.environ", {"OFFICECLAW_CLIENT_ID": "test-id"}, clear=True)
    def test_refresh_raises_when_login_required(self, mock_cache, mock_app, mock_env_loader):
        from officeclaw.auth import TokenManager

        mock_cache.return_value = MagicMock()
        manager = TokenManager()

        with (
            patch.object(manager, "get_access_token", side_effect=AuthenticationError("expired")),
            pytest.raises(AuthenticationError),
        ):
            manager.refresh()


class TestPrivateFileWrites:
    """Token files are owner-only where the platform supports it."""

    def test_mode_is_restricted_on_posix(self, tmp_path):
        import os

        from officeclaw.auth import _write_private_file

        target = tmp_path / "tokens.json"
        target.write_text("old")
        os.chmod(target, 0o644)

        _write_private_file(target, '{"access_token": "x"}')

        assert target.read_text() == '{"access_token": "x"}'
        if hasattr(os, "fchmod"):
            assert target.stat().st_mode & 0o777 == 0o600

    def test_writes_succeed_without_fchmod(self, tmp_path, monkeypatch):
        """Windows has no os.fchmod; the write must still work there."""
        import os

        from officeclaw.auth import _write_private_file

        monkeypatch.delattr(os, "fchmod", raising=False)
        target = tmp_path / "tokens.json"

        _write_private_file(target, "content")

        assert target.read_text() == "content"


class TestSuiteIsolation:
    """Guard against the suite reaching the developer's real credentials."""

    def test_home_is_redirected(self, tmp_path):
        from pathlib import Path

        assert str(Path.home()).startswith(str(tmp_path))

    @patch.dict(
        "os.environ",
        {"OFFICECLAW_CLIENT_ID": "test-id", "OFFICECLAW_CLIENT_SECRET": "test-secret"},
    )
    @patch("officeclaw.auth.ConfidentialClientApplication")
    def test_token_paths_stay_inside_the_sandbox(self, mock_app, tmp_path):
        """Legacy mode derives its token file from Path.home() at runtime."""
        from officeclaw.auth import CACHE_FILE, TokenManager

        manager = TokenManager()

        assert str(manager.token_file).startswith(str(tmp_path))
        assert str(CACHE_FILE).startswith(str(tmp_path))
