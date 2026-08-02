"""Tests for jarvisclaw.aio.FederationClient.

The async SDK had no federation surface at all, so an async application had to drop to raw
httpx or block its event loop on the sync client.

These use httpx.MockTransport rather than a mocking library: it ships with httpx (already a
hard dependency of the async extra), so the tests add nothing to install. Every assertion is on
the request the client actually built — method, path, query, body — because the bugs worth
catching here are wrong paths and dropped parameters, not response parsing.
"""
from __future__ import annotations

import json

import httpx
import pytest

from jarvisclaw.aio import FederationClient
from jarvisclaw.auth import APIKeyAuth
from jarvisclaw.errors import APIError


def client_with(handler) -> FederationClient:
    """Build a client whose transport is handler, recording what it was asked for.

    __new__ + manual field assignment rather than the constructor. AsyncBaseClient.__init__
    builds a real httpx.AsyncClient, and httpx loads the system CA bundle while doing so —
    several seconds per client on a machine with proxy environment variables set, which turned
    this file into a two-minute run for tests that never touch the network. Nothing under test
    here lives in __init__; auth resolution has its own coverage.
    """
    fed = FederationClient.__new__(FederationClient)
    fed._auth = APIKeyAuth("sk-test")
    fed.base_url = "https://api.example.test"
    fed.timeout = 30
    fed._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return fed


def recorder(payload, *, status: int = 200):
    """Handler returning payload and capturing the request it received."""
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(status, json=payload)

    return handler, seen


# ─── Registry ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_unwraps_data_and_sends_query():
    handler, seen = recorder({"success": True, "data": [{"resource_id": 64, "name": "qr"}]})
    fed = client_with(handler)

    out = await fed.search("qr code", category="utility", limit=5)

    assert out == [{"resource_id": 64, "name": "qr"}]
    req = seen["request"]
    assert req.url.path == "/v1/federation/search"
    assert req.url.params["q"] == "qr code"
    assert req.url.params["category"] == "utility"
    assert req.url.params["limit"] == "5"


@pytest.mark.asyncio
async def test_search_omits_empty_query():
    handler, seen = recorder({"success": True, "data": []})
    fed = client_with(handler)

    await fed.search()

    # An empty q would filter to nothing rather than listing everything.
    assert "q" not in seen["request"].url.params


@pytest.mark.asyncio
async def test_search_raises_on_success_false_in_200_body():
    handler, _ = recorder({"success": False, "message": "registry unavailable"})
    fed = client_with(handler)

    with pytest.raises(APIError) as exc:
        await fed.search("x")
    assert "registry unavailable" in str(exc.value)


@pytest.mark.asyncio
async def test_list_servers_paginates():
    handler, seen = recorder({"success": True, "data": [], "total": 91})
    fed = client_with(handler)

    out = await fed.list_servers(page=2, page_size=50)

    assert out["total"] == 91
    assert seen["request"].url.params["page"] == "2"
    assert seen["request"].url.params["page_size"] == "50"


@pytest.mark.asyncio
async def test_list_resources_forwards_filters():
    handler, seen = recorder({"success": True, "data": []})
    fed = client_with(handler)

    await fed.list_resources(category="dns", keyword="lookup")

    params = seen["request"].url.params
    assert params["category"] == "dns"
    assert params["keyword"] == "lookup"


@pytest.mark.asyncio
async def test_health_hits_public_path():
    handler, seen = recorder({"success": True, "data": {"healthy": 88}})
    fed = client_with(handler)

    await fed.health()

    assert seen["request"].url.path == "/v1/federation/health"


# ─── Catalogue and invoke ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_apis_uses_q_not_keyword():
    handler, seen = recorder({"success": True, "data": {"items": [], "total": 2720}})
    fed = client_with(handler)

    await fed.list_apis(keyword="qr code", category="utility")

    # The catalogue endpoint takes q; list_resources takes keyword. Sending the wrong one
    # returns an unfiltered page that looks like a working search.
    params = seen["request"].url.params
    assert seen["request"].url.path == "/api/marketplace/apis"
    assert params["q"] == "qr code"
    assert "keyword" not in params


@pytest.mark.asyncio
async def test_invoke_posts_to_resource_path():
    handler, seen = recorder({"summary": "ok"})
    fed = client_with(handler)

    out = await fed.invoke(64, payload={"text": "hello"})

    req = seen["request"]
    assert req.method == "POST"
    assert req.url.path == "/v1/marketplace/api/64"
    assert json.loads(req.content) == {"text": "hello"}
    assert out == {"summary": "ok"}


@pytest.mark.asyncio
async def test_invoke_get_sends_payload_as_query():
    handler, seen = recorder({"codes": []})
    fed = client_with(handler)

    await fed.invoke(64, payload={"data": "hello"}, method="GET")

    req = seen["request"]
    assert req.method == "GET"
    # A GET whose payload went into a body would reach the upstream with no parameters at all.
    assert req.url.params["data"] == "hello"
    assert not req.content


