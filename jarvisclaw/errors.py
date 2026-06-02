"""JarvisClaw SDK error types."""


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
