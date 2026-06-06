"""VideoClient — video generation with smart routing."""
from __future__ import annotations

import time
from typing import Any

from ._base import BaseClient
from .types import VideoJob


class VideoClient(BaseClient):
    """Video generation client. Defaults to model='auto/video' (smart routing).

    Usage:
        from jarvisclaw import VideoClient

        video = VideoClient(private_key="0x...")
        job = video.generate("A cinematic sunset over the ocean")
        print(job.url)  # blocks until ready
    """

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        duration: int = 5,
        poll_interval: float = 5.0,
        poll_timeout: float = 600.0,
        wait: bool = True,
        **kwargs: Any,
    ) -> VideoJob:
        """Submit video generation job.

        By default, blocks until the video is ready. Set wait=False for
        async behavior (returns immediately, poll with status()).

        Args:
            prompt: Description of the video to generate.
            model: Model identifier. Defaults to "auto/video".
            duration: Video duration in seconds.
            poll_interval: Seconds between poll requests (default 5).
            poll_timeout: Max seconds to wait for completion (default 600).
            wait: If True (default), block until video is ready.
            **kwargs: Additional params (e.g., asset_id, real_face_asset_id).
        """
        model = model or "auto/video"
        body = {"model": model, "prompt": prompt, "duration": duration, **kwargs}
        data = self._post("/v1/videos/generations", json=body)

        job = VideoJob(
            id=data.get("id", ""),
            status=data.get("status", "in_progress"),
            url=_extract_video_url(data),
            raw=data,
        )

        # If already complete or user wants async, return immediately
        if not wait or job.status == "completed" or job.url:
            return job

        # Auto-poll until ready
        return self._poll_video_job(job.id, poll_interval, poll_timeout)

    def status(self, job_id: str) -> VideoJob:
        """Check video generation status (single check, non-blocking).

        Args:
            job_id: The job ID returned from generate().
        """
        data = self._get(f"/v1/videos/generations/{job_id}")
        return VideoJob(
            id=data.get("id", job_id),
            status=data.get("status", ""),
            url=_extract_video_url(data),
            raw=data,
        )

    def wait(
        self,
        job_id: str,
        *,
        poll_interval: float = 5.0,
        poll_timeout: float = 600.0,
    ) -> VideoJob:
        """Block until a video job completes. Use after generate(wait=False).

        Args:
            job_id: The job ID returned from generate(wait=False).
            poll_interval: Seconds between polls (default 5).
            poll_timeout: Max seconds to wait (default 600).

        Usage:
            job = video.generate("Ocean waves", wait=False)
            # ... do other work ...
            result = video.wait(job.id)
            print(result.url)
        """
        return self._poll_video_job(job_id, poll_interval, poll_timeout)

    def _poll_video_job(
        self, job_id: str, interval: float, timeout: float
    ) -> VideoJob:
        """Poll a video job until completion."""
        start = time.monotonic()

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return VideoJob(
                    id=job_id,
                    status="timeout",
                    raw={"error": "Poll timeout exceeded"},
                )

            time.sleep(interval)

            job = self.status(job_id)
            if job.status == "completed":
                return job
            if job.status == "failed":
                from .errors import APIError
                raise APIError(500, "Video generation failed", job.raw)
            if job.status not in ("completed", "failed", "queued", "in_progress", "timeout"):
                from .errors import APIError
                raise APIError(500, f"Unexpected job status: {job.status}", job.raw)


def _extract_video_url(data: dict) -> str:
    """Extract video URL from response — handles both top-level and nested formats.

    Some providers return {"url": "..."} at the top level,
    others nest it as {"data": [{"url": "..."}]}.
    """
    # Try top-level url first
    url = data.get("url", "")
    if url:
        return url
    # Try nested data[0].url (BlockRun/x402 format)
    items = data.get("data")
    if isinstance(items, list) and len(items) > 0:
        url = items[0].get("url", "") if isinstance(items[0], dict) else ""
        if url:
            return url
    return ""
