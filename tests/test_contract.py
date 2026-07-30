"""Contract tests: pin every request path and body against the real gateway.

No network, no credentials — a local HTTP stub records what the SDK sent and
replies with JSON copied from the handler that produces it. The existing tests
mock at ``session.request``, so they never saw the URL; that is how the SDK came
to call ``/v1/aip/analytics/*`` long after those routes were deleted.

Run: python -m pytest tests/test_contract.py -q
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from jarvisclaw import (
    Agent,
    APIError,
    BudgetExceededError,
    ChatClient,
    EmbeddingsClient,
    FederationClient,
    IntentClient,
    JarvisClaw,
    JarvisClawError,
    PromptCoachClient,
    SearchClient,
    UserAPIClient,
    WalletClient,
)


class _Recorder:
    """What the stub server last received."""

    def __init__(self) -> None:
        self.method: str = ""
        self.path: str = ""
        self.query: str = ""
        self.body: str = ""
        self.headers: dict[str, str] = {}

    @property
    def json_body(self) -> Any:
        return json.loads(self.body) if self.body else None


@pytest.fixture
def stub():
    """Start a stub server; yields (make_client, recorder, set_response)."""
    state: dict[str, Any] = {"status": 200, "body": "{}", "content_type": "application/json"}
    rec = _Recorder()

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            rec.method = self.command
            raw_path = self.path
            rec.path, _, rec.query = raw_path.partition("?")
            length = int(self.headers.get("Content-Length") or 0)
            rec.body = self.rfile.read(length).decode() if length else ""
            rec.headers = dict(self.headers)

            payload = state["body"].encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", state["content_type"])
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = do_DELETE = _handle

        def log_message(self, *args):  # silence the default stderr logging
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    # A small poll interval keeps shutdown() from costing the default 0.5s per
    # test, which dominated the suite runtime.
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{srv.server_address[1]}"

    def set_response(body: Any, status: int = 200, content_type: str = "application/json") -> None:
        state["body"] = body if isinstance(body, str) else json.dumps(body)
        state["status"] = status
        state["content_type"] = content_type

    def make_client(cls, **kwargs):
        return cls(api_key="sk-test", base_url=base_url, **kwargs)

    try:
        yield make_client, rec, set_response
    finally:
        srv.shutdown()
        srv.server_close()


# ── Wallet ────────────────────────────────────────────────────────────────────


def test_wallet_balance_shape(stub):
    """controller/wallet/balance.go GetBalance"""
    make, rec, respond = stub
    respond({
        "balance_usd": "5.960000",
        "wallets": {
            "base": {"usdc": "5.910000", "address": "0xabc"},
            "solana": {"usdc": "0.050000", "address": "7xK"},
        },
    })
    client = make(WalletClient)
    result = client.balance()

    assert rec.path == "/v1/wallet/balance"
    assert result["balance_usd"] == "5.960000"
    assert result["wallets"]["solana"]["usdc"] == "0.050000"
    # The removed keys must not be resurrected by a future edit.
    assert "quota" not in result and "hd_wallet" not in result


def test_wallet_history_uses_params(stub):
    make, rec, respond = stub
    respond({"transactions": [], "total": 0, "page": 2})
    make(WalletClient).history(page=2, page_size=50)

    assert rec.path == "/v1/wallet/history"
    assert "page=2" in rec.query and "page_size=50" in rec.query


def test_wallet_set_limit_is_read_modify_write(stub):
    """PUT /v1/wallet/limits replaces the row, so omitted fields become zero."""
    make, rec, respond = stub
    respond({
        "user_id": 42, "daily_max_usd": 50, "per_request_max_usd": 1,
        "monthly_max_usd": 500, "auto_pause_below_usd": 2,
        "pool_allocation": '{"operations":0.6,"insurance":0.15,"savings":0.15,"dividends":0.1}',
        "updated_at": 1718841600,
    })
    make(WalletClient).set_limit(daily_max_usd=30)

    assert rec.method == "PUT"
    sent = rec.json_body
    assert sent["daily_max_usd"] == 30
    assert sent["monthly_max_usd"] == 500
    assert sent["per_request_max_usd"] == 1
    assert "pool_allocation" in sent


# ── Analytics ─────────────────────────────────────────────────────────────────


def test_spend_hits_consolidated_endpoint(stub):
    """The /v1/aip/analytics/* routes were removed; spend must use /api/analytics/aggregate."""
    make, rec, respond = stub
    respond({
        "success": True,
        "data": [{
            "day": "2026-07-29", "model": "gpt-4o", "api_source": "aip",
            "total_quota": 25000, "total_reqs": 4, "total_cost_usd": 0.05,
            "revenue_usd": 0.06, "settle_done": 4, "settle_failed": 0,
            "delivered": 4, "undelivered": 0, "loss_usd": 0,
        }],
    })
    rows = make(IntentClient).spend(period="30d", group_by=["day", "model"])

    assert rec.path == "/api/analytics/aggregate"
    assert "period=30d" in rec.query
    assert "group_by=day%2Cmodel" in rec.query or "group_by=day,model" in rec.query
    assert len(rows) == 1
    assert rows[0]["total_cost_usd"] == 0.05
    # AIP usage is visible here, tagged by api_source.
    assert rows[0]["api_source"] == "aip"


def test_spend_raises_on_success_false(stub):
    make, _, respond = stub
    respond({"success": False, "message": "unauthorized"})
    with pytest.raises(APIError, match="unauthorized"):
        make(IntentClient).spend()


def test_spend_filters_are_prefixed(stub):
    make, rec, respond = stub
    respond({"success": True, "data": []})
    make(IntentClient).spend(filters={"api_source": "aip", "principal_type": "agent"})

    assert "filter_api_source=aip" in rec.query
    assert "filter_principal_type=agent" in rec.query


def test_cost_by_model_overrides_group_by(stub):
    make, rec, respond = stub
    respond({"success": True, "data": []})
    make(IntentClient).cost_by_model()
    assert "group_by=model" in rec.query


def test_dead_analytics_methods_are_gone():
    """The old names pointed at deleted routes; they must not silently linger."""
    for name in ("cost_summary", "cost_trend", "roi"):
        assert not hasattr(IntentClient, name), f"{name} still present"


def test_unified_budget_status_is_derived(stub):
    """No budget endpoint exists, so budget_status computes from spend()."""
    make, rec, respond = stub
    respond({"success": True, "data": [{"total_cost_usd": 4.0}, {"total_cost_usd": 5.0}]})
    result = make(JarvisClaw).budget_status(daily_budget=10.0, monthly_budget=200.0)

    assert rec.path == "/api/analytics/aggregate"
    assert result["daily_spent"] == 9.0
    assert result["daily_remaining"] == 1.0
    assert result["daily_pct"] == 90.0
    assert any("90%" in a for a in result["alerts"])


def test_unified_audit_log_uses_intent_audit(stub):
    make, rec, respond = stub
    respond({"entries": [], "count": 0})
    make(JarvisClaw).audit_log()
    assert rec.path == "/v1/intent/audit"


# ── Intent / discovery ────────────────────────────────────────────────────────


def test_discover_body_keys(stub):
    """controller/aip/discover.go DiscoverRequest takes intent/features/max_price."""
    make, rec, respond = stub
    respond({
        "intents": [{"type": "web_search", "description": "Search", "features": [], "provider_count": 2}],
        "providers": [{"id": "p1", "name": "P1", "intents": ["web_search"], "features": [],
                       "pricing": {"per_call": 0.01}, "endpoint": "/v1/search", "source": "internal"}],
        "federated": [],
        "total": 1,
    })
    result = make(IntentClient).discover(intent="web_search", features=["citations"], max_price=0.02)

    assert rec.method == "POST"
    assert rec.path == "/v1/intent/discover"
    sent = rec.json_body
    assert sent == {"intent": "web_search", "features": ["citations"], "max_price": 0.02}
    # The old intent_type / protocol / min_uptime keys were never read.
    assert "intent_type" not in sent and "min_uptime" not in sent
    assert result["total"] == 1
    assert result["providers"][0]["source"] == "internal"


def test_discover_public_uses_get(stub):
    make, rec, respond = stub
    respond({"intents": [], "providers": [], "total": 0})
    make(IntentClient).discover(intent="web_search", features=["a", "b"], public=True)

    assert rec.method == "GET"
    assert rec.path == "/v1/intent/discover"
    assert "features=a%2Cb" in rec.query or "features=a,b" in rec.query


def test_resolve_natural_clarify_branch(stub):
    make, rec, respond = stub
    respond({
        "status": "clarify", "session_id": "s-1",
        "clarify": {"question": "How long?", "options": ["5s", "10s"], "round": 1},
    })
    result = make(IntentClient).resolve_natural("make a cat video")

    assert rec.path == "/v1/intent/resolve/natural"
    assert rec.json_body == {"query": "make a cat video"}
    assert result["status"] == "clarify"
    assert result["clarify"]["round"] == 1


def test_resolve_natural_rejects_blank(stub):
    make, _, _ = stub
    with pytest.raises(ValueError):
        make(IntentClient).resolve_natural("   ")


def test_network_stats(stub):
    make, rec, respond = stub
    respond({"success": True, "data": {"total_providers": 42, "by_source": {"internal": 30},
                                       "intent_types": 13}})
    result = make(IntentClient).network_stats()

    assert rec.path == "/v1/network/stats"
    # The {success, data} envelope is unwrapped, matching the Go SDK, so the
    # stats are at the top level rather than under "data".
    assert "data" not in result
    assert result["total_providers"] == 42
    # intent_types is a count, not a list.
    assert result["intent_types"] == 13


def test_network_stats_tolerates_unwrapped_body(stub):
    """A response already lacking the envelope must pass through untouched."""
    make, rec, respond = stub
    respond({"total_providers": 7, "intent_types": 2})
    result = make(IntentClient).network_stats()

    assert result["total_providers"] == 7


def test_subscribe_requires_payload(stub):
    make, _, _ = stub
    with pytest.raises(ValueError):
        make(IntentClient).subscribe("chat_completion", {})


def test_subscribe_body_has_no_budget(stub):
    """POST /v1/intent/subscribe binds intent/payload/constraints/preferences/optimize_for."""
    make, rec, respond = stub
    respond("event: done\ndata: {}\n\n", content_type="text/event-stream")
    events = list(make(IntentClient).subscribe(
        "chat_completion",
        {"messages": [{"role": "user", "content": "hi"}]},
        optimize_for="speed",
    ))

    assert rec.path == "/v1/intent/subscribe"
    sent = rec.json_body
    assert sent["optimize_for"] == "speed"
    # The handler has no budget field; sending one was silently ignored.
    assert "budget" not in sent
    assert events == [{"event": "done", "data": {}}]


def test_sse_framing(stub):
    """Optional space after data:, multi-line data, comments, trailing event."""
    make, _, respond = stub
    respond(
        ": keep-alive\n"
        "event: metadata\n"
        'data: {"provider":"p1"}\n'
        "\n"
        "event:chunk\n"
        'data:{"a":1}\n'
        'data:{"b":2}\n'
        "\n"
        "event: done\n"
        "data: [DONE]\n",
        content_type="text/event-stream",
    )
    events = list(make(IntentClient).subscribe("chat_completion", {"messages": []}))

    assert len(events) == 3, events
    assert events[0] == {"event": "metadata", "data": {"provider": "p1"}}
    # "event:chunk" with no space must parse, and both data lines are kept.
    assert events[1]["event"] == "chunk"
    assert events[1]["data"] == '{"a":1}\n{"b":2}'
    # [DONE] is not JSON and comes through as a string.
    assert events[2] == {"event": "done", "data": "[DONE]"}


def test_unsubscribe_path(stub):
    make, rec, respond = stub
    respond({"success": True, "message": "subscription cancelled"})
    make(IntentClient).unsubscribe("sub-9")
    assert rec.method == "DELETE"
    assert rec.path == "/v1/intent/subscribe/sub-9"


# ── Prompt coach ──────────────────────────────────────────────────────────────


def test_prompt_coach_unwraps_envelope(stub):
    """controller/prompt_coach_x402.go wraps its result in {success, data}."""
    make, rec, respond = stub
    respond({
        "success": True,
        "data": {
            "original_prompt": "make a site", "optimized_prompt": "Build a portfolio site...",
            "explanation": "Added scope.", "score_before": 35, "score_after": 88,
            "suggestions": ["state the audience"], "model_used": "deepseek/deepseek-chat",
        },
    })
    result = make(PromptCoachClient).optimize("make a site", context="portfolio")

    assert rec.path == "/v1/prompt-coach/optimize"
    # Scores are integers on a 1-100 scale, not 0-10.
    assert result["score_before"] == 35 and result["score_after"] == 88
    assert result["model_used"] == "deepseek/deepseek-chat"
    assert "success" not in result, "envelope should be unwrapped"


def test_prompt_score_uses_optimize(stub):
    """/v1/prompt-coach/score does not exist; score() derives from optimize()."""
    make, rec, respond = stub
    respond({"success": True, "data": {"score_before": 42, "score_after": 90}})
    assert make(PromptCoachClient).score("some prompt") == 42
    assert rec.path == "/v1/prompt-coach/optimize"


# ── Federation ────────────────────────────────────────────────────────────────


def test_federation_list_peers_unwraps_data(stub):
    """FederationStatus returns {success, data} with camelCase keys."""
    make, rec, respond = stub
    respond({
        "success": True,
        "data": [{"id": 1, "name": "peer-a", "url": "https://a.example", "status": "online",
                  "lastSeen": "2026-07-30T00:00:00Z", "resourceCount": 12, "latencyMs": 85}],
    })
    peers = make(FederationClient).list_peers()

    assert rec.path == "/v1/aip/federation/peers"
    assert len(peers) == 1
    assert peers[0]["resourceCount"] == 12
    assert peers[0]["status"] == "online"


def test_federation_remove_peer_sends_domain_in_body(stub):
    """FederationRemovePeer binds {"domain": ...}; there is no :id path param."""
    make, rec, respond = stub
    respond({"message": "peer removed", "domain": "a.example"})
    make(FederationClient).remove_peer("a.example")

    assert rec.method == "DELETE"
    assert rec.path == "/v1/aip/federation/peers"
    assert rec.json_body == {"domain": "a.example"}


def test_federation_crawl_takes_no_seed(stub):
    """FederationCrawl reads no body; seed_urls/max_depth were never honoured."""
    make, rec, respond = stub
    respond({"message": "crawl completed", "peers_crawled": 3, "healthy": 2, "results": []})
    result = make(FederationClient).crawl()

    assert rec.path == "/v1/aip/federation/crawl"
    assert rec.json_body == {}
    assert result["peers_crawled"] == 3


def test_federation_search_public(stub):
    make, rec, respond = stub
    respond({"success": True, "count": 1, "data": [{"name": "price", "sell_price": 0.002,
                                                    "server_name": "peer-a"}]})
    results = make(FederationClient).search("price", limit=5)

    assert rec.path == "/v1/federation/search"
    assert "q=price" in rec.query and "limit=5" in rec.query
    assert results[0]["sell_price"] == 0.002


def test_federation_raises_on_success_false(stub):
    make, _, respond = stub
    respond({"success": False, "message": "db down"})
    with pytest.raises(APIError, match="db down"):
        make(FederationClient).list_peers()


def test_unified_discover_peers_is_public_registry(stub):
    """discover_peers uses the public registry, not the admin-only peers route."""
    make, rec, respond = stub
    respond({"success": True, "data": [], "total": 0})
    make(JarvisClaw).discover_peers()
    assert rec.path == "/v1/federation/servers"


# ── Embeddings / rerank / moderation ──────────────────────────────────────────


def test_embeddings_and_batch_ordering(stub):
    make, rec, respond = stub
    # Deliberately out of order to prove embed_batch sorts by index.
    respond({"object": "list", "model": "m", "data": [
        {"object": "embedding", "index": 1, "embedding": [0.3, 0.4]},
        {"object": "embedding", "index": 0, "embedding": [0.1, 0.2]},
    ]})
    vectors = make(EmbeddingsClient).embed_batch("m", ["a", "b"])

    assert rec.path == "/v1/embeddings"
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_single(stub):
    make, rec, respond = stub
    respond({"data": [{"index": 0, "embedding": [0.5]}]})
    assert make(EmbeddingsClient).embed("m", "hi") == [0.5]
    assert rec.json_body == {"model": "m", "input": "hi"}


def test_embed_raises_when_no_vectors(stub):
    make, _, respond = stub
    respond({"data": []})
    with pytest.raises(APIError):
        make(EmbeddingsClient).embed("m", "hi")


def test_rerank(stub):
    make, rec, respond = stub
    respond({"results": [{"index": 2, "relevance_score": 0.87}], "model": "r"})
    results = make(EmbeddingsClient).rerank_texts("r", "cats", ["a", "b", "c"])

    assert rec.path == "/v1/rerank"
    assert rec.json_body["documents"] == ["a", "b", "c"]
    assert results[0]["relevance_score"] == 0.87


def test_embeddings_input_validation(stub):
    make, _, _ = stub
    client = make(EmbeddingsClient)
    with pytest.raises(ValueError):
        client.create("", "x")
    with pytest.raises(ValueError):
        client.create("m", None)
    with pytest.raises(ValueError):
        client.rerank("m", "q", [])
    with pytest.raises(ValueError):
        client.moderate(None)


# ── UAPI ──────────────────────────────────────────────────────────────────────


def test_uapi_list_and_call_paths(stub):
    make, rec, respond = stub
    respond({"success": True, "data": [{"slug": "weather", "price_per_call": 0.013}],
             "total": 1, "page": 1, "page_size": 20})
    result = make(UserAPIClient).list(category="data")

    assert rec.path == "/api/user-api/list"
    assert result["data"][0]["price_per_call"] == 0.013

    respond({"ok": True})
    make(UserAPIClient).call("weather", "forecast", method="POST", json={"city": "Tokyo"})
    assert rec.path == "/v1/uapi/weather/forecast"
    assert rec.json_body == {"city": "Tokyo"}


def test_uapi_list_raises_on_success_false(stub):
    make, _, respond = stub
    respond({"success": False, "message": "db down"})
    with pytest.raises(APIError, match="db down"):
        make(UserAPIClient).list()


def test_uapi_requires_slug(stub):
    make, _, _ = stub
    with pytest.raises(ValueError):
        make(UserAPIClient).call("", "x")


# ── Search ────────────────────────────────────────────────────────────────────


def test_exa_search_and_answer_paths(stub):
    make, rec, respond = stub
    respond({"results": [{"title": "T", "url": "https://e.com", "text": "body"}]})
    results = make(SearchClient).exa_search("cats")

    assert rec.path == "/v1/marketplace/exa/search"
    assert results[0].snippet == "body"

    respond({"answer": "Cats are mammals.", "results": []})
    answer = make(SearchClient).answer("what is a cat")
    assert rec.path == "/v1/marketplace/exa/answer"
    assert answer["answer"] == "Cats are mammals."


# ── Error handling ────────────────────────────────────────────────────────────


def test_error_message_is_extracted(stub):
    make, _, respond = stub
    respond({"error": {"message": "model not found", "type": "invalid_request_error"}}, status=400)
    with pytest.raises(APIError, match="model not found"):
        make(IntentClient).resolve("nope")


def test_billing_endpoint_200_error_is_raised(stub):
    """GetSubscription answers 200 with an {"error": ...} body on failure."""
    make, rec, respond = stub
    respond({"error": {"message": "token not found", "type": "upstream_error"}})
    with pytest.raises(APIError, match="token not found"):
        make(WalletClient).get_balance()
    assert rec.path == "/v1/dashboard/billing/subscription"


def test_get_balance_reads_hard_limit(stub):
    make, rec, respond = stub
    respond({"object": "billing_subscription", "hard_limit_usd": 5.96,
             "soft_limit_usd": 5.96, "system_hard_limit_usd": 5.96})
    assert make(WalletClient).get_balance() == 5.96
    # Not /api/user/self, which needs a dashboard session an API key cannot give.
    assert rec.path == "/v1/dashboard/billing/subscription"


# ── Regressions found by running the examples against the live gateway ────────


def test_agent_stream_survives_empty_choices(stub):
    """A usage-reporting stream ends with choices:[] — indexing it used to crash.

    The gateway's final SSE frame carries token usage and an empty choices array.
    Agent.stream() read choices[0] unconditionally, so every fully-consumed
    stream raised IndexError after yielding all its content.
    """
    make, _rec, respond = stub
    respond(
        'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[],"usage":{"total_tokens":7}}\n\n'
        "data: [DONE]\n\n",
        content_type="text/event-stream",
    )
    agent = make(Agent, default_model="openai/gpt-4o-mini")

    assert "".join(agent.stream("hi")) == "hello"


def test_agent_stream_accepts_spaceless_sse_field(stub):
    """The space after "data:" is optional per the SSE spec."""
    make, _rec, respond = stub
    respond(
        'data:{"choices":[{"delta":{"content":"ok"}}]}\n\n'
        ": this is a comment line and must be ignored\n\n"
        "data:[DONE]\n\n",
        content_type="text/event-stream",
    )
    agent = make(Agent, default_model="openai/gpt-4o-mini")

    assert "".join(agent.stream("hi")) == "ok"


def test_agent_ask_rejects_nonpositive_budget(stub):
    """ask(budget=...) used to be recorded after the fact and never enforced.

    Cost is only known from the response, so a budget that cannot cover any call
    has to be refused before the request is sent.
    """
    make, rec, respond = stub
    respond({"choices": [{"message": {"content": "hi"}}]})
    agent = make(Agent, default_model="openai/gpt-4o-mini")

    with pytest.raises(BudgetExceededError):
        agent.ask("hello", budget=0)

    # Nothing was sent.
    assert rec.path == ""


def test_transport_timeout_raises_sdk_error():
    """Transport failures must be catchable as JarvisClawError.

    They previously escaped as raw requests exceptions, so a caller could not
    write one except clause covering all SDK failures.
    """
    # 10.255.255.1 is non-routable, so this cannot reach a real service.
    client = ChatClient(api_key="sk-test", base_url="http://10.255.255.1", timeout=1)

    with pytest.raises(JarvisClawError) as exc:
        client.complete("hi")
    assert exc.value.is_timeout


def test_chat_complete_forwards_extra_params(stub):
    """complete() had no **kwargs, so max_tokens and friends were unreachable."""
    make, rec, respond = stub
    respond({"choices": [{"message": {"content": "ok"}}]})

    make(ChatClient).complete("hi", model="openai/gpt-4o-mini", max_tokens=5, seed=1)

    body = rec.json_body
    assert body["max_tokens"] == 5
    assert body["seed"] == 1
