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

    def execute_budget(
        self,
        intent: str,
        payload: dict[str, Any],
        budget: dict[str, Any],
        *,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an intent with a hard spend cap and settlement tracking.

        Identical to execute() with a budget, kept as its own name because that
        is how the endpoint is documented.

        Args:
            intent: Intent type
            payload: Request body forwarded to the provider
            budget: Must include max_total_usd. Optional:
                preferred_payment_method ("x402" | "api_key"), allow_overdraft.
            constraints: Optional routing constraints

        Returns dict with: request_id, status, provider, model, result,
        actual_cost_usd, settlement, risk_level, duration_ms, reason
        """
        if not budget or "max_total_usd" not in budget:
            raise ValueError("budget must include max_total_usd")
        body: dict[str, Any] = {
            "intent": intent,
            "payload": payload,
            "budget": budget,
        }
        if constraints is not None:
            body["constraints"] = constraints
        return self._post("/v1/intent/execute-budget", json=body)

    # ─── Streaming ────────────────────────────────────────────────────────────────

    def stream(
        self,
        intent: str,
        payload: dict[str, Any],
        *,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
        optimize_for: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Execute an intent with the response streamed back over SSE.

        Args:
            intent: Intent type
            payload: The provider request body. Required.
            constraints: Optional routing constraints
            preferences: Optional optimization preferences
            optimize_for: Shorthand for preferences["optimize_for"] using the
                subscribe vocabulary: "speed", "cost" or "quality"

        Yields:
            Dicts with 'event' and 'data'. The first event is "metadata"
            (provider, intent, model) and the last is "done". In between the
            gateway relays the upstream events verbatim, so for chat completions
            'data' holds OpenAI-style chunks — including the literal "[DONE]"
            sentinel, which is not JSON and comes through as a string.

        Note this endpoint takes no budget: use execute_budget() for a spend cap.

        Example:
            for event in client.stream("chat_completion", payload={...}):
                if event["event"] == "metadata":
                    print("provider:", event["data"]["provider"])
                    continue
                chunk = event["data"]
                if isinstance(chunk, dict):
                    # The last chunk of a usage-reporting stream has an empty
                    # choices array, so guard before indexing.
                    choices = chunk.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        print(delta.get("content", ""), end="", flush=True)
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
        resp = self._post_raw("/v1/intent/subscribe", json=body, stream=True)
        return self._iter_sse(resp)

    # subscribe() is the documented name for the streaming call; stream() is the
    # shorter alias. Both hit POST /v1/intent/subscribe.
    subscribe = stream

    @staticmethod
    def _iter_sse(resp) -> Generator[dict[str, Any], None, None]:
        """Parse Server-Sent Events from a streaming response.

        See IntentClient._iter_sse — same framing rules: optional single space
        after "field:", repeated data: lines joined with newlines, comments
        skipped, and a trailing event flushed even without a final blank line.
        """
        import json as _json

        event_type = None
        data_lines: list[str] = []

        def _emit() -> dict[str, Any]:
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
                continue
            name, sep, value = line.partition(":")
            if not sep:
                continue
            if value.startswith(" "):
                value = value[1:]
            if name == "event":
                event_type = value
            elif name == "data":
                data_lines.append(value)

        if event_type is not None or data_lines:
            yield _emit()

    # ─── Analytics / Audit ────────────────────────────────────────────────────────
    #
    # The old /v1/aip/analytics/* endpoints were removed from the gateway and
    # consolidated into /api/analytics/aggregate, where AIP usage appears with
    # api_source="aip". Scope comes from the auth context, so there is no "scope"
    # parameter: a non-admin only ever sees their own rows.

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
            period: "24h", "7d" (default), "30d" or "90d".
            group_by: Any of "day", "model", "api_source", "principal_type",
                "channel", "group", "client_id". Defaults to
                ["day", "model", "api_source"].
            model: Restrict to one model name.
            user_id: Widen scope to another user. Admin-only; ignored otherwise.
            filters: Exact-match filters keyed by dimension, e.g.
                {"api_source": "aip"}.

        Returns a list of rows with the requested dimension keys plus
        total_quota, total_reqs, total_cost_usd, revenue_usd, settle_done,
        settle_failed, delivered, undelivered, loss_usd.
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

    def model_breakdown(self, *, period: str = "7d", **kwargs: Any) -> list[dict[str, Any]]:
        """Per-model cost and request breakdown for the period."""
        kwargs.pop("group_by", None)
        return self.spend(period=period, group_by=["model"], **kwargs)

    def daily_trend(self, *, period: str = "30d", **kwargs: Any) -> list[dict[str, Any]]:
        """One spend row per calendar day in the period."""
        kwargs.pop("group_by", None)
        return self.spend(period=period, group_by=["day"], **kwargs)

    def audit_log(self) -> dict[str, Any]:
        """Get the AIP orchestrator audit trail for recent requests.

        Returns dict with: entries, count.

        This is the request-level event log, not spend analytics — use spend()
        for cost figures.
        """
        return self._get("/v1/intent/audit")

    # audit() is the shorter alias for the same endpoint.
    audit = audit_log

    def budget_status(
        self,
        *,
        daily_budget: float = 10.0,
        monthly_budget: float = 200.0,
    ) -> dict[str, Any]:
        """Compute budget utilisation from actual spend.

        The gateway has no budget endpoint — the old /v1/aip/analytics/budget was
        removed — so this derives the figures from spend() locally. The limits you
        pass are the ones compared against; they are not read from the server.

        Args:
            daily_budget: Daily limit in USD to compare against.
            monthly_budget: Monthly limit in USD to compare against.

        Returns dict with: daily_spent, monthly_spent, daily_budget,
        monthly_budget, daily_remaining, monthly_remaining, daily_pct,
        monthly_pct, alerts (list of human-readable warnings).
        """
        daily_rows = self.spend(period="24h", group_by=["day"])
        monthly_rows = self.spend(period="30d", group_by=["day"])

        def _total(rows: list[dict[str, Any]]) -> float:
            return sum(float(r.get("total_cost_usd") or 0.0) for r in rows)

        daily_spent = _total(daily_rows)
        monthly_spent = _total(monthly_rows)

        alerts: list[str] = []
        daily_pct = (daily_spent / daily_budget * 100) if daily_budget > 0 else 0.0
        monthly_pct = (monthly_spent / monthly_budget * 100) if monthly_budget > 0 else 0.0
        if daily_pct >= 100:
            alerts.append(f"daily budget exceeded: ${daily_spent:.4f} of ${daily_budget:.2f}")
        elif daily_pct >= 80:
            alerts.append(f"daily budget at {daily_pct:.0f}%")
        if monthly_pct >= 100:
            alerts.append(f"monthly budget exceeded: ${monthly_spent:.4f} of ${monthly_budget:.2f}")
        elif monthly_pct >= 80:
            alerts.append(f"monthly budget at {monthly_pct:.0f}%")

        return {
            "daily_spent": daily_spent,
            "monthly_spent": monthly_spent,
            "daily_budget": daily_budget,
            "monthly_budget": monthly_budget,
            "daily_remaining": max(0.0, daily_budget - daily_spent),
            "monthly_remaining": max(0.0, monthly_budget - monthly_spent),
            "daily_pct": daily_pct,
            "monthly_pct": monthly_pct,
            "alerts": alerts,
        }

    # ─── Discovery & Federation ───────────────────────────────────────────────────

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
            public: Use the free unauthenticated GET route. Same response shape.

        Returns:
            Dict with: intents (type, description, features, provider_count),
            providers (id, name, intents, features, pricing, endpoint, source),
            federated (peer-contributed entries), total.
            `total` counts providers only.
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

        Returns total_providers, by_source, intent_types (a count) and
        federation counts. The {"success", "data"} envelope is unwrapped.
        """
        resp = self._get("/v1/network/stats")
        if isinstance(resp, dict) and "data" in resp:
            return resp["data"]
        return resp

    def discover_peers(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        """List federation peers from the public registry.

        Returns dict with: success, data (server_uuid, name, base_url, network,
        verified, resource_count, healthy, last_checked_at, aip_version,
        discover_url, latency_ms), total, page, page_size.

        Public — no auth required. This is not /v1/aip/federation/peers, which is
        admin-only and needs a dashboard session rather than an API key; see
        FederationClient.list_peers for that one.
        """
        return self._get(
            "/v1/federation/servers",
            params={"page": page, "page_size": page_size},
        )

    # federation_peers() is the older alias for discover_peers().
    federation_peers = discover_peers

    def search_federation(
        self,
        query: str = "",
        *,
        category: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search callable resources across every known federation peer.

        Public — no auth required.

        Returns dict with: success, data (name, path, method, description,
        category, tags, sell_price, price_unit, currency, network, popular,
        call_count, server_name), count.
        """
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["q"] = query
        if category is not None:
            params["category"] = category
        return self._get("/v1/federation/search", params=params)

    def federation_execute(self, request: dict[str, Any]) -> dict[str, Any]:
        """Invoke a federated resource; the gateway settles with the peer.

        Requires an API key or x402 payment.
        """
        return self._post("/v1/federation/execute", json=request)

    def crawl_network(self) -> dict[str, Any]:
        """Trigger an immediate crawl of every registered federation peer.

        Admin-only: POST /v1/aip/federation/crawl sits behind AdminAuth, which
        needs a dashboard session or an access token plus a New-Api-User header.
        An API key or x402 wallet gets 401 here.

        The crawl covers all registered peers and takes no seed or depth — register
        targets first with FederationClient.add_peer.

        Returns dict with: message, peers_crawled, healthy, results.
        """
        return self._post("/v1/aip/federation/crawl", json={})

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
