"""
Microsoft Graph API base client for Outclaw.

Provides authenticated HTTP requests with error handling, retries, and pagination.
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

import requests

from officeclaw.auth import TokenManager
from officeclaw.env import load_environment
from officeclaw.exceptions import (
    AuthenticationError,
    GraphAPIError,
    RateLimitError,
)


def _parse_retry_after(value: str | None, default: int) -> int:
    """
    Read a Retry-After header.

    RFC 9110 allows either a delay in seconds or an HTTP-date; int() alone
    raises on the latter, turning a rate limit into an unhandled error.
    """
    if not value:
        return default

    value = value.strip()
    if value.isdigit():
        return int(value)

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return default

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0, int((retry_at - datetime.now(timezone.utc)).total_seconds()))


class GraphClient:
    """
    Base client for Microsoft Graph API.

    Features:
        - Authenticated HTTP requests
        - Automatic token refresh
        - Error handling and retries
        - Rate limit handling with backoff
        - Pagination support

    Example:
        with GraphClient() as client:
            messages = client.get("/me/messages", params={"$top": 10})
    """

    def __init__(self, token_manager: TokenManager | None = None) -> None:
        """
        Initialize Graph API client.

        Args:
            token_manager: TokenManager instance (creates new if not provided)
        """
        load_environment()

        self.token_manager = token_manager or TokenManager()
        self.base_url = os.getenv(
            "OFFICECLAW_GRAPH_API_ENDPOINT", "https://graph.microsoft.com/v1.0"
        )
        self.max_retries = int(os.getenv("OFFICECLAW_MAX_RETRIES", "3"))
        self.request_timeout = int(os.getenv("OFFICECLAW_REQUEST_TIMEOUT", "30"))
        self.rate_limit_wait = int(os.getenv("OFFICECLAW_RATE_LIMIT_WAIT", "60"))

        # Session for connection pooling
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _get_headers(self, custom_headers: dict[str, str] | None = None) -> dict[str, str]:
        """Get headers with authentication token."""
        access_token = self.token_manager.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint."""
        if endpoint.startswith("http"):
            return endpoint
        base = self.base_url.rstrip("/") + "/"
        return urljoin(base, endpoint.lstrip("/"))

    def _handle_response(self, response: requests.Response, raw: bool = False) -> Any:
        """Handle API response and errors."""
        # Success
        if response.status_code in (200, 201, 202):
            if raw:
                return response.content
            return response.json() if response.content else None

        # No content (successful delete)
        if response.status_code == 204:
            return None

        # Parse error
        try:
            error_data = response.json()
            error_info = error_data.get("error", {})
            error_code = error_info.get("code", "Unknown")
            error_message = error_info.get("message", "No error message")
        except (ValueError, KeyError):
            error_code = f"HTTP{response.status_code}"
            error_message = response.text or response.reason

        # Map to exceptions
        if response.status_code == 401:
            raise AuthenticationError(f"Authentication failed: {error_message}")
        elif response.status_code == 403:
            raise GraphAPIError("AccessDenied", f"Permission denied: {error_message}", 403)
        elif response.status_code == 404:
            raise GraphAPIError("ResourceNotFound", f"Not found: {error_message}", 404)
        elif response.status_code == 429:
            retry_after = _parse_retry_after(
                response.headers.get("Retry-After"), self.rate_limit_wait
            )
            raise RateLimitError("Rate limit exceeded", retry_after)
        else:
            raise GraphAPIError(error_code, error_message, response.status_code)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_count: int = 0,
        raw: bool = False,
    ) -> Any:
        """Make HTTP request with retries and error handling."""
        url = self._build_url(endpoint)
        request_headers = self._get_headers(headers)
        if raw:
            # Attachment content is bytes, not JSON.
            request_headers["Accept"] = "*/*"

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=request_headers,
                params=params,
                json=data,
                timeout=self.request_timeout,
            )
            return self._handle_response(response, raw=raw)

        except RateLimitError as e:
            if retry_count < self.max_retries:
                wait_time = e.retry_after or (2**retry_count * self.rate_limit_wait)
                time.sleep(wait_time)
                return self._make_request(
                    method, endpoint, params, data, headers, retry_count + 1, raw
                )
            raise

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if retry_count < self.max_retries:
                time.sleep(2**retry_count)
                return self._make_request(
                    method, endpoint, params, data, headers, retry_count + 1, raw
                )
            raise GraphAPIError("NetworkError", str(e)) from e

        except AuthenticationError:
            if retry_count == 0:
                # Force token refresh and retry once
                self.token_manager.invalidate_cache()
                return self._make_request(
                    method, endpoint, params, data, headers, retry_count + 1, raw
                )
            raise

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Make GET request."""
        return self._make_request("GET", endpoint, params=params, headers=headers)

    def post(self, endpoint: str, data: dict[str, Any]) -> Any:
        """Make POST request."""
        return self._make_request("POST", endpoint, data=data)

    def patch(self, endpoint: str, data: dict[str, Any]) -> Any:
        """Make PATCH request."""
        return self._make_request("PATCH", endpoint, data=data)

    def delete(self, endpoint: str) -> None:
        """Make DELETE request."""
        self._make_request("DELETE", endpoint)

    def get_binary(self, endpoint: str) -> bytes:
        """
        GET an endpoint that returns bytes rather than JSON.

        Used for attachment content (``/$value``), which the JSON response
        handling would otherwise try to decode.
        """
        content: bytes = self._make_request("GET", endpoint, raw=True)
        return content

    def get_paginated(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """
        Get paginated results from API.

        Args:
            endpoint: API endpoint
            params: Query parameters
            limit: Maximum items to return
            headers: Extra request headers, applied to every page

        Yields:
            Individual items from response
        """
        next_url: str | None = endpoint
        items_returned = 0

        while next_url:
            if next_url.startswith("http"):
                response = self._make_request("GET", next_url, headers=headers)
            else:
                response = self._make_request("GET", next_url, params=params, headers=headers)
                params = None  # Only use params on first request

            items = response.get("value", [])

            for item in items:
                yield item
                items_returned += 1
                if limit and items_returned >= limit:
                    return

            next_url = response.get("@odata.nextLink")

    def get_all(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get all items from paginated endpoint as a list."""
        return list(self.get_paginated(endpoint, params, limit, headers))

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()

    def __enter__(self) -> GraphClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