@pytest.mark.asyncio
async def test_invoke_post_with_no_payload_sends_empty_object():
    handler, seen = recorder({"ok": True})
    fed = client_with(handler)

    await fed.invoke(64)

    assert json.loads(seen["request"].content) == {}


@pytest.mark.parametrize("bad", [0, -1, "64", None, True, 1.0])
@pytest.mark.asyncio
async def test_invoke_rejects_non_positive_int_resource_id(bad):
    handler, _ = recorder({})
    fed = client_with(handler)

    # "64" would build /v1/marketplace/api/64 and appear to work, so a string is rejected
    # rather than coerced. True is an int subclass and would resolve to resource 1.
    with pytest.raises(ValueError):
        await fed.invoke(bad)


@pytest.mark.asyncio
async def test_execute_posts_envelope():
    handler, seen = recorder({"success": True, "status_code": 200})
    fed = client_with(handler)

    await fed.execute({"resource_id": 476, "payload": {}})

    req = seen["request"]
    assert req.url.path == "/v1/federation/execute"
    assert json.loads(req.content)["resource_id"] == 476


# ─── Peer management ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_peers_unwraps_data():
    handler, seen = recorder({"success": True, "data": [{"id": 1, "status": "online"}]})
    fed = client_with(handler)

    out = await fed.list_peers()

    assert out == [{"id": 1, "status": "online"}]
    assert seen["request"].url.path == "/v1/aip/federation/peers"


@pytest.mark.asyncio
async def test_remove_peer_sends_domain_in_body_not_path():
    handler, seen = recorder({"success": True})
    fed = client_with(handler)

    await fed.remove_peer("peer.example.test")

    req = seen["request"]
    assert req.method == "DELETE"
    # The server identifies the peer by body, not by a path id.
    assert req.url.path == "/v1/aip/federation/peers"
    assert json.loads(req.content) == {"domain": "peer.example.test"}


@pytest.mark.parametrize("method", ["add_peer", "remove_peer"])
@pytest.mark.asyncio
async def test_peer_methods_reject_empty_domain(method):
    handler, _ = recorder({})
    fed = client_with(handler)

    with pytest.raises(ValueError):
        await getattr(fed, method)("")


@pytest.mark.asyncio
async def test_crawl_posts_empty_body():
    handler, seen = recorder({"message": "ok", "peers_crawled": 91})
    fed = client_with(handler)

    out = await fed.crawl()

    assert out["peers_crawled"] == 91
    assert json.loads(seen["request"].content) == {}


@pytest.mark.asyncio
async def test_call_wraps_execute_with_resource_id_key():
    handler, seen = recorder({"success": True, "status_code": 200, "response_body": {}})
    fed = client_with(handler)

    await fed.call(476, {"query": "x402"})

    req = seen["request"]
    # call goes through execute, NOT the marketplace path -- the two differ in response shape,
    # so routing it to /v1/marketplace/api/476 would silently drop the envelope.
    assert req.url.path == "/v1/federation/execute"
    assert json.loads(req.content) == {"resource_id": 476, "payload": {"query": "x402"}}


@pytest.mark.asyncio
async def test_call_defaults_payload_to_empty_object():
    handler, seen = recorder({"success": True})
    fed = client_with(handler)

    await fed.call(476)

    assert json.loads(seen["request"].content)["payload"] == {}


@pytest.mark.parametrize("bad", [0, -1, "476", None, True, 1.5])
@pytest.mark.asyncio
async def test_call_rejects_bad_resource_id(bad):
    handler, _ = recorder({})
    fed = client_with(handler)

    with pytest.raises(ValueError):
        await fed.call(bad)


# ─── Parity with the sync client ──────────────────────────────────────────────


def test_async_client_covers_every_sync_federation_method():
    """A partial async port is worse than none: callers hit AttributeError at runtime."""
    from jarvisclaw import FederationClient as Sync

    def federation_methods(cls):
        # Only methods defined on the federation class itself — the base client contributes
        # transport helpers that have no business being compared.
        return {n for n, v in vars(cls).items() if callable(v) and not n.startswith("_")}

    missing = federation_methods(Sync) - federation_methods(FederationClient)
    assert not missing, f"async client is missing: {sorted(missing)}"


def test_every_async_federation_method_is_a_coroutine():
    """A def that should have been async def blocks the event loop and returns a plain value."""
    import inspect

    for name, fn in vars(FederationClient).items():
        if not callable(fn) or name.startswith("_"):
            continue
        if isinstance(vars(FederationClient)[name], staticmethod):
            continue
        assert inspect.iscoroutinefunction(fn), f"{name} is not async"
