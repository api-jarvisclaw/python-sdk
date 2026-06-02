"""JarvisClaw LLM Client — full-feature SDK."""
from __future__ import annotations

import os
from typing import Any, Generator

import requests

from .auth import APIKeyAuth, AuthStrategy, X402Auth
from .errors import (
    APIError,
    AuthenticationError,
    InsufficientBalanceError,
    RateLimitError,
)
from .streaming import stream_chat_response
from .types import (
    AudioResponse,
    ChatResponse,
    ImageResponse,
    Model,
    SearchResult,
    VideoJob,
)

DEFAULT_BASE_URL = "https://api.jarvisclaw.ai"


class LLMClient:
    """JarvisClaw AI client. Supports API Key and x402 Agent authentication.

    Usage:
        # API Key mode
        client = LLMClient(api_key="sk-...")

        # x402 Agent mode (requires: pip install jarvisclaw[agent])
        client = LLMClient(private_key="0x...")

        # Chat
        print(client.chat("auto", "Hello!"))

        # Streaming
        for chunk in client.chat_stream("auto", "Hello!"):
            print(chunk, end="")
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        private_key: str | None = None,
        base_url: str | None = None,
        network: str = "eip155:8453",
        timeout: int = 120,
    ):
        if api_key:
            self._auth: AuthStrategy = APIKeyAuth(api_key)
        elif private_key:
            self._auth = X402Auth(private_key, network)
        else:
            env_key = os.environ.get("JARVISCLAW_API_KEY")
            env_pk = os.environ.get("JARVISCLAW_WALLET_KEY")
            if env_key:
                self._auth = APIKeyAuth(env_key)
            elif env_pk:
                self._auth = X402Auth(env_pk, network)
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
        self._total_spent = 0.0

    @property
    def address(self) -> str | None:
        """Wallet address (x402 mode only)."""
        return self._auth.address

    # ─── Chat ───────────────────────────────────────────────

    def chat(
        self,
        model: str,
        message: str,
        *,
        system: str | None = None,
        temperature: float = 0.7,
    ) -> str:
        """Simple chat — returns response text directly."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})
        resp = self.chat_completion(model, messages, temperature=temperature)
        return resp.content

    def chat_completion(
        self, model: str, messages: list[dict], **kwargs
    ) -> ChatResponse:
        """Full chat completion — returns ChatResponse with metadata."""
        body: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
        data = self._post("/v1/chat/completions", json=body)
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            id=data.get("id", ""),
            usage=data.get("usage", {}),
            raw=data,
        )

    def chat_stream(
        self,
        model: str,
        message: str,
        *,
        system: str | None = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        """Streaming chat — yields text chunks."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        resp = self._post_raw("/v1/chat/completions", json=body, stream=True)
        yield from stream_chat_response(resp)

    def smart_chat(self, message: str, **kwargs) -> str:
        """Smart Router — auto-selects cheapest capable model."""
        return self.chat("auto", message, **kwargs)

    # ─── Images ─────────────────────────────────────────────

    def image_generate(
        self, model: str, prompt: str, *, size: str = "1024x1024", n: int = 1
    ) -> ImageResponse:
        """Generate an image."""
        data = self._post(
            "/v1/images/generations",
            json={"model": model, "prompt": prompt, "size": size, "n": n},
        )
        images = data.get("data", [])
        if images:
            img = images[0]
            return ImageResponse(
                url=img.get("url", ""),
                b64_json=img.get("b64_json", ""),
                revised_prompt=img.get("revised_prompt", ""),
                raw=data,
            )
        return ImageResponse(raw=data)

    # ─── Video ──────────────────────────────────────────────

    def video_generate(
        self, model: str, *, prompt: str, duration: int = 5, **kwargs
    ) -> VideoJob:
        """Submit video generation job."""
        body = {"model": model, "prompt": prompt, "duration": duration, **kwargs}
        data = self._post("/v1/videos/generations", json=body)
        return VideoJob(
            id=data.get("id", ""),
            status=data.get("status", "in_progress"),
            raw=data,
        )

    def video_status(self, job_id: str) -> VideoJob:
        """Check video generation status."""
        data = self._get(f"/v1/videos/generations/{job_id}")
        return VideoJob(
            id=data.get("id", job_id),
            status=data.get("status", ""),
            url=data.get("url", ""),
            raw=data,
        )

    # ─── Audio ──────────────────────────────────────────────

    def audio_speech(
        self, model: str, text: str, *, voice: str = "alloy"
    ) -> AudioResponse:
        """Text-to-speech — returns audio bytes."""
        resp = self._post_raw(
            "/v1/audio/speech",
            json={"model": model, "input": text, "voice": voice},
        )
        return AudioResponse(
            content=resp.content,
            content_type=resp.headers.get("content-type", "audio/mpeg"),
        )

    def audio_transcribe(self, audio_file, *, model: str = "whisper-1") -> str:
        """Speech-to-text — returns transcript text."""
        data = self._post(
            "/v1/audio/transcriptions",
            files={"file": audio_file},
            data={"model": model},
        )
        return data.get("text", "")

    # ─── Search ─────────────────────────────────────────────

    def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        """Web search."""
        data = self._post(
            "/v1/search", json={"query": query, "max_results": max_results}
        )
        results = data.get("results", data.get("data", []))
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("snippet", ""),
            )
            for r in results
        ]

    # ─── Prediction Market ──────────────────────────────────

    def prediction(self, path: str, *, method: str = "GET", **kwargs) -> Any:
        """Prediction market API — pass path like 'polymarket/markets'."""
        full_path = f"/v1/prediction/{path.lstrip('/')}"
        if method.upper() == "GET":
            return self._get(full_path, **kwargs)
        return self._post(full_path, **kwargs)

    # ─── Models ─────────────────────────────────────────────

    def list_models(self) -> list[Model]:
        """List available models."""
        data = self._get("/v1/models")
        models = data.get("data", [])
        return [
            Model(
                id=m.get("id", ""),
                object=m.get("object", "model"),
                owned_by=m.get("owned_by", ""),
            )
            for m in models
        ]

    # ─── Utility ────────────────────────────────────────────

    def get_spending(self) -> float:
        """Total USD spent in this session (tracked locally)."""
        return self._total_spent

    # ─── Internal ───────────────────────────────────────────

    def _get(self, path: str, **kwargs) -> Any:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs) -> Any:
        return self._request("POST", path, **kwargs)

    def _post_raw(self, path: str, **kwargs) -> requests.Response:
        return self._request_raw("POST", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = self._request_raw(method, path, **kwargs)
        return resp.json()

    def _request_raw(self, method: str, path: str, **kwargs) -> requests.Response:
        url = self.base_url + path
        kwargs.setdefault("timeout", self.timeout)
        stream = kwargs.pop("stream", False)

        headers = kwargs.pop("headers", {}) or {}
        headers = self._auth.prepare_headers(headers)
        kwargs["headers"] = headers

        resp = self._session.request(method, url, stream=stream, **kwargs)

        # Handle 402 (x402 payment flow)
        if resp.status_code == 402:
            retry = self._auth.handle_402(
                resp, method, url, self._session, stream=stream, **kwargs
            )
            if retry is None:
                body = {}
                try:
                    body = resp.json()
                except Exception:
                    pass
                raise InsufficientBalanceError(
                    402, "Insufficient balance", body
                )
            resp = retry

        # Error handling
        if resp.status_code == 401:
            body = self._safe_json(resp)
            raise AuthenticationError(
                401, body.get("message", "Unauthorized"), body
            )
        if resp.status_code == 429:
            body = self._safe_json(resp)
            raise RateLimitError(
                429, body.get("message", "Rate limit exceeded"), body
            )
        if resp.status_code >= 400:
            body = self._safe_json(resp)
            raise APIError(
                resp.status_code,
                body.get("message", resp.reason or "Unknown error"),
                body,
            )

        return resp

    @staticmethod
    def _safe_json(resp: requests.Response) -> dict:
        try:
            return resp.json()
        except Exception:
            return {}
