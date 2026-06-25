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
