"""Async base client and capability clients using httpx."""
from __future__ import annotations

import asyncio
import json as _json
import os
import random
import time
from typing import Any, AsyncGenerator

try:
    import httpx
except ImportError:
    raise ImportError(
        "httpx is required for async clients. Install with: pip install jarvisclaw[async]"
    )

from ..auth import APIKeyAuth, AuthStrategy, X402Auth, detect_key_type
from ..errors import (
    APIError,
    AuthenticationError,
    InsufficientBalanceError,
    RateLimitError,
)
from ..types import AudioResponse, ChatResponse, ImageResponse, SearchResult, VideoJob

DEFAULT_BASE_URL = "https://api.jarvisclaw.ai"
MAX_RETRIES = 3
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class AsyncBaseClient:
    """Async HTTP engine with x402 payment support."""

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
            key_type = network or detect_key_type(private_key)
            if key_type == "solana":
                from ..auth import SolanaX402Auth
                base = (base_url or os.environ.get("JARVISCLAW_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
                self._auth = SolanaX402Auth(private_key, base_url=base)
            else:
                self._auth = X402Auth(private_key)
        else:
            env_key = os.environ.get("JARVISCLAW_API_KEY")
            env_pk = os.environ.get("JARVISCLAW_WALLET_KEY")
            if env_key:
                self._auth = APIKeyAuth(env_key)
            elif env_pk:
                key_type = detect_key_type(env_pk)
                if key_type == "solana":
                    from ..auth import SolanaX402Auth
                    base = (base_url or os.environ.get("JARVISCLAW_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
                    self._auth = SolanaX402Auth(env_pk, base_url=base)
                else:
                    self._auth = X402Auth(env_pk)
            else:
                raise ValueError("Provide api_key or private_key, or set JARVISCLAW_API_KEY / JARVISCLAW_WALLET_KEY")

        self.base_url = (base_url or os.environ.get("JARVISCLAW_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def _get(self, path: str, **kwargs) -> Any:
        return await self._request("GET", path, **kwargs)

    async def _post(self, path: str, **kwargs) -> Any:
        resp = await self._request_raw("POST", path, **kwargs)
        return resp.json()

    async def _post_raw(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_raw("POST", path, **kwargs)

    async def _put(self, path: str, **kwargs) -> Any:
        return await self._request("PUT", path, **kwargs)

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = await self._request_raw(method, path, **kwargs)
        return resp.json()

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Send a request, translating transport failures into SDK exceptions.

        Mirrors the sync client: without this, timeouts and connection errors
        would surface as raw httpx exceptions, so callers could not catch every
        failure through JarvisClawError.
        """
        try:
            return await self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as e:
            from ..errors import TimeoutError as JCTimeoutError

            raise JCTimeoutError(
                f"request to {url} timed out after {kwargs.get('timeout')}s", e
            ) from e
        except httpx.HTTPError as e:
            from ..errors import ConnectionError as JCConnectionError

            raise JCConnectionError(f"request to {url} failed: {e}", e) from e

    async def _request_raw(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = self.base_url + path
        headers = kwargs.pop("headers", {}) or {}
        headers = self._auth.prepare_headers(headers)
        kwargs["headers"] = headers
        req_timeout = kwargs.pop("timeout", self.timeout)

        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                await asyncio.sleep(min(2 ** attempt + random.random(), 30))
                # Rewind file objects for retry (they're at EOF after first send)
                from ..auth import _rewind_files
                _rewind_files(kwargs)

            resp = await self._send(method, url, timeout=req_timeout, **kwargs)

            if resp.status_code == 402:
                retry_resp = await self._handle_402(resp, method, url, req_timeout, **kwargs)
                if retry_resp is None:
                    body = self._safe_json(resp)
                    if self._auth.supports_x402():
                        raise InsufficientBalanceError(402, "Payment signing failed", body)
                    raise InsufficientBalanceError(
                        402, "Insufficient balance (x402 not available in API key mode)", body
                    )
                resp = retry_resp
                # The paid retry failed on its own terms — surface the server's
                # message rather than re-entering the loop and paying again.
                if resp.status_code >= 400:
                    body = self._safe_json(resp)
                    msg = self._extract_message(body, f"Payment rejected (status {resp.status_code})")
                    if resp.status_code == 402:
                        raise InsufficientBalanceError(402, msg, body)
                    raise APIError(resp.status_code, msg, body)

            if resp.status_code in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                continue
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
                    self._extract_message(body, f"Error {resp.status_code}"),
                    body,
                )
            return resp

        raise APIError(500, "Request failed after retries", {})

    async def _handle_402(self, resp, method, url, req_timeout, **kwargs):
        """Sign x402 payment and retry."""
        if not self._auth.supports_x402():
            return None
        # Build response snapshot for signer (CPU-only, no I/O)
        _status_code = resp.status_code
        _headers = dict(resp.headers)
        _content = resp.content
        _text = resp.text
        _json_data = resp.json()

        class _Resp:
            status_code = _status_code
            headers = _headers
            content = _content
            text = _text
            def json(self): return _json_data

        # Dispatch to the correct signer — Solana needs base_url as third arg
        from ..auth import SolanaX402Auth, _rewind_files
        if isinstance(self._auth, SolanaX402Auth):
            signature = self._auth._signer.sign_from_402(_Resp(), url, self.base_url)
        else:
            signature = self._auth._signer.sign_from_402(_Resp(), url)
        if not signature:
            return None
        headers = kwargs.pop("headers", {}) or {}
        headers["PAYMENT-SIGNATURE"] = signature
        _rewind_files(kwargs)
        return await self._send(method, url, headers=headers, timeout=req_timeout, **kwargs)

    def _raise_for_stream_status(self, resp) -> None:
        """Raise the typed error for an already-read streaming response.

        Streaming paths cannot go through _request_raw's error handling, so the
        status mapping lives here to keep both paths consistent.
        """
        body = self._safe_json(resp)
        msg = self._extract_message(body, f"Error {resp.status_code}")
        if resp.status_code == 401:
            raise AuthenticationError(401, msg, body)
        if resp.status_code == 402:
            raise InsufficientBalanceError(402, msg, body)
        if resp.status_code == 429:
            raise RateLimitError(429, msg, body)
        raise APIError(resp.status_code, msg, body)

    @staticmethod
    def _safe_json(resp) -> dict:
        try:
            return resp.json()
        except Exception:
            return {}

    @staticmethod
    def _extract_message(body: dict, fallback: str) -> str:
        """Extract an error message from an OpenAI-style or flat error body."""
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict) and err.get("message"):
                return err["message"]
            if body.get("message"):
                return body["message"]
        return fallback


# ─── Chat ─────────────────────────────────────────────────────

class AsyncChatClient(AsyncBaseClient):
    """Async chat completions."""

    async def complete(self, message: str, *, model: str | None = None, system: str | None = None, temperature: float = 0.7, **kwargs) -> str:
        """Simple chat — returns response text directly.

        **kwargs forwards extra API params such as max_tokens. Capping
        max_tokens matters on a low balance: the gateway reserves against the
        model's full output allowance up front.
        """
        resp = await self.completion(
            self._build_messages(message, system), model=model,
            temperature=temperature, **kwargs,
        )
        return resp.content

    async def completion(self, messages: list[dict], *, model: str | None = None, **kwargs) -> ChatResponse:
        model = model or "auto"
        data = await self._post("/v1/chat/completions", json={"model": model, "messages": messages, **kwargs})

        # Handle search response format (auto/search returns {summary} not {choices})
        if "summary" in data and "choices" not in data:
            return ChatResponse(
                content=data["summary"],
                model=data.get("model", model),
                id=data.get("id", ""),
                usage=data.get("usage", {}),
                raw=data,
            )

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "") if data.get("choices") else ""
        return ChatResponse(content=content, model=data.get("model", model), id=data.get("id", ""), usage=data.get("usage", {}), raw=data)

    async def stream(self, message: str, *, model: str | None = None, system: str | None = None, **kwargs) -> AsyncGenerator[str, None]:
        model = model or "auto"
        messages = self._build_messages(message, system)
        body = {"model": model, "messages": messages, "stream": True, **kwargs}
        headers = self._auth.prepare_headers({})
        url = self.base_url + "/v1/chat/completions"
        async with self._client.stream("POST", url, json=body, headers=headers, timeout=self.timeout) as resp:
            # Errors must be checked before parsing SSE.
            if resp.status_code == 402:
                await resp.aread()
                # A 402 cannot be paid mid-stream: the payment retry needs a fresh
                # request, and re-issuing it here would restart the generation the
                # caller is already iterating. complete() handles payment.
                if self._auth.supports_x402():
                    raise InsufficientBalanceError(
                        402, "x402 streaming not supported — use complete() for paid requests",
                        self._safe_json(resp),
                    )
                raise InsufficientBalanceError(402, "Insufficient balance", self._safe_json(resp))
            if resp.status_code >= 400:
                await resp.aread()
                self._raise_for_stream_status(resp)

            async for line in resp.aiter_lines():
                line = (line or "").rstrip("\r").strip()
                if not line or line.startswith(":"):
                    continue
                # Match "data:" with an optional single space, per the SSE spec.
                # Requiring the space silently dropped any upstream emitting
                # "data:{...}".
                name, sep, value = line.partition(":")
                if not sep or name != "data":
                    continue
                if value.startswith(" "):
                    value = value[1:]
                if value == "[DONE]":
                    return
                try:
                    chunk = _json.loads(value)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                except (_json.JSONDecodeError, IndexError, KeyError):
                    continue

    @staticmethod
    def _build_messages(message: str, system: str | None) -> list[dict]:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": message})
        return msgs


# ─── Image ────────────────────────────────────────────────────

class AsyncImageClient(AsyncBaseClient):
    """Async image generation."""

    async def generate(self, prompt: str, *, model: str | None = None, size: str = "1024x1024", n: int = 1, wait: bool = True, poll_interval: float = 5.0, poll_timeout: float = 300.0) -> ImageResponse:
        model = model or "auto/image"
        data = await self._post("/v1/images/generations", json={"model": model, "prompt": prompt, "size": size, "n": n})
        if data.get("status") not in ("queued", "in_progress") or not data.get("poll_url"):
            return self._parse(data)
        if not wait:
            return ImageResponse(raw=data)
        return await self._poll(data, poll_interval, poll_timeout)

    async def status(self, job_id: str) -> ImageResponse:
        data = await self._get(f"/v1/images/generations/{job_id}")
        if data.get("status") in ("queued", "in_progress"):
            return ImageResponse(raw=data)
        return self._parse(data)

    async def _poll(self, data: dict, interval: float, timeout: float) -> ImageResponse:
        poll_url = data["poll_url"]
        start = time.monotonic()
        while True:
            if time.monotonic() - start >= timeout:
                return ImageResponse(raw=data)
            await asyncio.sleep(interval)
            result = await self._request("GET", poll_url)
            if result.get("status") == "completed":
                return self._parse(result)
            if result.get("status") == "failed":
                raise APIError(500, result.get("error", "Generation failed"), result)

    @staticmethod
    def _parse(data: dict) -> ImageResponse:
        images = data.get("data", [])
        if images:
            img = images[0]
            return ImageResponse(url=img.get("url", ""), b64_json=img.get("b64_json", ""), revised_prompt=img.get("revised_prompt", ""), raw=data)
        if data.get("url"):
            return ImageResponse(url=data["url"], raw=data)
        return ImageResponse(raw=data)


# ─── Video ────────────────────────────────────────────────────

class AsyncVideoClient(AsyncBaseClient):
    """Async video generation."""

    async def generate(self, prompt: str, *, model: str | None = None, duration: int = 5, wait: bool = True, poll_interval: float = 5.0, poll_timeout: float = 600.0, **kwargs) -> VideoJob:
        model = model or "auto/video"
        data = await self._post("/v1/videos/generations", json={"model": model, "prompt": prompt, "duration": duration, **kwargs})
        job = VideoJob(id=data.get("id", ""), status=data.get("status", "in_progress"), url=_extract_video_url_async(data), raw=data)
        if not wait or job.status == "completed" or job.url:
            return job
        return await self._poll(job.id, poll_interval, poll_timeout)

    async def status(self, job_id: str) -> VideoJob:
        data = await self._get(f"/v1/videos/generations/{job_id}")
        return VideoJob(id=data.get("id", job_id), status=data.get("status", ""), url=_extract_video_url_async(data), raw=data)

    async def _poll(self, job_id: str, interval: float, timeout: float) -> VideoJob:
        start = time.monotonic()
        last_raw: dict = {}
        while True:
            if time.monotonic() - start >= timeout:
                return VideoJob(id=job_id, status="timeout", raw=last_raw or {"error": "Poll timeout"})
            await asyncio.sleep(interval)
            job = await self.status(job_id)
            last_raw = job.raw
            if job.status == "completed":
                return job
            if job.status == "failed":
                raise APIError(500, "Video generation failed", job.raw)


# ─── Audio ────────────────────────────────────────────────────

class AsyncAudioClient(AsyncBaseClient):
    """Async audio client."""

    async def music(self, prompt: str, *, model: str | None = None, instrumental: bool = False, **kwargs) -> AudioResponse:
        model = model or "auto/music"
        resp = await self._post_raw("/v1/audio/generations", json={"model": model, "prompt": prompt, "instrumental": instrumental, **kwargs}, timeout=300)
        # Some providers return JSON with a URL instead of raw audio
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = _json.loads(resp.content)
                items = data.get("data", [])
                if items and isinstance(items[0], dict) and items[0].get("url"):
                    audio_url = items[0]["url"]
                    audio_resp = await self._client.get(audio_url, timeout=60)
                    return AudioResponse(
                        content=audio_resp.content,
                        content_type=audio_resp.headers.get("content-type", "audio/mpeg"),
                    )
            except Exception:
                pass
        return AudioResponse(content=resp.content, content_type=content_type or "audio/mpeg")

    async def speech(self, text: str, *, model: str = "auto/tts", voice: str = "sarah") -> AudioResponse:
        resp = await self._post_raw("/v1/audio/speech", json={"model": model, "input": text, "voice": voice})
        # BlockRun returns JSON with URL instead of raw audio
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = _json.loads(resp.content)
                items = data.get("data", [])
                if items and isinstance(items[0], dict) and items[0].get("url"):
                    audio_url = items[0]["url"]
                    audio_resp = await self._client.get(audio_url, timeout=60)
                    return AudioResponse(
                        content=audio_resp.content,
                        content_type=audio_resp.headers.get("content-type", "audio/mpeg"),
                    )
            except Exception:
                pass
        return AudioResponse(content=resp.content, content_type=content_type or "audio/mpeg")

    async def transcribe(self, file, *, model: str = "whisper-1", language: str | None = None) -> str:
        """Transcribe audio to text.

        Args:
            file: Audio file (file-like object or path).
            model: Transcription model. Defaults to "whisper-1".
            language: Optional language hint (ISO 639-1, e.g. "en").
        """
        data_fields: dict = {"model": model}
        if language:
            data_fields["language"] = language
        resp = await self._post_raw(
            "/v1/audio/transcriptions",
            data=data_fields,
            files={"file": file},
        )
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            result = resp.json()
            return result.get("text", "")
        return resp.text



# ─── Search ───────────────────────────────────────────────────

class AsyncSearchClient(AsyncBaseClient):
    """Async search client."""

    async def query(self, query: str, *, num_results: int = 10) -> list[SearchResult]:
        data = await self._post("/v1/search", json={
            "model": "auto/search",
            "messages": [{"role": "user", "content": query}],
            "max_results": num_results,
        })
        # Structured results
        results = data.get("results", data.get("data", []))
        if isinstance(results, list) and results:
            return [SearchResult(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("snippet", r.get("text", ""))) for r in results if isinstance(r, dict)]
        # Search-summary format
        summary = data.get("summary", "")
        if summary:
            citations = data.get("citations", [])
            if isinstance(citations, list) and citations:
                return [SearchResult(title=c.get("title", ""), url=c.get("url", ""), snippet=c.get("snippet", c.get("text", ""))) for c in citations if isinstance(c, dict)]
            return [SearchResult(title="Search Result", url="", snippet=summary)]
        # Chat completion format
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            if content:
                return [SearchResult(title="Search Result", url="", snippet=content)]
        return []

    async def find_similar(self, url: str, *, num_results: int = 10) -> list[SearchResult]:
        data = await self._post("/v1/marketplace/exa/find-similar", json={
            "url": url,
            "numResults": num_results,
        })
        results = data.get("results", data.get("data", []))
        if results:
            return [SearchResult(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("text", r.get("snippet", ""))) for r in results]
        return []

    async def contents(self, urls: list[str]) -> list[Any]:
        data = await self._post("/v1/marketplace/exa/contents", json={
            "ids": urls,
        })
        return data.get("results", data.get("data", []))


# ─── Marketplace ─────────────────────────────────────────────

class AsyncMarketplaceClient(AsyncBaseClient):
    """Async marketplace client for generic service calls."""

    async def call(self, service: str, path: str, *, method: str = "GET", **kwargs) -> Any:
        """Make a generic marketplace API call.

        Args:
            service: Service name (e.g., "polymarket", "dex", "phone").
            path: API path within the service.
            method: HTTP method (GET, POST, PUT, DELETE, PATCH).
            **kwargs: Additional request params (json, data, params, etc.).
        """
        full_path = f"/v1/marketplace/{service.strip('/')}/{path.lstrip('/')}"
        m = method.upper()
        if m == "GET":
            return await self._get(full_path, **kwargs)
        if m == "POST":
            return await self._post(full_path, **kwargs)
        # PUT, DELETE, PATCH, etc.
        return await self._request(m, full_path, **kwargs)

    async def rpc_call(self, chain: str, method: str, params: Any = None) -> Any:
        """Send a JSON-RPC 2.0 request to a blockchain."""
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
        return await self.call("rpc", chain, method="POST", json=body)


def _extract_video_url_async(data: dict) -> str:
    """Extract video URL from response — handles both top-level and nested formats."""
    url = data.get("url", "")
    if url:
        return url
    items = data.get("data")
    if isinstance(items, list) and len(items) > 0:
        url = items[0].get("url", "") if isinstance(items[0], dict) else ""
        if url:
            return url
    return ""


# ─── Wallet ───────────────────────────────────────────────────

class AsyncWalletClient(AsyncBaseClient):
    """Async wallet management client."""

    async def balance(self) -> dict[str, Any]:
        """Get the HD wallet's on-chain USDC balance (Base + Solana).

        Returns dict with:
            - balance_usd (str): Base + Solana total, decimal string
            - wallets (dict): {"base": {...}, "solana": {...}}, each with
              "usdc" and "address"

        Account quota is deliberately excluded: x402 settles against the wallet
        and never debits quota.
        """
        return await self._get("/v1/wallet/balance")

    async def total_usd(self) -> float:
        """Get balance()["balance_usd"] as a float, or 0.0 if unparseable."""
        data = await self.balance()
        try:
            return float(data.get("balance_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    async def history(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        """Get transaction history. page is 1-based; page_size caps at 100.

        Returns dict with: transactions, total, page. Each transaction's
        amount_quota is negated spend, so normally negative.
        """
        return await self._get(f"/v1/wallet/history?page={page}&page_size={page_size}")

    async def limits(self) -> dict[str, Any]:
        """Get spending limits.

        Returns dict with: user_id, daily_max_usd, per_request_max_usd,
        monthly_max_usd, auto_pause_below_usd, pool_allocation, updated_at
        """
        return await self._get("/v1/wallet/limits")

    async def update_limits(self, data: dict[str, Any]) -> dict[str, Any]:
        """Replace the spending limits.

        WARNING: full replacement, not a patch. The server writes the whole row,
        so any field you omit is stored as 0 — including pool_allocation, which
        makes pools() fall back to defaults. Use set_limit() to change one value.

        Returns dict with: success
        """
        return await self._put("/v1/wallet/limits", json=data)

    async def set_limit(self, **changes: Any) -> dict[str, Any]:
        """Change specific limits, preserving the rest (read-modify-write).

        Example:
            await wallet.set_limit(daily_max_usd=30)
        """
        current = dict(await self.limits())
        current.pop("updated_at", None)
        current.update(changes)
        return await self.update_limits(current)

    async def pools(self) -> dict[str, Any]:
        """Get pool allocation ratios and the resulting balances.

        Returns dict with allocation and pool_balances, both keyed by
        operations / insurance / savings / dividends. Pools are slices of the
        same on-chain balance balance() reports, not separate accounts.
        """
        return await self._get("/v1/wallet/pools")


# ─── Intent ───────────────────────────────────────────────────

class AsyncIntentClient(AsyncBaseClient):
    """Async AIP Intent Protocol client. Resolve, execute, and budget-manage AI intents."""

    async def resolve(
        self,
        intent: str,
        *,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve an intent to ranked provider matches.

        Args:
            intent: Intent type (e.g. "chat_completion", "image_generation")
            constraints: Optional dict with max_price_usd, max_latency_ms, features
            preferences: Optional dict with optimize_for, limit

        Returns dict with: matches, intent_type, total_available
        """
        body: dict[str, Any] = {"intent": intent}
        if constraints:
            body["constraints"] = constraints
        if preferences:
            body["preferences"] = preferences
        return await self._post("/v1/intent/resolve", json=body)

    async def execute(
        self,
        intent: str,
        payload: dict[str, Any],
        *,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve and execute an intent, returning the raw provider response.

        Args:
            intent: Intent type
            payload: Opaque request body forwarded to the resolved provider
            constraints: Optional filtering constraints
            preferences: Optional optimization preferences

        Returns: Raw upstream provider response as dict
        """
        body: dict[str, Any] = {"intent": intent, "payload": payload}
        if constraints:
            body["constraints"] = constraints
        if preferences:
            body["preferences"] = preferences
        return await self._post("/v1/intent/execute", json=body)

    async def execute_budget(
        self,
        intent: str,
        payload: dict[str, Any],
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an intent with budget control and settlement tracking.

        Args:
            intent: Intent type
            payload: Opaque request body forwarded to provider
            budget: Dict with max_total_usd (required), preferred_payment_method, allow_overdraft

        Returns dict with: request_id, status, provider, model, result,
            actual_cost_usd, settlement, risk_level, duration_ms, reason
        """
        body: dict[str, Any] = {
            "intent": intent,
            "payload": payload,
            "budget": budget,
        }
        return await self._post("/v1/intent/execute-budget", json=body)

    async def audit(self) -> dict[str, Any]:
        """Get the audit trail for recent requests.

        Returns dict with: entries, count
        """
        return await self._get("/v1/intent/audit")

    async def types(self) -> list[str]:
        """List supported intent types.

        Returns list of intent type strings.
        """
        data = await self._get("/v1/intent/types")
        return data["intent_types"]

    async def providers(self) -> dict[str, Any]:
        """List all registered providers.

        Returns dict with: providers, total
        """
        return await self._get("/v1/providers")

    async def discover(
        self,
        *,
        intent: str | None = None,
        features: list[str] | None = None,
        max_price: float | None = None,
    ) -> dict[str, Any]:
        """Discover the intents and providers this gateway and its peers serve.

        Returns dict with: intents, providers, federated, total.
        `total` counts providers only.
        """
        body: dict[str, Any] = {}
        if intent is not None:
            body["intent"] = intent
        if features:
            body["features"] = features
        if max_price is not None:
            body["max_price"] = max_price
        return await self._post("/v1/intent/discover", json=body)

    async def resolve_natural(
        self,
        query: str,
        *,
        session_id: str | None = None,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve a free-text request to an intent and ranked providers.

        Returns dict with status ("resolved" | "clarify" | "budget_insufficient"
        | "no_match"), session_id, intent, confidence, matches, clarify, message.
        """
        if not query or not query.strip():
            raise ValueError("query is required")
        body: dict[str, Any] = {"query": query}
        if session_id is not None:
            body["session_id"] = session_id
        if constraints is not None:
            body["constraints"] = constraints
        if preferences is not None:
            body["preferences"] = preferences
        return await self._post("/v1/intent/resolve/natural", json=body)

    async def spend(
        self,
        *,
        period: str = "7d",
        group_by: list[str] | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get aggregated spend and settlement rows.

        The old /v1/aip/analytics/* endpoints were removed; this reads
        /api/analytics/aggregate, where AIP usage appears with api_source="aip".
        Scope comes from the auth context — a non-admin only sees their own rows.

        Args:
            period: "24h", "7d" (default), "30d" or "90d".
            group_by: Any of "day", "model", "api_source", "principal_type",
                "channel", "group", "client_id".
            model: Restrict to one model name.
        """
        query = f"period={period}"
        if group_by:
            query += "&group_by=" + ",".join(group_by)
        if model:
            query += f"&model={model}"
        data = await self._get(f"/api/analytics/aggregate?{query}")
        if not data.get("success", True):
            raise APIError(200, data.get("message", "analytics request failed"), data)
        return data.get("data") or []

    async def subscribe(
        self,
        intent: str,
        payload: dict[str, Any],
        *,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
        optimize_for: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute an intent with the response streamed back over SSE.

        Yields dicts with 'event' and 'data'. The first event is "metadata" and
        the last is "done"; in between the gateway relays upstream events
        verbatim, so 'data' may be an OpenAI-style chunk dict or the literal
        "[DONE]" string.

        This endpoint takes no budget — use execute_budget() for a spend cap.
        """
        if not payload:
            raise ValueError("payload is required")
        body: dict[str, Any] = {"intent": intent, "payload": payload}
        if constraints is not None:
            body["constraints"] = constraints
        if preferences is not None:
            body["preferences"] = preferences
        if optimize_for is not None:
            body["optimize_for"] = optimize_for

        # Must use client.stream, not _post_raw: the latter reads the whole body
        # before returning, so events would arrive in one batch at the end.
        headers = self._auth.prepare_headers({})
        url = self.base_url + "/v1/intent/subscribe"

        event_type: str | None = None
        data_lines: list[str] = []

        def _emit() -> dict[str, Any]:
            raw = "\n".join(data_lines)
            try:
                return {"event": event_type or "message", "data": _json.loads(raw)}
            except (ValueError, TypeError):
                return {"event": event_type or "message", "data": raw}

        async with self._client.stream(
            "POST", url, json=body, headers=headers, timeout=None
        ) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                self._raise_for_stream_status(resp)

            async for line in resp.aiter_lines():
                line = (line or "").rstrip("\r")
                if line == "":
                    if event_type is not None or data_lines:
                        yield _emit()
                        event_type = None
                        data_lines = []
                    continue
                if line.startswith(":"):
                    continue
                name, sep, value = line.partition(":")
                if not sep:
                    continue
                if value.startswith(" "):
                    value = value[1:]
                if name == "event":
                    event_type = value
                elif name == "data":
                    data_lines.append(value)

        if event_type is not None or data_lines:
            yield _emit()

    async def list_subscriptions(self) -> dict[str, Any]:
        """List active subscriptions for the authenticated user."""
        return await self._get("/v1/intent/subscribe")

    async def unsubscribe(self, subscription_id: str) -> dict[str, Any]:
        """Cancel an active subscription."""
        if not subscription_id:
            raise ValueError("subscription_id is required")
        return await self._request("DELETE", f"/v1/intent/subscribe/{subscription_id}")

    async def network_stats(self) -> dict[str, Any]:
        """Get provider and network counts. Public, no auth required.

        Returns total_providers, by_source, intent_types (a count) and
        network counts. The {"success", "data"} envelope is unwrapped.
        """
        resp = await self._get("/v1/network/stats")
        if isinstance(resp, dict) and "data" in resp:
            return resp["data"]
        return resp