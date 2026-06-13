"""BaseClient — shared HTTP engine with x402 payment support."""
from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any

import requests

from .auth import APIKeyAuth, AuthStrategy, X402Auth, SolanaX402Auth
from .errors import (
    APIError,
    AuthenticationError,
    InsufficientBalanceError,
    RateLimitError,
)

DEFAULT_BASE_URL = "https://api.jarvisclaw.ai"

MAX_RETRIES = 3
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

# 1 USD = 500,000 quota units in the API billing system
QUOTA_PER_USD = 500_000


class BaseClient:
    """Shared HTTP + x402 engine for all JarvisClaw client classes.

    Usage:
        # API Key mode
        client = ChatClient(api_key="sk-...")

        # x402 Agent mode (requires: pip install jarvisclaw[agent])
        client = ChatClient(private_key="0x...")
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        private_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 120,
        network: str | None = None,
    ):
        if api_key:
            self._auth: AuthStrategy = APIKeyAuth(api_key)
        elif private_key:
            from .auth import detect_key_type, SolanaX402Auth
            key_type = network or detect_key_type(private_key)
            if key_type == "solana":
                determined_base = (
                    base_url
                    or os.environ.get("JARVISCLAW_BASE_URL")
                    or DEFAULT_BASE_URL
                ).rstrip("/")
                self._auth = SolanaX402Auth(private_key, base_url=determined_base)
            else:
                self._auth = X402Auth(private_key)
        else:
            env_key = os.environ.get("JARVISCLAW_API_KEY")
            env_pk = os.environ.get("JARVISCLAW_WALLET_KEY")
            if env_key:
                self._auth = APIKeyAuth(env_key)
            elif env_pk:
                from .auth import detect_key_type, SolanaX402Auth
                key_type = detect_key_type(env_pk)
                if key_type == "solana":
                    determined_base = (
                        base_url
                        or os.environ.get("JARVISCLAW_BASE_URL")
                        or DEFAULT_BASE_URL
                    ).rstrip("/")
                    self._auth = SolanaX402Auth(env_pk, base_url=determined_base)
                else:
                    self._auth = X402Auth(env_pk)
            else:
                raise ValueError(
                    "Provide api_key or private_key, or set "
                    "JARVISCLAW_API_KEY / JARVISCLAW_WALLET_KEY env var"
                )

        self.base_url = (
            base_url
            or os.environ.get("JARVISCLAW_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session_lock = __import__("threading").Lock()
        self._total_spent = 0.0

    @property
    def address(self) -> str | None:
        """Wallet address (x402 mode only)."""
        return self._auth.address

    # ─── Utility ────────────────────────────────────────────

    def get_balance(self) -> float:
        """Get current balance in USD.

        - x402 mode: queries on-chain USDC balance via public RPC
        - API Key mode: queries remaining quota via billing API
        """
        if self._auth.address:
            return self._query_onchain_balance()
        data = self._get("/v1/dashboard/billing/subscription")
        # OpenAI-compatible billing response: hard_limit_usd = remaining + used
        return data.get("hard_limit_usd", 0.0)

    def get_spending(self) -> float:
        """Total estimated USD spent in this session (approximate, uses flat rate)."""
        return self._total_spent

    # ─── Internal HTTP ──────────────────────────────────────

    def _get(self, path: str, **kwargs) -> Any:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs) -> Any:
        return self._request("POST", path, **kwargs)

    def _post_raw(self, path: str, **kwargs) -> requests.Response:
        return self._request_raw("POST", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = self._request_raw(method, path, **kwargs)
        return resp.json()

    def _do_request(self, method: str, url: str, stream: bool, **kwargs) -> requests.Response:
        """Thread-safe session request (protects against concurrent MusicJob threads)."""
        with self._session_lock:
            return self._session.request(method, url, stream=stream, **kwargs)

    def _request_raw(self, method: str, path: str, **kwargs) -> requests.Response:
        url = self.base_url + path
        kwargs.setdefault("timeout", self.timeout)
        stream = kwargs.pop("stream", False)

        headers = kwargs.pop("headers", {}) or {}
        headers = self._auth.prepare_headers(headers)
        kwargs["headers"] = headers

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                delay = min(2 ** attempt + random.random(), 30)
                time.sleep(delay)
                # Rewind file objects for retry (they're at EOF after first send)
                from .auth import _rewind_files
                _rewind_files(kwargs)

            resp = self._do_request(method, url, stream, **kwargs)

            # Handle 402 (x402 payment flow)
            if resp.status_code == 402:
                retry = self._auth.handle_402(
                    resp, method, url, self._session, stream=stream, **kwargs
                )
                if retry is None:
                    body: dict = {}
                    try:
                        body = resp.json()
                    except Exception:
                        pass
                    if self._auth.supports_x402():
                        raise InsufficientBalanceError(402, "Payment signing failed", body)
                    else:
                        raise InsufficientBalanceError(
                            402, "Insufficient balance (x402 not available in API key mode)", body
                        )
                resp = retry
                # If the paid retry itself failed, raise immediately with
                # the server's actual error message — don't re-enter the loop.
                if resp.status_code >= 400:
                    body = self._safe_json(resp)
                    msg = self._extract_message(body, f"Payment rejected (status {resp.status_code})")
                    if resp.status_code == 402:
                        raise InsufficientBalanceError(402, msg, body)
                    raise APIError(resp.status_code, msg, body)

            # Retry on 429/5xx
            if resp.status_code in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                last_error = resp
                continue

            # Error handling
            if resp.status_code == 401:
                body = self._safe_json(resp)
                raise AuthenticationError(401, self._extract_message(body, "Unauthorized"), body)
            if resp.status_code == 429:
                body = self._safe_json(resp)
                raise RateLimitError(429, self._extract_message(body, "Rate limit exceeded"), body)
            if resp.status_code >= 400:
                body = self._safe_json(resp)
                raise APIError(
                    resp.status_code,
                    self._extract_message(body, resp.reason or "Unknown error"),
                    body,
                )

            return resp

        if last_error:
            body = self._safe_json(last_error)
            raise APIError(
                last_error.status_code,
                self._extract_message(body, "Request failed after retries"),
                body,
            )
        raise APIError(500, "Request failed after retries", {})

    def _query_onchain_balance(self) -> float:
        """Query USDC balance on Base chain via public RPC."""
        usdc_contract = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        address = self._auth.address
        padded_addr = "0x70a08231" + address[2:].lower().zfill(64)

        rpc_url = "https://mainnet.base.org"
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": usdc_contract, "data": padded_addr}, "latest"],
            "id": 1,
        }
        resp = requests.post(rpc_url, json=payload, timeout=10)
        result = resp.json().get("result", "0x0")
        balance_raw = int(result, 16)
        return balance_raw / 1_000_000

    def _track_cost(self, model: str, path: str, usage: dict) -> None:
        """Record request cost to local log file."""
        import json as _json  # noqa: PLC0415

        total_tokens = usage.get("total_tokens", 0)
        estimated_usd = total_tokens * 0.00001
        self._total_spent += estimated_usd

        entry = {
            "timestamp": time.time(),
            "model": model,
            "path": path,
            "tokens": total_tokens,
            "estimated_usd": estimated_usd,
        }
        try:
            log_dir = Path.home() / ".jarvisclaw"
            log_dir.mkdir(exist_ok=True)
            with open(log_dir / "cost_log.jsonl", "a") as f:
                f.write(_json.dumps(entry) + "\n")
        except OSError:
            pass

    @staticmethod
    def _safe_json(resp: requests.Response) -> dict:
        try:
            return resp.json()
        except Exception:
            return {}

    @staticmethod
    def _extract_message(body: dict, fallback: str) -> str:
        """Extract error message from response body (supports OpenAI format)."""
        # OpenAI format: {"error": {"message": "..."}}
        if "error" in body and isinstance(body["error"], dict):
            msg = body["error"].get("message")
            if msg:
                return msg
        # Flat format: {"message": "..."}
        if "message" in body:
            return body["message"]
        return fallback

