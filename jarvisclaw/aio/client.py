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

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = await self._request_raw(method, path, **kwargs)
        return resp.json()

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

            resp = await self._client.request(method, url, timeout=req_timeout, **kwargs)

            if resp.status_code == 402:
                retry_resp = await self._handle_402(resp, method, url, req_timeout, **kwargs)
                if retry_resp is None:
                    raise InsufficientBalanceError(402, "Insufficient balance", {})
                resp = retry_resp
                if resp.status_code >= 400:
                    body = self._safe_json(resp)
                    raise APIError(resp.status_code, body.get("error", {}).get("message", "Error"), body)

            if resp.status_code in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                continue
            if resp.status_code == 401:
                raise AuthenticationError(401, "Unauthorized", {})
            if resp.status_code == 429:
                raise RateLimitError(429, "Rate limit exceeded", {})
            if resp.status_code >= 400:
                body = self._safe_json(resp)
                raise APIError(resp.status_code, body.get("error", {}).get("message", "Error"), body)
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
        return await self._client.request(method, url, headers=headers, timeout=req_timeout, **kwargs)

    @staticmethod
    def _safe_json(resp) -> dict:
        try:
            return resp.json()
        except Exception:
            return {}


# ─── Chat ─────────────────────────────────────────────────────

class AsyncChatClient(AsyncBaseClient):
    """Async chat completions."""

    async def complete(self, message: str, *, model: str | None = None, system: str | None = None, temperature: float = 0.7) -> str:
        resp = await self.completion(self._build_messages(message, system), model=model, temperature=temperature)
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
            # Check for errors before parsing SSE
            if resp.status_code == 401:
                await resp.aread()
                raise AuthenticationError(401, "Unauthorized", {})
            if resp.status_code == 402:
                await resp.aread()
                # Try x402 payment and fall back to non-streaming
                if self._auth.supports_x402():
                    raise InsufficientBalanceError(
                        402, "x402 streaming not supported — use complete() for paid requests", {}
                    )
                raise InsufficientBalanceError(402, "Insufficient balance", {})
            if resp.status_code == 429:
                await resp.aread()
                raise RateLimitError(429, "Rate limit exceeded", {})
            if resp.status_code >= 400:
                await resp.aread()
                body_data = self._safe_json(resp)
                msg = body_data.get("error", {}).get("message", f"Error {resp.status_code}")
                raise APIError(resp.status_code, msg, body_data)

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    return
                try:
                    chunk = _json.loads(data)
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
        while True:
            if time.monotonic() - start >= timeout:
                return VideoJob(id=job_id, status="timeout", raw={"error": "Poll timeout"})
            await asyncio.sleep(interval)
            job = await self.status(job_id)
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
        # Response is chat completion format — extract structured results or content
        results = data.get("results", data.get("data", []))
        if results:
            return [SearchResult(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("snippet", "")) for r in results]
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        if content:
            return [SearchResult(title="Search Result", url="", snippet=content)]
        return []

    async def find_similar(self, url: str, *, num_results: int = 10) -> list[SearchResult]:
        data = await self._post("/v1/marketplace/exa/findSimilar", json={
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