"""IntentClient — AIP (Agent Intent Protocol) for intent-based AI access."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient


class IntentClient(BaseClient):
    """AIP Intent Protocol client. Resolve, execute, and budget-manage AI intents.

    Usage:
        from jarvisclaw import IntentClient

        intent = IntentClient(api_key="sk-...")
        matches = intent.resolve("chat_completion")
    """

    def resolve(
        self,
        intent: str,
        *,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve an intent to ranked provider matches.

        Args:
            intent: Intent type (e.g. "chat_completion", "image_generation")
            constraints: Optional dict with max_price_usd, max_latency_ms, features
            preferences: Optional dict with optimize_for, limit

        Returns dict with: matches, intent_type, total_available
        """
        body: dict[str, Any] = {"intent": intent}
        if constraints:
            body["constraints"] = constraints
        if preferences:
            body["preferences"] = preferences
        return self._post("/v1/intent/resolve", json=body)

    def execute(
        self,
        intent: str,
        payload: dict[str, Any],
        *,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve and execute an intent, returning the raw provider response.

        Args:
            intent: Intent type
            payload: Opaque request body forwarded to the resolved provider
            constraints: Optional filtering constraints
            preferences: Optional optimization preferences

        Returns: Raw upstream provider response as dict
        """
        body: dict[str, Any] = {"intent": intent, "payload": payload}
        if constraints:
            body["constraints"] = constraints
        if preferences:
            body["preferences"] = preferences
        return self._post("/v1/intent/execute", json=body)

    def execute_budget(
        self,
        intent: str,
        payload: dict[str, Any],
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an intent with budget control and settlement tracking.

        Args:
            intent: Intent type
            payload: Opaque request body forwarded to provider
            budget: Dict with max_total_usd (required), preferred_payment_method, allow_overdraft

        Returns dict with: request_id, status, provider, model, result,
            actual_cost_usd, settlement, risk_level, duration_ms, reason
        """
        body: dict[str, Any] = {
            "intent": intent,
            "payload": payload,
            "budget": budget,
        }
        return self._post("/v1/intent/execute-budget", json=body)

    def audit(self) -> dict[str, Any]:
        """Get the audit trail for recent requests.

        Returns dict with: entries, count
        """
        return self._get("/v1/intent/audit")

    def types(self) -> list[str]:
        """List supported intent types.

        Returns list of intent type strings.
        """
        data = self._get("/v1/intent/types")
        return data["intent_types"]

    def providers(self) -> dict[str, Any]:
        """List all registered providers.

        Returns dict with: providers, total
        """
        return self._get("/v1/providers")

    # ─── Analytics ────────────────────────────────────────────

    def cost_summary(
        self,
        *,
        start: int | None = None,
        end: int | None = None,
        top_n: int = 10,
        scope: str = "self",
    ) -> dict[str, Any]:
        """Get cost summary for a time range.

        Args:
            start: Start time as unix timestamp (default: 24h ago)
            end: End time as unix timestamp (default: now)
            top_n: Number of top models/providers to include
            scope: "self" for current user, "global" for admin-level view

        Returns dict with: success, data (total_cost, request_count, top_models, etc.)
        """
        params: dict[str, Any] = {"top_n": top_n, "scope": scope}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        return self._get("/v1/aip/analytics/summary", params=params)

    def cost_trend(
        self,
        *,
        start: int | None = None,
        end: int | None = None,
        granularity: str = "hour",
        scope: str = "self",
    ) -> dict[str, Any]:
        """Get cost trend over time.

        Args:
            start: Start time as unix timestamp (default: 24h ago)
            end: End time as unix timestamp (default: now)
            granularity: "hour" or "day"
            scope: "self" for current user, "global" for admin-level view

        Returns dict with: success, data (list of time-bucketed cost entries)
        """
        params: dict[str, Any] = {"granularity": granularity, "scope": scope}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        return self._get("/v1/aip/analytics/trend", params=params)

    def budget_status(
        self,
        *,
        daily_budget: float = 10.0,
        monthly_budget: float = 200.0,
        scope: str = "self",
    ) -> dict[str, Any]:
        """Get current budget utilization status.

        Args:
            daily_budget: Daily budget limit in USD
            monthly_budget: Monthly budget limit in USD
            scope: "self" for current user, "global" for admin-level view

        Returns dict with: success, data (daily_spent, monthly_spent, remaining, alerts)
        """
        params: dict[str, Any] = {
            "daily_budget": daily_budget,
            "monthly_budget": monthly_budget,
            "scope": scope,
        }
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
            scope: "self" for current user, "global" for admin-level view

        Returns dict with: success, data (list of model entries with tokens, cost, requests)
        """
        params: dict[str, Any] = {"top_n": top_n, "scope": scope}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        return self._get("/v1/aip/analytics/models", params=params)

    def roi(
        self,
        *,
        start: int | None = None,
        end: int | None = None,
        top_n: int = 10,
        scope: str = "self",
    ) -> dict[str, Any]:
        """Get ROI (tokens-per-dollar) efficiency metrics per model.

        Args:
            start: Start time as unix timestamp (default: 24h ago)
            end: End time as unix timestamp (default: now)
            top_n: Number of top models to return
            scope: "self" for current user, "global" for admin-level view

        Returns dict with: success, data (list of model ROI entries with
            model_name, total_tokens, cost_usd, tokens_per_dollar)
        """
        params: dict[str, Any] = {"top_n": top_n, "scope": scope}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        return self._get("/v1/aip/analytics/roi", params=params)


    # ─── Discovery & Subscription ─────────────────────────────────────────────────

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

        Returns dict with: intents (list of discovered capabilities)
        """
        body: dict[str, Any] = {}
        if intent_type is not None:
            body["intent_type"] = intent_type
        if protocol is not None:
            body["protocol"] = protocol
        if min_uptime is not None:
            body["min_uptime"] = min_uptime
        return self._post("/v1/intent/discover", json=body)

    def subscribe(
        self,
        intent: str,
        payload: dict[str, Any],
        *,
        budget: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        stream: bool = True,
    ):
        """Subscribe to an intent with streaming execution.

        This is the streaming variant of execute() — the server resolves
        the best provider and streams the response back via SSE.

        Args:
            intent: Intent type (e.g. "chat_completion", "web_search")
            payload: The request payload (model, messages, etc.)
            budget: Optional budget constraints
            constraints: Optional routing constraints
            stream: Whether to stream (default True)

        Returns:
            If stream=True: generator yielding SSE event dicts with 'event' and 'data' keys
            If stream=False: dict with the final JSON response
        """
        body: dict[str, Any] = {"intent": intent, "payload": payload}
        if budget is not None:
            body["budget"] = budget
        if constraints is not None:
            body["constraints"] = constraints
        if stream:
            body["stream"] = True
            resp = self._post_raw("/v1/intent/subscribe", json=body, stream=True)
            return self._iter_sse(resp)
        return self._post("/v1/intent/subscribe", json=body)

    @staticmethod
    def _iter_sse(resp):
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

    def unsubscribe(self, subscription_id: str) -> dict[str, Any]:
        """Cancel an intent subscription.

        Args:
            subscription_id: The subscription to cancel

        Returns dict with: success, message
        """
        return self._delete(f"/v1/intent/subscribe/{subscription_id}")

    def list_subscriptions(self) -> dict[str, Any]:
        """List active subscriptions for the authenticated user.

        Returns dict with: subscriptions (list)
        """
        return self._get("/v1/intent/subscribe")
