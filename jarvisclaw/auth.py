"""Authentication strategies for JarvisClaw SDK."""
from __future__ import annotations

import abc
import re
from typing import Any


def detect_key_type(key: str) -> str:
    """Detect whether a private key is EVM or Solana.

    Returns: "evm" or "solana"
    """
    # 0x prefix = definitely EVM
    if key.startswith("0x") or key.startswith("0X"):
        return "evm"

    # 64 hex chars (no prefix) = EVM
    if len(key) == 64 and re.fullmatch(r"[0-9a-fA-F]+", key):
        return "evm"

    # Otherwise try base58 decode
    try:
        import base58
        decoded = base58.b58decode(key)
        if len(decoded) in (32, 64):
            return "solana"
    except Exception:
        pass

    # Fallback: if it looks like hex, treat as EVM
    if re.fullmatch(r"[0-9a-fA-F]+", key):
        return "evm"

    raise ValueError(
        f"Cannot detect key type (length={len(key)}). "
        "Use network='base' or network='solana' to specify explicitly."
    )


class AuthStrategy(abc.ABC):
    """Base class for authentication strategies."""

    @abc.abstractmethod
    def prepare_headers(self, headers: dict) -> dict:
        ...

    @abc.abstractmethod
    def handle_402(self, resp, method: str, url: str, session, **kwargs) -> Any:
        ...

    @property
    def address(self) -> str | None:
        return None

    def supports_x402(self) -> bool:
        """Whether this auth strategy supports x402 payment signing."""
        return False


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
    """x402 EVM (Base chain) authentication."""

    def __init__(self, private_key: str, network: str = "eip155:8453"):
        from .x402 import X402Signer
        self._signer = X402Signer(private_key, network)

    def prepare_headers(self, headers: dict) -> dict:
        return headers

    def handle_402(self, resp, method, url, session, **kwargs):
        signature = self._signer.sign_from_402(resp, url)
        headers = kwargs.pop("headers", {}) or {}
        headers["PAYMENT-SIGNATURE"] = signature
        _rewind_files(kwargs)
        retry = session.request(method, url, headers=headers, **kwargs)
        return retry

    @property
    def address(self) -> str | None:
        return self._signer.address

    def supports_x402(self) -> bool:
        return True


class SolanaX402Auth(AuthStrategy):
    """x402 Solana authentication."""

    def __init__(self, private_key: str, base_url: str = ""):
        from .x402_solana import SolanaX402Signer
        self._signer = SolanaX402Signer(private_key)
        self._base_url = base_url

    def prepare_headers(self, headers: dict) -> dict:
        return headers

    def handle_402(self, resp, method, url, session, **kwargs):
        signature = self._signer.sign_from_402(resp, url, self._base_url)
        headers = kwargs.pop("headers", {}) or {}
        headers["PAYMENT-SIGNATURE"] = signature
        _rewind_files(kwargs)
        retry = session.request(method, url, headers=headers, **kwargs)
        return retry

    @property
    def address(self) -> str | None:
        return self._signer.address

    def supports_x402(self) -> bool:
        return True


def _rewind_files(kwargs: dict) -> None:
    """Seek file objects in 'files' back to start for retry after 402.

    After the initial request is sent, file objects are at EOF.
    Without rewinding, the retry would upload empty content.
    Handles all formats accepted by requests/httpx:
      - dict: {"file": file_obj} or {"file": ("name", file_obj, "mime")}
      - list: [("file", file_obj)] or [("file", ("name", file_obj, "mime"))]
    """
    files = kwargs.get("files")
    if not files:
        return

    def _seek(obj):
        if hasattr(obj, "seek"):
            obj.seek(0)
        elif isinstance(obj, (tuple, list)) and len(obj) >= 2:
            # ("filename", file_obj, ...) tuple format
            if hasattr(obj[1], "seek"):
                obj[1].seek(0)

    if isinstance(files, dict):
        for val in files.values():
            _seek(val)
    elif isinstance(files, (list, tuple)):
        for item in files:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                _seek(item[1])
            elif hasattr(item, "seek"):
                item.seek(0)
