"""JarvisClaw SDK error types."""
from __future__ import annotations


class JarvisClawError(Exception):
    """Base exception for all JarvisClaw SDK errors."""
    pass


class APIError(JarvisClawError):
    """HTTP error from the API (4xx/5xx)."""

    def __init__(self, status_code: int, message: str, body: dict | None = None):
        self.status_code = status_code
        self.message = message
        self.body = body or {}
        super().__init__(f"[{status_code}] {message}")


class AuthenticationError(APIError):
    """401 Unauthorized — invalid API key or expired token."""
    pass


class RateLimitError(APIError):
    """429 Too Many Requests."""

    @property
    def retry_after(self) -> float | None:
        return self.body.get("retry_after")


class InsufficientBalanceError(APIError):
    """402 Payment Required — not enough USDC balance (x402 mode)."""
    pass


class PaymentError(JarvisClawError):
    """x402 payment signing or settlement failed."""
    pass


class ConnectionError(JarvisClawError):
    """The request never produced an HTTP response.

    Covers timeouts, DNS failures, refused connections and dropped sockets.
    Without this, transport failures would surface as raw `requests` exceptions,
    so callers could not catch every SDK failure via JarvisClawError.

    `cause` holds the underlying exception, and `is_timeout` distinguishes a
    timeout — usually worth retrying — from a hard connection failure.
    """

    def __init__(self, message: str, cause: BaseException | None = None,
                 *, is_timeout: bool = False):
        self.cause = cause
        self.is_timeout = is_timeout
        super().__init__(message)


class TimeoutError(ConnectionError):
    """The request exceeded the client timeout before a response arrived."""

    def __init__(self, message: str, cause: BaseException | None = None):
        super().__init__(message, cause, is_timeout=True)
