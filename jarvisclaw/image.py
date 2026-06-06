"""ImageClient — image generation and editing with smart routing."""
from __future__ import annotations

import time
from typing import Any

from ._base import BaseClient
from .types import ImageResponse


class ImageClient(BaseClient):
    """Image generation client. Defaults to model='auto/image' (smart routing).

    Usage:
        from jarvisclaw import ImageClient

        img = ImageClient(api_key="sk-...")
        result = img.generate("A watercolor painting of a mountain lake")
        print(result.url)
    """

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        size: str = "1024x1024",
        n: int = 1,
        wait: bool = True,
        poll_interval: float = 5.0,
        poll_timeout: float = 300.0,
    ) -> ImageResponse:
        """Generate an image from a text prompt.

        By default, blocks until the image is ready. Set wait=False for
        async behavior (returns immediately, poll with status()).

        Args:
            prompt: Description of the image to generate.
            model: Model identifier. Defaults to "auto/image" (smart routing).
            size: Image dimensions (e.g., "1024x1024", "1792x1024").
            n: Number of images to generate.
            wait: If True (default), block until image is ready.
            poll_interval: Seconds between poll requests (default 5).
            poll_timeout: Max seconds to wait for completion (default 300).
        """
        model = model or "auto/image"
        data = self._post(
            "/v1/images/generations",
            json={"model": model, "prompt": prompt, "size": size, "n": n},
        )

        # Synchronous response (fast model)
        if data.get("status") not in ("queued", "in_progress") or not data.get("poll_url"):
            return self._parse_image_response(data)

        # Async job response — return immediately if wait=False
        if not wait:
            return ImageResponse(raw=data)

        # Auto-poll until ready
        return self._poll_image_job(data, poll_interval, poll_timeout)

    def status(self, job_id: str) -> ImageResponse:
        """Check image generation job status (single check, non-blocking).

        Args:
            job_id: The job ID returned from generate(wait=False).raw["id"].
        """
        data = self._get(f"/v1/images/generations/{job_id}")
        if data.get("status") in ("queued", "in_progress"):
            return ImageResponse(raw=data)
        return self._parse_image_response(data)

    def wait(
        self,
        job_id: str,
        *,
        poll_interval: float = 5.0,
        poll_timeout: float = 300.0,
    ) -> ImageResponse:
        """Block until an image job completes. Use after generate(wait=False).

        Args:
            job_id: The job ID from generate(wait=False).raw["id"].
            poll_interval: Seconds between polls (default 5).
            poll_timeout: Max seconds to wait (default 300).

        Usage:
            job = image.generate("A cat", wait=False)
            # ... do other work ...
            result = image.wait(job.raw["id"])
            print(result.url)
        """
        initial = {"poll_url": f"/v1/images/generations/{job_id}", "id": job_id}
        return self._poll_image_job(initial, poll_interval, poll_timeout)

    def edit(
        self,
        image: Any,
        prompt: str,
        *,
        mask: Any | None = None,
        model: str | None = None,
    ) -> ImageResponse:
        """Edit an existing image with a text prompt.

        Args:
            image: Image file (file-like object or path).
            prompt: Description of the edit to apply.
            mask: Optional mask file indicating areas to edit.
            model: Model identifier. Defaults to "auto/image".
        """
        model = model or "auto/image"
        files: dict[str, Any] = {"image": image}
        if mask is not None:
            files["mask"] = mask
        data = self._post(
            "/v1/images/edits",
            files=files,
            data={"model": model, "prompt": prompt},
        )
        return self._parse_image_response(data)

    def _poll_image_job(
        self, initial_data: dict, interval: float, timeout: float
    ) -> ImageResponse:
        """Poll an async image job until completion."""
        poll_url = initial_data["poll_url"]
        start = time.monotonic()

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                return ImageResponse(raw=initial_data)

            time.sleep(interval)
            data = self._get(poll_url)
            status = data.get("status", "")

            if status == "completed":
                return self._parse_image_response(data)
            if status == "failed":
                from .errors import APIError
                raise APIError(500, data.get("error", "Image generation failed"), data)
            if status not in ("completed", "failed", "queued", "in_progress", ""):
                from .errors import APIError
                raise APIError(500, f"Unexpected job status: {status}", data)

    @staticmethod
    def _parse_image_response(data: dict) -> ImageResponse:
        """Parse standard or completed async image response."""
        images = data.get("data", [])
        if images:
            img = images[0]
            return ImageResponse(
                url=img.get("url", ""),
                b64_json=img.get("b64_json", ""),
                revised_prompt=img.get("revised_prompt", ""),
                raw=data,
            )
        if data.get("url"):
            return ImageResponse(
                url=data["url"],
                revised_prompt=data.get("revised_prompt", ""),
                raw=data,
            )
        return ImageResponse(raw=data)
