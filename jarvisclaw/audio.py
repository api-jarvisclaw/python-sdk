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

        # Some providers return JSON with a URL instead of raw audio
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = resp.json()
                # Format: {"data": [{"url": "https://...mp3"}]}
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
                pass  # Fall through to raw content

        return AudioResponse(
            content=resp.content,
            content_type=content_type or "audio/mpeg",
        )

    def speech(
        self,
        text: str,
        *,
        model: str = "auto/tts",
        voice: str = "sarah",
    ) -> AudioResponse:
        """Text-to-speech — returns audio bytes.

        Args:
            text: Text to synthesize.
            model: TTS model identifier.
            voice: Voice alias or ElevenLabs voice_id (sarah, george, etc.).
        """
        resp = self._post_raw(
            "/v1/audio/speech",
            json={"model": model, "input": text, "voice": voice},
        )

        # BlockRun returns JSON with URL instead of raw audio
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = resp.json()
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

    def transcribe(
        self,
        file: Any,
        *,
        model: str = "whisper-1",
        language: str | None = None,
        response_format: str | None = None,
    ) -> str:
        """Transcribe audio to text (speech-to-text).

        Args:
            file: Audio file (file-like object, e.g. open("audio.mp3", "rb")).
            model: Transcription model. Defaults to "whisper-1".
            language: Optional language hint (ISO 639-1 code, e.g. "en", "zh").
            response_format: Response format ("json", "text", "srt", "vtt").
                             Defaults to "json" (returns text string).
        """
        data_fields: dict[str, Any] = {"model": model}
        if language:
            data_fields["language"] = language
        if response_format:
            data_fields["response_format"] = response_format

        resp = self._post_raw(
            "/v1/audio/transcriptions",
            files={"file": file},
            data=data_fields,
        )

        # If response is plain text (srt, vtt, text formats)
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            result = resp.json()
            return result.get("text", "")
        return resp.text

