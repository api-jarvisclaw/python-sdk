"""Server-Sent Events (SSE) streaming parser for chat responses."""
from __future__ import annotations

import json
from typing import Generator


def stream_chat_response(resp) -> Generator[str, None, None]:
    """Parse SSE stream from chat completions endpoint, yielding text chunks.

    Handles OpenAI-format SSE:
        data: {"choices":[{"delta":{"content":"Hello"}}]}
        data: [DONE]
    """
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            return
        try:
            chunk = json.loads(data)
            choices = chunk.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
        except json.JSONDecodeError:
            continue


def stream_raw_events(resp) -> Generator[dict, None, None]:
    """Parse SSE stream yielding raw event dicts (for advanced usage)."""
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue
