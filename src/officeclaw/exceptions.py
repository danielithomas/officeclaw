"""
Outclaw exceptions.

Custom exception classes for handling Microsoft Graph API errors
and authentication failures.
"""

from __future__ import annotations


class OutclawError(Exception):
    """Base exception for Outclaw errors."""

    pass


class AuthenticationError(OutclawError):
    """
    Raised when authentication fails.

    This can occur when:
    - No tokens are available (user not logged in)
    - Access token is expired and refresh fails
    - Token refresh returns an error
    - Credentials are invalid

    Resolution: Run `officeclaw auth login` to re-authenticate.
    """

    pass


class GraphAPIError(OutclawError):
    """
    Raised when Microsoft Graph API returns an error.

    Attributes:
        code: Error code from Graph API (e.g., "InvalidAuthenticationToken")
        message: Human-readable error message
        status_code: HTTP status code (if available)

    Common error codes:
        - InvalidAuthenticationToken: Token expired or invalid
        - ResourceNotFound: Requested resource doesn't exist
        - AccessDenied: Insufficient permissions
        - BadRequest: Invalid request parameters
        - TooManyRequests: Rate limit exceeded
    """

    def __init__(self, code: str, message: str, status_code: int | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"{code}: {message}")


class RateLimitError(GraphAPIError):
    """
    Raised when rate limit is exceeded.

    Microsoft Graph API has rate limits (~120 requests/minute for most endpoints).
    When exceeded, wait and retry.

    Attributes:
        retry_after: Seconds to wait before retrying (if provided by API)
    """

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int | None = None):
        self.retry_after = retry_after
        super().__init__("TooManyRequests", message, 429)


class PolicyViolationError(OutclawError):
    """
    Base class for outbound actions refused by local policy.

    Policy checks live in :mod:`officeclaw.policy` and are enforced by the CLI
    and the Python API alike. Blocked attempts are logged.
    """

    pass


class RecipientNotAllowedError(PolicyViolationError):
    """
    Raised when an outbound message targets an address outside the allowlist.

    Enforced on every send path (send, reply, reply-all, forward) whenever
    OFFICECLAW_ALLOWED_RECIPIENTS is set.

    Resolution: add the address to OFFICECLAW_ALLOWED_RECIPIENTS, or send to
    an address that is already listed.
    """

    pass


class AttachmentNotAllowedError(PolicyViolationError):
    """
    Raised when a file to attach sits outside the permitted directories.

    Enforced when OFFICECLAW_ALLOWED_ATTACHMENT_DIRS is set, which keeps an
    agent from attaching arbitrary files (SSH keys, password stores) to
    outbound mail.

    Resolution: move the file into one of the configured directories, or add
    its directory to OFFICECLAW_ALLOWED_ATTACHMENT_DIRS.
    """

    pass


class TaskListError(OutclawError):
    """
    Raised when a task list cannot be resolved from a name or default.

    This covers a name that matches no list, a name that matches more than one
    (which is not guessed at), and the case where no list was given and no
    default could be determined.

    Resolution: pass --list-id, or set OFFICECLAW_DEFAULT_TASK_LIST_NAME.
    """

    pass


class ConfigurationError(OutclawError):
    """
    Raised when configuration is missing or invalid.

    This can occur when:
    - Required environment variables are not set
    - .env file is malformed
    - Client ID or secret is invalid

    Resolution: Check .env file and environment variables.
    """

    pass


class TokenStorageError(OutclawError):
    """
    Raised when token storage operations fail.

    This can occur when:
    - Keyring is not available and file storage fails
    - File permissions prevent reading/writing tokens
    - Token file is corrupted

    Resolution: Check ~/.officeclaw/ directory permissions.
    """

    pass


class AttachmentSecurityError(OutclawError):
    """
    Raised when an attachment download is blocked for security reasons.

    This can occur when:
    - The sender is not in the configured safe senders list
    - Attachment download capability is disabled

    Resolution: Check OFFICECLAW_SAFE_SENDERS_LIST configuration.
    """

    pass


class AttachmentSizeError(OutclawError):
    """
    Raised when an attachment exceeds the configured maximum size.

    Attributes:
        size_bytes: Actual attachment size in bytes
        max_size_mb: Configured maximum size in MB

    Resolution: Increase OFFICECLAW_ATTACHMENT_MAX_SIZE_MB or use alternative delivery.
    """

    def __init__(self, size_bytes: int, max_size_mb: int):
        self.size_bytes = size_bytes
        self.max_size_mb = max_size_mb
        super().__init__(
            f"Attachment size ({size_bytes / 1024 / 1024:.1f} MB) exceeds maximum ({max_size_mb} MB)"
        )


class AttachmentTypeError(OutclawError):
    """
    Raised when an attachment MIME type is not in the allowed types list.

    Attributes:
        content_type: The rejected MIME type
        allowed_types: Configured allowed MIME types

    Resolution: Add MIME type to OFFICECLAW_ATTACHMENT_ALLOWED_TYPES.
    """

    def __init__(self, content_type: str, allowed_types: list[str]):
        self.content_type = content_type
        self.allowed_types = allowed_types
        super().__init__(
            f"Attachment type '{content_type}' not in allowed types: {', '.join(allowed_types)}"
        )
