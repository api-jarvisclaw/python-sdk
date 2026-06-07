"""ChatClient — text chat completions with smart routing."""
from __future__ import annotations

from typing import Any, Generator

from ._base import BaseClient
from .streaming import stream_chat_response
from .types import ChatResponse


class ChatClient(BaseClient):
    """Chat completions client. Defaults to model='auto' (smart routing).

    Usage:
        from jarvisclaw import ChatClient

        chat = ChatClient(api_key="sk-...")
        print(chat.complete("Hello!"))
    """

    def complete(
        self,
        message: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
    ) -> str:
        """Simple chat — returns response text directly.

        Args:
            message: User message text.
            model: Model identifier. Defaults to "auto" (smart routing).
            system: Optional system prompt.
            temperature: Sampling temperature (0.0 - 2.0).
        """
        model = model or "auto"
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})
        resp = self.completion(messages, model=model, temperature=temperature)
        return resp.content

    def completion(
        self, messages: list[dict], *, model: str | None = None, **kwargs: Any
    ) -> ChatResponse:
        """Full chat completion — returns ChatResponse with metadata.

        Args:
            messages: List of message dicts (role/content).
            model: Model identifier. Defaults to "auto".
            **kwargs: Additional params passed to the API.
        """
        model = model or "auto"
        body: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
        data = self._post("/v1/chat/completions", json=body)

        # Handle search response format (auto/search returns {summary} not {choices})
        if "summary" in data and "choices" not in data:
            usage = data.get("usage", {})
            if usage:
                self._track_cost(model, "/v1/chat/completions", usage)
            return ChatResponse(
                content=data["summary"],
                model=data.get("model", model),
                id=data.get("id", ""),
                usage=usage,
                raw=data,
            )

        # Standard chat format
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        if usage:
            self._track_cost(model, "/v1/chat/completions", usage)
        return ChatResponse(
            content=content,
            model=data.get("model", model),
            id=data.get("id", ""),
            usage=usage,
            raw=data,
        )

    def stream(
        self,
        message: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        """Streaming chat — yields text chunks.

        Args:
            message: User message text.
            model: Model identifier. Defaults to "auto".
            system: Optional system prompt.
            temperature: Sampling temperature.
        """
        model = model or "auto"
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            **kwargs,
        }
        resp = self._post_raw("/v1/chat/completions", json=body, stream=True)
        yield from stream_chat_response(resp)
