"""BaseClient — shared HTTP engine with x402 payment support."""
from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any

import requests

from .auth import APIKeyAuth, AuthStrategy, X402Auth
from .errors import (
    APIError,
    AuthenticationError,
    InsufficientBalanceError,
    RateLimitError,
)
from .types import Model

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
            from .auth import SolanaX402Auth, detect_key_type
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
                from .auth import SolanaX402Auth, detect_key_type
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
        """Get current spendable balance in USD.

        - x402 mode: reads the wallet's on-chain USDC balance directly, on Base
          for an EVM key and on Solana mainnet for a Solana key.
        - API Key mode: reads the OpenAI-compatible billing endpoint. When the
          account has an HD deposit wallet the gateway reports the real on-chain
          balance there; otherwise it reports the ledger quota in USD.
        """
        if self._auth.address:
            from .auth import SolanaX402Auth

            if isinstance(self._auth, SolanaX402Auth):
                return self._query_solana_usdc_balance()
            return self._query_onchain_balance()

        data = self._get("/v1/dashboard/billing/subscription")
        # This endpoint answers 200 with an {"error": {...}} body on failure
        # instead of a 4xx, so _request_raw cannot catch it by status.
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            raise APIError(200, err["message"], data)
        return data.get("hard_limit_usd", 0.0)

    def get_spending(self) -> float:
        """Total estimated USD spent in this session (approximate, uses flat rate)."""
        return self._total_spent

    def list_models(self) -> list[Model]:
        """List the models this gateway serves.

        Available on every client, since knowing what you can pass as `model` is
        useful regardless of which capability you are using. Worth checking
        before assuming a model exists: a gateway that has no channel for one
        answers 503 rather than falling back.
        """
        data = self._get("/v1/models")
        items = data.get("data") if isinstance(data, dict) else data
        return [
            Model(
                id=m.get("id", ""),
                object=m.get("object", "model"),
                owned_by=m.get("owned_by", ""),
            )
            for m in (items or [])
        ]

    # ─── Internal HTTP ──────────────────────────────────────

    def _get(self, path: str, **kwargs) -> Any:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs) -> Any:
        return self._request("POST", path, **kwargs)

    def _put(self, path: str, **kwargs) -> Any:
        return self._request("PUT", path, **kwargs)

    def _delete(self, path: str, **kwargs) -> Any:
        return self._request("DELETE", path, **kwargs)

    def _post_raw(self, path: str, **kwargs) -> requests.Response:
        return self._request_raw("POST", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = self._request_raw(method, path, **kwargs)
        return resp.json()

    def _do_request(self, method: str, url: str, stream: bool, **kwargs) -> requests.Response:
        """Thread-safe session request (protects against concurrent MusicJob threads).

        Transport failures are translated into SDK exceptions so that callers can
        catch every failure mode through JarvisClawError instead of also having to
        know about `requests`.
        """
        try:
            with self._session_lock:
                return self._session.request(method, url, stream=stream, **kwargs)
        except requests.exceptions.Timeout as e:
            from .errors import TimeoutError as JCTimeoutError

            raise JCTimeoutError(
                f"request to {url} timed out after {kwargs.get('timeout')}s", e
            ) from e
        except requests.exceptions.RequestException as e:
            from .errors import ConnectionError as JCConnectionError

            raise JCConnectionError(f"request to {url} failed: {e}", e) from e

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
        """Query USDC balance on Base via public RPC (EVM keys only)."""
        usdc_contract = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        address = self._auth.address or ""

        # balanceOf(address): 4-byte selector + the address right-aligned in a
        # 32-byte word. Strip 0x only if present — a bare hex address would
        # otherwise lose its first two characters.
        hex_addr = address[2:] if address.lower().startswith("0x") else address
        try:
            int(hex_addr, 16)
        except ValueError:
            raise ValueError(
                f"Cannot read an EVM balance for non-EVM address {address!r}"
            ) from None
        call_data = "0x70a08231" + hex_addr.lower().rjust(64, "0")

        rpc_url = "https://mainnet.base.org"
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": usdc_contract, "data": call_data}, "latest"],
            "id": 1,
        }
        resp = requests.post(rpc_url, json=payload, timeout=10)
        body = resp.json()
        if body.get("error"):
            raise APIError(502, f"Base RPC error: {body['error']}", body)
        result = body.get("result") or "0x0"
        return int(result, 16) / 1_000_000

    def _query_solana_usdc_balance(self) -> float:
        """Query USDC balance on Solana mainnet via public RPC.

        Sums every USDC token account owned by the wallet. getTokenAccountsByOwner
        is used rather than deriving the associated token account, because a wallet
        can legitimately hold USDC in more than one account.
        """
        from .x402_solana import FALLBACK_RPC, USDC_MINT

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                self._auth.address,
                {"mint": USDC_MINT},
                {"encoding": "jsonParsed"},
            ],
        }
        resp = requests.post(FALLBACK_RPC, json=payload, timeout=10)
        body = resp.json()
        if body.get("error"):
            raise APIError(502, f"Solana RPC error: {body['error']}", body)

        total = 0.0
        for acct in (body.get("result") or {}).get("value", []):
            info = (
                acct.get("account", {})
                .get("data", {})
                .get("parsed", {})
                .get("info", {})
            )
            amount = info.get("tokenAmount", {}).get("uiAmount")
            if isinstance(amount, (int, float)):
                total += float(amount)
        return total

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

