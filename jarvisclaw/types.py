"""Response types for JarvisClaw SDK."""
from __future__ import annotations

import atexit
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._base import BaseClient

# Shared thread pool for non-blocking operations
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="jarvisclaw")
atexit.register(_pool.shutdown, wait=False)


@dataclass
class ChatResponse:
    """Response from chat/chat_completion."""
    content: str
    model: str = ""
    id: str = ""
    usage: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


@dataclass
class ImageResponse:
    """Response from image_generate."""
    url: str = ""
    b64_json: str = ""
    revised_prompt: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class VideoJob:
    """Response from video_generate."""
    id: str = ""
    status: str = ""
    url: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class AudioResponse:
    """Response from audio_speech."""
    content: bytes = b""
    content_type: str = "audio/mpeg"


@dataclass
class MusicJob:
    """Non-blocking music generation handle.

    Usage:
        job = audio.music("An electronic beat", wait=False)
        # ... do other work ...
        result = job.result()  # blocks until ready
    """
    _future: Future | None = field(default=None, repr=False)

    def result(self, timeout: float | None = 300) -> AudioResponse:
        """Block until the music is ready and return AudioResponse."""
        if self._future is None:
            raise RuntimeError("MusicJob has no pending operation")
        return self._future.result(timeout=timeout)

    @property
    def done(self) -> bool:
        """Check if generation has completed without blocking."""
        return self._future is not None and self._future.done()

    @classmethod
    def _submit(cls, client: BaseClient, path: str, body: dict[str, Any]) -> MusicJob:
        """Submit music generation in background thread."""
        def _do():
            resp = client._post_raw(path, json=body, timeout=300)
            # Some providers return JSON with a URL instead of raw audio
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    import json as _json
                    data = _json.loads(resp.content)
                    items = data.get("data", [])
                    if items and isinstance(items[0], dict) and items[0].get("url"):
                        audio_url = items[0]["url"]
                        import requests as _requests
                        audio_resp = _requests.get(audio_url, timeout=60)
                        audio_resp.raise_for_status()
                        return AudioResponse(
                            content=audio_resp.content,
                            content_type=audio_resp.headers.get("content-type", "audio/mpeg"),
                        )
                except Exception:
                    pass
            return AudioResponse(
                content=resp.content,
                content_type=content_type or "audio/mpeg",
            )
        future = _pool.submit(_do)
        return cls(_future=future)


@dataclass
class SearchResult:
    """Single search result."""
    title: str = ""
    url: str = ""
    snippet: str = ""


@dataclass
class Model:
    """Model info from list_models."""
    id: str = ""
    object: str = "model"
    owned_by: str = ""
