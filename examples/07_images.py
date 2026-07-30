"""Image generation — synchronous and async job polling.

Run: python examples/07_images.py

This is the only example that generates media, so it is the most expensive one.
It creates a single small image.
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from jarvisclaw import ImageClient
from jarvisclaw.errors import APIError

img = ImageClient(api_key=os.environ["JARVISCLAW_API_KEY"], timeout=180)

# --- Blocking generation ----------------------------------------------------
# By default generate() waits for the image and returns it. Some models answer
# immediately with a job id instead; the SDK polls those transparently, so
# either way you get a finished result here.
try:
    result = img.generate(
        "A single brass gear on a white background, product photo",
        model="openai/gpt-image-1",
        size="1024x1024",
    )
    print("URL:", result.url or "(returned inline)")
    if result.b64_json:
        print(f"Inline data: {len(result.b64_json)} base64 chars")
except APIError as e:
    print(f"Generation failed [{e.status_code}]: {e.message[:120]}")
    raise SystemExit(1)

# --- Async: submit now, collect later ---------------------------------------
# wait=False returns as soon as the job is accepted, so you can do other work.
job = img.generate(
    "A blueprint of a mechanical clock, blue ink on paper",
    model="openai/gpt-image-1",
    size="1024x1024",
    wait=False,
)

# An async submission carries the job id on .raw rather than as a field, since
# the same ImageResponse type covers both the queued and the finished case.
job_id = job.raw.get("id")
if job_id:
    print(f"\nJob {job_id} submitted, status={job.raw.get('status')!r}")
    # status() polls once and returns immediately; wait() blocks until the job
    # finishes or the timeout elapses.
    finished = img.wait(job_id, poll_interval=5, poll_timeout=300)
    print("Finished:", finished.url or "(inline)")
else:
    # The model answered synchronously despite wait=False.
    print("\nReturned inline instead of queueing:", job.url or "(inline data)")
