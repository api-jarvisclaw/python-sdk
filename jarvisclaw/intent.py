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
    #
    # The standalone /v1/aip/analytics/* endpoints were removed from the gateway
    # and consolidated into /api/analytics/aggregate. AIP usage shows up there
    # with api_source="aip". Scope is enforced server-side from the auth context:
    # a non-admin caller only ever sees their own rows, so there is no "scope"
    # parameter to pass.

    def spend(
        self,
        *,
        period: str = "7d",
        group_by: list[str] | None = None,
        model: str | None = None,
        user_id: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Get aggregated spend and settlement rows.

        Args:
            period: Lookback window — "24h", "7d" (default), "30d" or "90d".
                Anything else falls back to "7d" server-side.
            group_by: Aggregation dimensions. Valid values: "day", "model",
                "api_source", "principal_type", "channel", "group", "client_id".
                Defaults to ["day", "model", "api_source"].
            model: Restrict to a single model name.
            user_id: Widen the scope to another user. Admin-only and ignored
                otherwise.
            filters: Exact-match filters keyed by dimension, e.g.
                {"api_source": "aip", "principal_type": "agent"}.

        Returns a list of rows, each with the requested dimension keys plus
        total_quota, total_reqs, total_cost_usd, revenue_usd, settle_done,
        settle_failed, delivered, undelivered and loss_usd.
        """
        params: dict[str, Any] = {"period": period}
        if group_by:
            params["group_by"] = ",".join(group_by)
        if model is not None:
            params["model"] = model
        if user_id is not None:
            params["user_id"] = user_id
        for key, value in (filters or {}).items():
            params[f"filter_{key}"] = value

        data = self._get("/api/analytics/aggregate", params=params)
        if not data.get("success", True):
            from .errors import APIError

            raise APIError(200, data.get("message", "analytics request failed"), data)
        return data.get("data") or []

    def cost_by_model(self, *, period: str = "7d", **kwargs: Any) -> list[dict[str, Any]]:
        """Per-model cost and request breakdown for the period."""
        kwargs.pop("group_by", None)
        return self.spend(period=period, group_by=["model"], **kwargs)

    def daily_trend(self, *, period: str = "30d", **kwargs: Any) -> list[dict[str, Any]]:
        """One spend row per calendar day in the period."""
        kwargs.pop("group_by", None)
        return self.spend(period=period, group_by=["day"], **kwargs)

    def quality(self, *, period: str = "7d", model: str | None = None) -> dict[str, Any]:
        """Get per-request quality signals mined from the logs.

        Keyed by (model, principal). The signal set evolves with what the gateway
        mines, so the payload is returned as-is.
        """
        params: dict[str, Any] = {"period": period}
        if model is not None:
            params["model"] = model
        return self._get("/api/analytics/quality", params=params)

    def insights(self, *, period: str = "7d", model: str | None = None) -> dict[str, Any]:
        """Get the deep-scan summary over consume and marketplace logs.

        Folds cache, latency, reliability, pricing and mapping signals into a
        global summary plus a per-(model, principal) breakdown.
        """
        params: dict[str, Any] = {"period": period}
        if model is not None:
            params["model"] = model
        return self._get("/api/analytics/insights", params=params)


    # ─── Discovery & Subscription ─────────────────────────────────────────────────

    def discover(
        self,
        *,
        intent: str | None = None,
        features: list[str] | None = None,
        max_price: float | None = None,
        public: bool = False,
    ) -> dict[str, Any]:
        """Discover the intents and providers this gateway and its peers serve.

        Args:
            intent: Restrict to one intent type. Omit for everything.
            features: Require providers to support ALL of these features.
            max_price: Cap the estimated per-request price in USD.
            public: Use the free unauthenticated GET route instead of the paid
                POST one. Same response shape.

        Returns dict with: intents, providers, federated, total.
        Note `total` counts providers only.
        """
        if public:
            params: dict[str, Any] = {}
            if intent is not None:
                params["intent"] = intent
            if features:
                params["features"] = ",".join(features)
            if max_price is not None:
                params["max_price"] = max_price
            return self._get("/v1/intent/discover", params=params)

        body: dict[str, Any] = {}
        if intent is not None:
            body["intent"] = intent
        if features:
            body["features"] = features
        if max_price is not None:
            body["max_price"] = max_price
        return self._post("/v1/intent/discover", json=body)

    def resolve_natural(
        self,
        query: str,
        *,
        session_id: str | None = None,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve a free-text request to an intent and ranked providers.

        Uses embedding similarity with a keyword fallback. Nothing is executed,
        so no provider is charged — but the embedding itself is billable.

        Args:
            query: The natural-language request.
            session_id: Carry a multi-turn clarification forward. Pass back the
                session_id from a previous "clarify" response.
            constraints: Optional max_price_usd / max_latency_ms / features.
            preferences: Optional optimize_for ("cost", "quality", "latency").

        Returns dict with: status ("resolved" | "clarify" | "budget_insufficient"
        | "no_match"), session_id, intent, confidence, matches, clarify, message.
        On "clarify", ask clarify["question"] and retry with the same session_id.
        """
        if not query or not query.strip():
            raise ValueError("query is required")
        body: dict[str, Any] = {"query": query}
        if session_id is not None:
            body["session_id"] = session_id
        if constraints is not None:
            body["constraints"] = constraints
        if preferences is not None:
            body["preferences"] = preferences
        return self._post("/v1/intent/resolve/natural", json=body)

    def network_stats(self) -> dict[str, Any]:
        """Get provider and federation counts. Public, no auth required.

        Returns dict with: success, data (total_providers, by_source,
        intent_types as a count, and federation counts when available).
        """
        return self._get("/v1/network/stats")

    def subscribe(
        self,
        intent: str,
        payload: dict[str, Any],
        *,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
        optimize_for: str | None = None,
        stream: bool = True,
    ):
        """Execute an intent with the response streamed back over SSE.

        This is the streaming variant of execute(): the server resolves the best
        provider, injects stream=true and the resolved model into your payload,
        and relays the upstream events.

        Args:
            intent: Intent type (e.g. "chat_completion", "web_search").
            payload: The provider request body (messages, prompt, …). Required.
            constraints: Optional routing constraints.
            preferences: Optional optimization preferences.
            optimize_for: Shorthand for preferences["optimize_for"], using the
                subscribe vocabulary: "speed", "cost" or "quality".
            stream: Parse the response as SSE (default). Set False to get the
                raw JSON body, which is only useful for error responses — the
                endpoint always streams on success.

        Returns:
            stream=True: a generator of {"event": str, "data": Any} dicts. The
                first event is "metadata" and the last is "done". `data` is
                parsed JSON where possible, and the raw string otherwise — note
                OpenAI-style streams end with the literal "[DONE]" sentinel.
            stream=False: the decoded JSON body.

        Note there is no budget parameter: this endpoint takes constraints and
        preferences only. Use execute_budget() for a hard spend cap.
        """
        if not payload:
            raise ValueError("payload is required")
        body: dict[str, Any] = {"intent": intent, "payload": payload}
        if constraints is not None:
            body["constraints"] = constraints
        if preferences is not None:
            body["preferences"] = preferences
        if optimize_for is not None:
            body["optimize_for"] = optimize_for
        if stream:
            resp = self._post_raw("/v1/intent/subscribe", json=body, stream=True)
            return self._iter_sse(resp)
        return self._post("/v1/intent/subscribe", json=body)

    @staticmethod
    def _iter_sse(resp):
        """Parse Server-Sent Events from a streaming response.

        Follows the SSE framing rules rather than assuming one shape: the field
        separator is "field:" with at most one optional leading space, and
        repeated data: lines in one event are joined with newlines. Matching on
        "data: " with a hard-coded space silently drops any upstream that writes
        "data:{...}".
        """
        import json as _json

        event_type = None
        data_lines: list[str] = []

        def _emit():
            raw = "\n".join(data_lines)
            try:
                data = _json.loads(raw)
            except (ValueError, TypeError):
                data = raw
            return {"event": event_type or "message", "data": data}

        for line in resp.iter_lines(decode_unicode=True):
            if line is None:
                continue
            line = line.rstrip("\r")
            if line == "":
                if event_type is not None or data_lines:
                    yield _emit()
                    event_type = None
                    data_lines = []
                continue
            if line.startswith(":"):
                continue  # comment / keep-alive
            name, sep, value = line.partition(":")
            if not sep:
                continue
            if value.startswith(" "):
                value = value[1:]
            if name == "event":
                event_type = value
            elif name == "data":
                data_lines.append(value)

        # Flush a trailing event the stream ended without a blank line after.
        if event_type is not None or data_lines:
            yield _emit()

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
