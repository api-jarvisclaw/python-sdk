"""Authentication strategies for JarvisClaw SDK."""
from __future__ import annotations

import abc
from typing import Any


class AuthStrategy(abc.ABC):
    """Base class for authentication strategies."""

    @abc.abstractmethod
    def prepare_headers(self, headers: dict) -> dict:
        """Add auth headers before sending request."""
        ...

    @abc.abstractmethod
    def handle_402(self, resp, method: str, url: str, session, **kwargs) -> Any:
        """Handle 402 Payment Required. Return retry response or None."""
        ...

    @property
    def address(self) -> str | None:
        """Wallet address (x402 mode only)."""
        return None


class APIKeyAuth(AuthStrategy):
    """API Key authentication (Bearer token)."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def prepare_headers(self, headers: dict) -> dict:
        headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def handle_402(self, resp, method, url, session, **kwargs):
        return None


class X402Auth(AuthStrategy):
    """x402 Agent authentication (wallet signing)."""

    def __init__(self, private_key: str, network: str = "eip155:8453"):
        from .x402 import X402Signer
        self._signer = X402Signer(private_key, network)

    def prepare_headers(self, headers: dict) -> dict:
        return headers

    def handle_402(self, resp, method, url, session, **kwargs):
        signature = self._signer.sign_from_402(resp, url)
        headers = kwargs.pop("headers", {}) or {}
        headers["PAYMENT-SIGNATURE"] = signature
        retry = session.request(method, url, headers=headers, **kwargs)
        return retry

    @property
    def address(self) -> str | None:
        return self._signer.address
