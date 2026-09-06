"""
Authentication flow for Outclaw.

Supports two modes:
- Device code flow (default): For public client apps without a client secret.
- Authorization code flow (legacy): For confidential client apps with a client secret.
"""

from __future__ import annotations

import html
import http.server
import os
import secrets
import socketserver
import threading
import webbrowser
from typing import Any
from urllib.parse import parse_qs, urlparse

from msal import ConfidentialClientApplication
from rich.console import Console

from officeclaw.auth import CACHE_FILE, TokenManager, _is_public_client_mode, _save_msal_cache
from officeclaw.env import load_environment
from officeclaw.exceptions import AuthenticationError, ConfigurationError

console = Console()


def run_auth_flow() -> dict[str, Any]:
    """
    Run the appropriate authentication flow based on configuration.

    If OFFICECLAW_CLIENT_SECRET is set, uses authorization code flow (legacy).
    Otherwise, uses device code flow (default).

    Returns:
        Token dictionary

    Raises:
        AuthenticationError: If authentication fails
        ConfigurationError: If configuration is invalid
    """
    load_environment()

    if _is_public_client_mode():
        return run_device_code_flow()
    return run_authorization_code_flow()


def run_device_code_flow() -> dict[str, Any]:
    """
    Run the OAuth 2.0 Device Code Flow.

    Displays a URL and code for the user to enter in a browser.
    Polls until authentication completes or times out.

    Returns:
        Token dictionary

    Raises:
        AuthenticationError: If authentication fails
        ConfigurationError: If configuration is invalid
    """
    manager = TokenManager()
    app = manager.get_msal_app()
    cache = manager.get_msal_cache()

    console.print("\n[bold]Outclaw Authentication (Device Code Flow)[/bold]\n")

    # Initiate device code flow
    flow = app.initiate_device_flow(scopes=manager.scopes)

    if "user_code" not in flow:
        error = flow.get("error_description", flow.get("error", "Unknown error"))
        raise AuthenticationError(
            f"Failed to initiate device code flow: {error}\n"
            "Make sure 'Allow public client flows' is enabled in your "
            "Azure app registration (Authentication > Advanced settings)."
        )

    # Display instructions
    console.print(flow["message"])
    console.print()

    # Poll for completion
    console.print("[dim]Waiting for authentication...[/dim]")

    result: dict[str, Any] = app.acquire_token_by_device_flow(flow)

    if "error" in result:
        error = result.get("error", "unknown_error")
        error_desc = result.get("error_description", "Authentication failed")

        if error == "authorization_pending":
            raise AuthenticationError("Authentication timed out. Please try again.")
        elif error == "authorization_declined":
            raise AuthenticationError("Authentication was declined by the user.")
        elif error == "expired_token":
            raise AuthenticationError("The device code expired. Please try again.")
        else:
            raise AuthenticationError(f"Authentication failed: {error_desc}")

    if "access_token" not in result:
        raise AuthenticationError("No access token in response.")

    # Save the MSAL token cache
    _save_msal_cache(cache)

    account = result.get("id_token_claims", {}).get("preferred_username", "Unknown")
    console.print("\n[green]✓[/green] [bold]Authentication successful![/bold]")
    console.print(f"[dim]Signed in as: {account}[/dim]")
    console.print(f"[dim]Token cache: {CACHE_FILE}[/dim]\n")

    return result


# ===========================================================================
# Legacy: Authorization Code Flow (confidential client)
# ===========================================================================


class AuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP handler for the OAuth callback.

    Deliberately a BaseHTTPRequestHandler: SimpleHTTPRequestHandler would serve
    the working directory for any request this class does not override.
    """

    auth_code: str | None = None
    error: str | None = None
    expected_state: str | None = None

    def do_GET(self) -> None:
        """Handle GET request (OAuth callback)."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Reject callbacks that did not originate from the request we started.
        state = params.get("state", [""])[0]
        if self.expected_state and not secrets.compare_digest(state, self.expected_state):
            AuthCallbackHandler.error = "State mismatch — ignoring unexpected callback."
            self._send_error("State mismatch")
            return

        if "code" in params:
            AuthCallbackHandler.auth_code = params["code"][0]
            self._send_success()
        elif "error" in params:
            AuthCallbackHandler.error = params.get("error_description", params["error"])[0]
            self._send_error()
        else:
            self._send_error("No authorization code received")

    def _send_success(self) -> None:
        """Send success response."""
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        page = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Outclaw - Authentication Successful</title>
            <style>
                body { font-family: system-ui, sans-serif; text-align: center; padding: 50px; }
                .success { color: #22c55e; font-size: 48px; }
                h1 { color: #333; }
                p { color: #666; }
            </style>
        </head>
        <body>
            <div class="success">✓</div>
            <h1>Authentication Successful!</h1>
            <p>You can close this window and return to the terminal.</p>
        </body>
        </html>
        """
        self.wfile.write(page.encode())

    def _send_error(self, message: str = "Authentication failed") -> None:
        """Send error response."""
        self.send_response(400)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        page = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Outclaw - Authentication Failed</title>
            <style>
                body {{ font-family: system-ui, sans-serif; text-align: center; padding: 50px; }}
                .error {{ color: #ef4444; font-size: 48px; }}
                h1 {{ color: #333; }}
                p {{ color: #666; }}
            </style>
        </head>
        <body>
            <div class="error">✗</div>
            <h1>Authentication Failed</h1>
            <p>{html.escape(message)}</p>
        </body>
        </html>
        """
        self.wfile.write(page.encode())

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress HTTP server logging."""
        pass


def run_authorization_code_flow() -> dict[str, Any]:
    """
    Run the OAuth 2.0 Authorization Code Flow (legacy).

    Opens browser for user authentication, handles callback,
    and stores tokens securely.

    Returns:
        Token dictionary

    Raises:
        AuthenticationError: If authentication fails
        ConfigurationError: If configuration is invalid
    """
    load_environment()

    # Load configuration
    client_id = os.getenv("OFFICECLAW_CLIENT_ID") or TokenManager.DEFAULT_CLIENT_ID
    client_secret = os.getenv("OFFICECLAW_CLIENT_SECRET")
    redirect_uri = os.getenv("OFFICECLAW_REDIRECT_URI", "http://localhost:8000/callback")
    tenant_id = os.getenv("OFFICECLAW_TENANT_ID", "consumers")
    scopes_str = os.getenv("OFFICECLAW_SCOPES")

    scopes = scopes_str.split() if scopes_str else TokenManager.DEFAULT_SCOPES

    if not client_secret:
        raise ConfigurationError(
            "OFFICECLAW_CLIENT_SECRET is required for authorization code flow. "
            "Remove it to use device code flow instead."
        )

    # Parse redirect URI to get port
    parsed_uri = urlparse(redirect_uri)
    port = parsed_uri.port or 8000

    # Build authority URL
    authority = f"https://login.microsoftonline.com/{tenant_id}"

    # Initialize MSAL app
    app = ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )

    # Get authorization URL. The state is echoed back on the callback and
    # checked there, so another origin cannot feed us an authorization code.
    state = secrets.token_urlsafe(32)
    auth_url = app.get_authorization_request_url(
        scopes=scopes,
        redirect_uri=redirect_uri,
        state=state,
    )

    console.print("\n[bold]Outclaw Authentication (Authorization Code Flow)[/bold]\n")
    console.print("Opening browser for Microsoft login...")
    console.print("[dim]If browser doesn't open, visit:[/dim]")
    console.print(f"[link]{auth_url}[/link]\n")

    # Reset handler state
    AuthCallbackHandler.auth_code = None
    AuthCallbackHandler.error = None
    AuthCallbackHandler.expected_state = state

    # Start callback server on loopback only: ("", port) would accept the
    # callback — and the authorization code in it — from anyone on the network.
    server = socketserver.TCPServer(("127.0.0.1", port), AuthCallbackHandler)
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.start()

    # Open browser
    webbrowser.open(auth_url)

    console.print("[dim]Waiting for authentication...[/dim]")

    # Wait for callback
    server_thread.join(timeout=300)  # 5 minute timeout
    server.server_close()

    # Check result
    if AuthCallbackHandler.error:
        raise AuthenticationError(f"Authentication failed: {AuthCallbackHandler.error}")

    if not AuthCallbackHandler.auth_code:
        raise AuthenticationError("No authorization code received. Authentication timed out.")

    console.print("[dim]Exchanging code for tokens...[/dim]")

    # Exchange code for tokens
    result: dict[str, Any] = app.acquire_token_by_authorization_code(
        code=AuthCallbackHandler.auth_code,
        scopes=scopes,
        redirect_uri=redirect_uri,
    )

    if "error" in result:
        error_desc = result.get("error_description", result["error"])
        raise AuthenticationError(f"Token exchange failed: {error_desc}")

    if "access_token" not in result:
        raise AuthenticationError("No access token in response")

    # Save tokens
    manager = TokenManager()
    manager.save_tokens(result)

    console.print("\n[green]✓[/green] [bold]Authentication successful![/bold]")
    console.print(f"[dim]Tokens stored in: {manager.get_token_info()['storage_location']}[/dim]\n")

    return result


if __name__ == "__main__":
    try:
        run_auth_flow()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from e
