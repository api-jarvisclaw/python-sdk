"""OpenAI-compatible shim — drop-in replacement for openai.OpenAI().

Usage:
    # Replace:  from openai import OpenAI
    # With:     from jarvisclaw.openai_compat import OpenAI

    client = OpenAI(api_key="sk-...")  # or uses JARVISCLAW_API_KEY
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
    )
    print(resp.choices[0].message.content)

This gives you instant AIP benefits (intent routing, x402, budget) with zero code changes.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Generator, Optional

from ._base import BaseClient


# ═══════════════════════════════════════════════════════════════════
# Response dataclasses (mimics openai SDK structure)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class FunctionCall:
    name: str
    arguments: str


@dataclass
class ToolCall:
    id: str
    type: str = "function"
    function: FunctionCall = None


@dataclass
class Message:
    role: str
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None

    def __getitem__(self, key):
        return getattr(self, key)


@dataclass
class Choice:
    index: int
    message: Message
    finish_reason: str

    def __getitem__(self, key):
        return getattr(self, key)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatCompletion:
    id: str = ""
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: list[Choice] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    def __getitem__(self, key):
        return getattr(self, key)


@dataclass
class DeltaMessage:
    role: Optional[str] = None
    content: Optional[str] = None


@dataclass
class StreamChoice:
    index: int
    delta: DeltaMessage
    finish_reason: Optional[str] = None


@dataclass
class ChatCompletionChunk:
    id: str = ""
    object: str = "chat.completion.chunk"
    created: int = 0
    model: str = ""
    choices: list[StreamChoice] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# Chat Completions resource
# ═══════════════════════════════════════════════════════════════════

class Completions:
    """Mimics openai.chat.completions interface."""

    def __init__(self, client: "OpenAI"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs,
    ) -> ChatCompletion | Generator[ChatCompletionChunk, None, None]:
        """Create a chat completion — identical to openai API."""
        payload = {"model": model, "messages": messages, **kwargs}

        if stream:
            return self._stream(payload)

        resp = self._client._request("POST", "/v1/chat/completions", json=payload)
        return self._parse_response(resp)

    def _stream(self, payload: dict) -> Generator[ChatCompletionChunk, None, None]:
        payload["stream"] = True
        resp = self._client._post_raw("/v1/chat/completions", json=payload, stream=True)
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk_data = json.loads(data_str)
                yield self._parse_chunk(chunk_data)
            except json.JSONDecodeError:
                continue

    @staticmethod
    def _parse_response(data: dict) -> ChatCompletion:
        choices = []
        for c in data.get("choices", []):
            msg = c.get("message", {})
            tool_calls = None
            if msg.get("tool_calls"):
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        type=tc.get("type", "function"),
                        function=FunctionCall(
                            name=tc["function"]["name"],
                            arguments=tc["function"].get("arguments", "{}"),
                        ),
                    )
                    for tc in msg["tool_calls"]
                ]
            message = Message(
                role=msg.get("role", "assistant"),
                content=msg.get("content"),
                tool_calls=tool_calls,
            )
            choices.append(Choice(
                index=c.get("index", 0),
                message=message,
                finish_reason=c.get("finish_reason", "stop"),
            ))

        usage_data = data.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        return ChatCompletion(
            id=data.get("id", ""),
            object=data.get("object", "chat.completion"),
            created=data.get("created", int(time.time())),
            model=data.get("model", ""),
            choices=choices,
            usage=usage,
        )

    @staticmethod
    def _parse_chunk(data: dict) -> ChatCompletionChunk:
        choices = []
        for c in data.get("choices", []):
            delta = c.get("delta", {})
            choices.append(StreamChoice(
                index=c.get("index", 0),
                delta=DeltaMessage(
                    role=delta.get("role"),
                    content=delta.get("content"),
                ),
                finish_reason=c.get("finish_reason"),
            ))
        return ChatCompletionChunk(
            id=data.get("id", ""),
            object=data.get("object", "chat.completion.chunk"),
            created=data.get("created", int(time.time())),
            model=data.get("model", ""),
            choices=choices,
        )


class Chat:
    """Mimics openai.chat namespace."""

    def __init__(self, client: "OpenAI"):
        self.completions = Completions(client)


# ═══════════════════════════════════════════════════════════════════
# Main OpenAI-compatible client
# ═══════════════════════════════════════════════════════════════════

class OpenAI(BaseClient):
    """Drop-in replacement for openai.OpenAI() — routes through AIP protocol.

    All the benefits of AIP (intent routing, x402 payment, provider fallback)
    with zero code changes from OpenAI SDK usage.

    Usage:
        from jarvisclaw.openai_compat import OpenAI

        client = OpenAI(api_key="sk-...")
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
        )
        print(resp.choices[0].message.content)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        private_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 120,
        network: str | None = None,
    ):
        super().__init__(
            api_key=api_key,
            private_key=private_key,
            base_url=base_url,
            timeout=timeout,
            network=network,
        )
        self.chat = Chat(self)
