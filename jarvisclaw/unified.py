"""JarvisClaw — Unified SDK entry point.

This is the single public interface for all JarvisClaw AI operations.
It combines intent resolution, execution, streaming, analytics, and federation
into one cohesive client that matches the official documentation.

Usage:
    from jarvisclaw import JarvisClaw

    # API Key mode (managed billing)
    client = JarvisClaw(api_key="sk-...")

    # x402 mode (on-chain USDC settlement)
    client = JarvisClaw(private_key="0x...")

    # Resolve + Execute
    plan = client.resolve("chat_completion", constraints={"max_latency_ms": 3000})
    result = client.execute("chat_completion", payload={...}, budget={"max_total_usd": 0.05})

    # Streaming
    for chunk in client.stream("chat_completion", payload={...}):
        print(chunk["data"])
"""
from __future__ import annotations

from typing import Any, Generator

from ._base import BaseClient


class JarvisClaw(BaseClient):
    """Unified JarvisClaw AI client.

    Single entry point for the entire AIP (Agent Intent Protocol) surface:
    - resolve: find the best provider for an intent
    - execute: run an intent with budget control
    - stream: streaming execution via SSE
    - audit: usage analytics and budget tracking
    - discover: federation peer discovery
    - balance: check wallet/account balance

    Args:
        api_key: JarvisClaw API key (managed billing mode)
        private_key: Wallet private key for x402 on-chain settlement
        base_url: API base URL (default: https://api.jarvisclaw.ai)
        timeout: Request timeout in seconds (default: 120)
        network: Chain network — "evm" or "solana" (auto-detected if omitted)
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

    # ─── Intent Resolution ────────────────────────────────────────────────────────

    def resolve(
        self,
        intent: str,
        *,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve the best provider/model for an intent without executing.

        Args:
            intent: Intent type (e.g. "chat_completion", "image_generation",
                    "code_generation", "web_search", "tts", "transcription")
            constraints: Optional routing constraints:
                - max_latency_ms: Maximum acceptable latency
                - preferred_providers: List of preferred provider names
                - region: Geographic region preference
                - min_context_window: Minimum context window size

        Returns:
            Dict with: intent, provider, model, estimated_cost_usd,
            confidence, alternatives (list of fallback options)
        """
        body: dict[str, Any] = {"intent": intent}
        if constraints is not None:
            body["constraints"] = constraints
        return self._post("/v1/intent/resolve", json=body)

    # ─── Execution ────────────────────────────────────────────────────────────────

    def execute(
        self,
        intent: str,
        payload: dict[str, Any],
        *,
        budget: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an intent with budget control and settlement tracking.

        Args:
            intent: Intent type
            payload: Request body forwarded to provider. Structure depends on intent:
                - chat_completion: {"model": "...", "messages": [...]}
                - image_generation: {"prompt": "...", "size": "1024x1024"}
                - web_search: {"query": "..."}
                - code_generation: {"prompt": "...", "language": "python"}
                - tts: {"text": "...", "voice": "alloy"}
                - transcription: {"audio_url": "..."}
            budget: Budget constraints:
                - max_total_usd: Maximum spend for this request (required)
                - preferred_payment_method: "x402" or "api_key"
                - allow_overdraft: Whether to allow slight budget overflow
            constraints: Optional routing constraints (same as resolve)

        Returns:
            Dict with: request_id, status ("success"|"rejected"|"error"),
            provider, model, result, actual_cost_usd, settlement, duration_ms
        """
        body: dict[str, Any] = {
            "intent": intent,
            "payload": payload,
        }
        if budget is not None:
            body["budget"] = budget
        if constraints is not None:
            body["constraints"] = constraints
        return self._post("/v1/intent/execute", json=body)

    # ─── Streaming ────────────────────────────────────────────────────────────────

    def stream(
        self,
        intent: str,
        payload: dict[str, Any],
        *,
        budget: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Execute an intent with streaming response via SSE.

        Same parameters as execute(), but returns a generator of SSE events.

        Yields:
            Dict with 'event' and 'data' keys:
            - event="chunk": partial content (data.content has the text delta)
            - event="usage": token usage update
            - event="done": final settlement info (data.actual_cost_usd, data.settlement)
            - event="error": error occurred during streaming

        Example:
            for event in client.stream("chat_completion", payload={...}):
                if event["event"] == "chunk":
                    print(event["data"]["content"], end="", flush=True)
                elif event["event"] == "done":
                    print(f"\\nCost: ${event['data']['actual_cost_usd']}")
        """
        body: dict[str, Any] = {
            "intent": intent,
            "payload": payload,
            "stream": True,
        }
        if budget is not None:
            body["budget"] = budget
        if constraints is not None:
            body["constraints"] = constraints
        resp = self._post_raw("/v1/intent/subscribe", json=body, stream=True)
        return self._iter_sse(resp)

    @staticmethod
    def _iter_sse(resp) -> Generator[dict[str, Any], None, None]:
        """Parse Server-Sent Events from a streaming response."""
        import json as _json

        event_type = None
        for line in resp.iter_lines(decode_unicode=True):
            if line is None:
                continue
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    data = _json.loads(data_str)
                except (ValueError, TypeError):
                    data = data_str
                yield {"event": event_type or "message", "data": data}
                event_type = None
            elif line == "":
                continue

    # ─── Analytics / Audit ────────────────────────────────────────────────────────

    def audit(
        self,
        *,
        start: int | None = None,
        end: int | None = None,
        scope: str = "self",
    ) -> dict[str, Any]:
        """Get usage analytics and spending history.

        Args:
            start: Start time as unix timestamp (default: 24h ago)
            end: End time as unix timestamp (default: now)
            scope: "self" for current user, "global" for admin view

        Returns:
            Dict with: success, data containing:
            - daily_spent, monthly_spent, remaining
            - model_breakdown (list of per-model usage)
            - alerts (budget warnings)
        """
        params: dict[str, Any] = {"scope": scope}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        return self._get("/v1/aip/analytics/budget", params=params)

    def model_breakdown(
        self,
        *,
        start: int | None = None,
        end: int | None = None,
        top_n: int = 10,
        scope: str = "self",
    ) -> dict[str, Any]:
        """Get per-model usage breakdown.

        Args:
            start: Start time as unix timestamp (default: 24h ago)
            end: End time as unix timestamp (default: now)
            top_n: Number of top models to return
            scope: "self" for current user, "global" for admin view

        Returns:
            Dict with model entries containing: model_name, requests,
            total_tokens, cost_usd
        """
        params: dict[str, Any] = {"top_n": top_n, "scope": scope}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        return self._get("/v1/aip/analytics/models", params=params)

    # ─── Discovery & Federation ───────────────────────────────────────────────────

    def discover(
        self,
        *,
        intent_type: str | None = None,
        protocol: str | None = None,
        min_uptime: float | None = None,
    ) -> dict[str, Any]:
        """Discover AIP-compatible platforms via federation.

        Args:
            intent_type: Filter by supported intent type
            protocol: Filter by protocol ("aip", "a2a", "mcp")
            min_uptime: Minimum uptime percentage (0-100)

        Returns:
            Dict with: intents (list of discovered capabilities with
            provider, endpoint, supported_intents, uptime, pricing)
        """
        body: dict[str, Any] = {}
        if intent_type is not None:
            body["intent_type"] = intent_type
        if protocol is not None:
            body["protocol"] = protocol
        if min_uptime is not None:
            body["min_uptime"] = min_uptime
        return self._post("/v1/intent/discover", json=body)

    def federation_peers(
        self,
        *,
        status: str | None = None,
        protocol: str | None = None,
    ) -> dict[str, Any]:
        """List known federation peers.

        Args:
            status: Filter by status ("active", "unreachable")
            protocol: Filter by protocol ("aip", "a2a", "mcp")

        Returns:
            Dict with: peers (list of peer objects with endpoint, status,
            last_seen, supported_intents)
        """
        params: dict[str, Any] = {}
        if status is not None:
            params["status"] = status
        if protocol is not None:
            params["protocol"] = protocol
        return self._get("/v1/aip/federation/peers", params=params)

    # ─── Balance ──────────────────────────────────────────────────────────────────

    def balance(self) -> float:
        """Get current balance.

        - x402 mode: queries on-chain USDC balance
        - API Key mode: queries remaining account credits

        Returns:
            Balance in USD as float
        """
        return self.get_balance()

    # ─── Convenience Properties ───────────────────────────────────────────────────

    @property
    def wallet_address(self) -> str | None:
        """Wallet address (x402 mode only). None in API key mode."""
        return self.address

    def __repr__(self) -> str:
        mode = "x402" if self.wallet_address else "api_key"
        return f"JarvisClaw(mode={mode}, base_url={self.base_url!r})"
