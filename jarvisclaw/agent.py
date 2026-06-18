"""High-level Agent class — one object for the full AIP + Treasury loop."""
from __future__ import annotations

import os
from typing import Any, Optional

from ._base import BaseClient, DEFAULT_BASE_URL


class Agent(BaseClient):
    """Unified agent: intent resolution + treasury budget + model execution.

    Usage:
        from jarvisclaw import Agent

        agent = Agent(api_key="sk-...")  # or private_key="0x..."
        result = agent.ask("explain quantum computing", budget=0.01, optimize="cost")
    """

    def __init__(self, *, api_key=None, private_key=None, base_url=None, timeout=120, network=None):
        super().__init__(api_key=api_key, private_key=private_key, base_url=base_url, timeout=timeout, network=network)
        self._treasury = None  # lazy init

    # ── Intent Resolution (calls /v1/intent/resolve) ──────────────────

    def resolve(self, intent: str, *, max_price: float | None = None,
                features: list[str] | None = None, optimize: str = "cost") -> dict:
        """Resolve an intent to the best provider match."""
        payload = {
            "intent": intent,
            "constraints": {},
            "preferences": {"optimize_for": optimize},
        }
        if max_price is not None:
            payload["constraints"]["max_price_usd"] = max_price
        if features:
            payload["constraints"]["features"] = features
        resp = self._request("POST", "/v1/intent/resolve", json=payload)
        return resp

    def list_providers(self) -> dict:
        """List all available providers."""
        return self._request("GET", "/v1/providers")

    def list_intent_types(self) -> list[str]:
        """List supported intent types."""
        resp = self._request("GET", "/v1/intent/types")
        return resp.get("intent_types", [])

    # ── Wallet / Treasury (calls /v1/wallet/*) ────────────────────────

    def balance(self) -> dict:
        """Get wallet balance (quota + HD wallet + subscription)."""
        return self._request("GET", "/v1/wallet/balance")

    def history(self, page: int = 1, page_size: int = 20, category: str | None = None) -> dict:
        """Get transaction history."""
        params = {"page": page, "page_size": page_size}
        if category:
            params["category"] = category
        return self._request("GET", "/v1/wallet/history", params=params)

    def get_limits(self) -> dict:
        """Get current spending limits."""
        return self._request("GET", "/v1/wallet/limits")

    def set_limits(self, *, daily_max_usd: float | None = None,
                   per_request_max_usd: float | None = None,
                   monthly_max_usd: float | None = None) -> dict:
        """Update spending limits."""
        payload = {}
        if daily_max_usd is not None:
            payload["daily_max_usd"] = daily_max_usd
        if per_request_max_usd is not None:
            payload["per_request_max_usd"] = per_request_max_usd
        if monthly_max_usd is not None:
            payload["monthly_max_usd"] = monthly_max_usd
        return self._request("PUT", "/v1/wallet/limits", json=payload)

    def pools(self) -> dict:
        """Get pool allocation and balances."""
        return self._request("GET", "/v1/wallet/pools")

    # ── High-level "ask" — resolve + execute in one call ──────────────

    def ask(self, prompt: str, *, budget: float = 0.05, optimize: str = "cost",
            model: str | None = None, **kwargs) -> str:
        """Ask a question: auto-resolve best model within budget, then call it.

        Args:
            prompt: The question/instruction
            budget: Max USD to spend on this request
            optimize: "cost", "quality", or "latency"
            model: Override model (skip resolve if provided)
            **kwargs: Extra params passed to chat completion

        Returns:
            The assistant's response text
        """
        if model is None:
            # Resolve best provider
            resolved = self.resolve("chat_completion", max_price=budget, optimize=optimize)
            matches = resolved.get("matches", [])
            if not matches:
                raise ValueError(f"No provider found within budget ${budget}")
            model = matches[0].get("model", matches[0].get("provider_id"))

        # Execute chat completion
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            **kwargs,
        }
        resp = self._request("POST", "/v1/chat/completions", json=payload)
        # Extract text from OpenAI-format response
        choices = resp.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""
