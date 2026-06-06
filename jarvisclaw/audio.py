"""AudioClient — music generation, speech synthesis, and transcription."""
from __future__ import annotations

import time
from typing import Any

from ._base import BaseClient
from .types import AudioResponse, MusicJob


class AudioClient(BaseClient):
    """Audio client for music generation, TTS, and transcription.

    Usage:
        from jarvisclaw import AudioClient

        audio = AudioClient(api_key="sk-...")
        result = audio.music("An upbeat electronic track")
        result = audio.speech("Hello world", voice="nova")
        text = audio.transcribe(open("recording.mp3", "rb"))
    """

    def music(
        self,
        prompt: str,
        *,
        model: str | None = None,
        instrumental: bool = False,
        wait: bool = True,
        **kwargs: Any,
    ) -> AudioResponse | MusicJob:
        """Generate music from a text prompt.

        Music generation takes 1-3 minutes. Set wait=False to return
        immediately with a MusicJob that can be resolved later.

        Args:
            prompt: Description of the music to generate.
            model: Model identifier. Defaults to "auto/music".
            instrumental: If True, generate without vocals.
            wait: If True (default), block until music is ready.
            **kwargs: Additional params passed to the API.
        """
        model = model or "auto/music"
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "instrumental": instrumental,
            **kwargs,
        }

        if not wait:
            return MusicJob._submit(self, "/v1/audio/generations", body)

        resp = self._post_raw("/v1/audio/generations", json=body, timeout=300)  # Music generation takes 1-3 minutes on upstream
        return AudioResponse(
            content=resp.content,
            content_type=resp.headers.get("content-type", "audio/mpeg"),
        )

    def speech(
        self,
        text: str,
        *,
        model: str = "auto/tts",
        voice: str = "alloy",
    ) -> AudioResponse:
        """Text-to-speech — returns audio bytes.

        Args:
            text: Text to synthesize.
            model: TTS model identifier.
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer).
        """
        resp = self._post_raw(
            "/v1/audio/speech",
            json={"model": model, "input": text, "voice": voice},
        )
        return AudioResponse(
            content=resp.content,
            content_type=resp.headers.get("content-type", "audio/mpeg"),
        )

    def transcribe(self, audio_file: Any, *, model: str = "whisper-1") -> str:
        """Speech-to-text — returns transcript text.

        Args:
            audio_file: Audio file (file-like object).
            model: Transcription model identifier.
        """
        data = self._post(
            "/v1/audio/transcriptions",
            files={"file": audio_file},
            data={"model": model},
        )
        return data.get("text", "")
