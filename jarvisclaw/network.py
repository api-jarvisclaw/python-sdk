"""NetworkClient — AIP network peer management and the public registry."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient


class NetworkClient(BaseClient):
    """Client for AIP network endpoints.

    Two groups of endpoints live here:

    - The public registry (search, servers, resources) needs no auth at all.
    - Peer management (list_peers, add_peer, remove_peer, crawl) sits behind
      AdminAuth, which requires a dashboard session or an access token plus a
      New-Api-User header. An API key or x402 wallet gets 401 on those, by
      design — use the registry methods, or JarvisClaw.discover_peers, instead.

    Usage:
        from jarvisclaw import NetworkClient

        fed = NetworkClient(api_key="sk-...")
        resources = fed.search("crypto price")   # public
        servers = fed.list_servers()             # public
    """

    # ─── Public registry (no auth) ────────────────────────────────────────────

    def search(
        self,
        query: str = "",
        *,
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search callable resources across every known peer.

        Args:
            query: Free-text match on the resource.
            category: Exact category match.
            limit: Max results (default 20).

        Returns a list of resources, each with: resource_id, name, path, method,
        description, category, tags, price_input, price_output, sell_price,
        price_unit, currency, network, popular, call_count, server_name,
        updated_at.

        sell_price is what this gateway charges you. Pass resource_id to
        ``call(...)`` to invoke a result.
        """
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["q"] = query
        if category is not None:
            params["category"] = category
        data = self._get("/v1/federation/search", params=params)
        self._raise_if_failed(data, "network search failed")
        return data.get("data") or []

    def list_servers(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        """List peers in the public registry, paginated.

        page is 1-based; page_size is clamped to 1..100 server-side.

        Returns dict with: success, data (server_uuid, name, base_url,
        description, network, verified, resource_count, healthy, last_checked_at,
        capabilities, aip_version, discover_url, latency_ms), total, page,
        page_size.
        """
        return self._get(
            "/v1/federation/servers",
            params={"page": page, "page_size": page_size},
        )

    def list_resources(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """List APIs published across the network, paginated.

        Returns dict with: success, data, total, page, page_size.
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if category is not None:
            params["category"] = category
        if keyword is not None:
            params["keyword"] = keyword
        return self._get("/v1/federation/resources", params=params)

    def health(self) -> dict[str, Any]:
        """Get network health status. Public, no auth required."""
        return self._get("/v1/federation/health")

    # ─── API catalogue and direct invocation ──────────────────────────────────

    def list_apis(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        category: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """List the marketplace API catalogue, paginated. Public, no auth required.

        The customer-facing view of the same capacity list_resources returns: priced in
        marketplace terms, and excluding anything without a usable price.

        page_size is clamped to 200 server-side; the unpaginated form was a ~1.5 MB response.

        Returns dict with: success, data (items, total, page, page_size).
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if category is not None:
            params["category"] = category
        if keyword is not None:
            params["q"] = keyword
        return self._get("/api/marketplace/apis", params=params)

    def invoke(
        self,
        resource_id: int,
        *,
        payload: dict[str, Any] | None = None,
        method: str = "POST",
    ) -> Any:
        """Call a catalogue API directly by resource_id; the gateway settles with the peer.

        Needs an API key or x402 payment. Takes a resource_id straight from list_apis or search,
        so a caller needs to know nothing about the network subsystem — that decoupling is
        the point of this endpoint over execute.

        Args:
            resource_id: Positive integer handle from list_apis / search.
            payload: Request body for POST, or query parameters for GET.
            method: "POST" (default) or "GET", matching the resource's own method.

        Returns the upstream response body.
        """
        if not isinstance(resource_id, int) or isinstance(resource_id, bool) or resource_id <= 0:
            raise ValueError("resource_id must be a positive integer")
        path = f"/v1/marketplace/api/{resource_id}"
        if method.upper() == "GET":
            return self._get(path, params=payload or {})
        # No body at all when there is no payload, rather than "{}". The gateway keeps an
        # absent body absent on purpose (readFederationPayload), because an empty object
        # is a real difference to an upstream that expects no input.
        if payload is None:
            return self._post(path)
        return self._post(path, json=payload)

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        """Invoke a federated resource; the gateway settles with the peer.

        Takes the raw request body. Two wrappers cover the common cases, and they are not
        interchangeable:

        - ``call(resource_id, payload)`` wraps THIS endpoint, so it keeps execute's
          request/response envelope (``success``, ``status_code``, ``response_body``).
        - ``invoke(resource_id, payload)`` goes to ``/v1/marketplace/api/{id}`` instead and
          returns the upstream body directly, with no envelope to unwrap.

        Prefer one of those unless you need to set fields this SDK does not model.

        Requires an API key or x402 payment (not admin rights).
        """
        return self._post("/v1/federation/execute", json=request)

    def call(
        self,
        resource_id: int,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke a catalogue resource by its ``resource_id``.

        This is the follow-up to ``search(...)``::

            hits = fed.search("google search")
            result = fed.call(hits[0]["resource_id"], {"query": "x402"})

        ``execute`` takes an untyped body, so a caller had to know the key is
        ``resource_id`` rather than ``id``. This wraps it.

        Requires an API key or x402 payment.
        """
        # bool is excluded explicitly: it subclasses int, so True would otherwise be
        # accepted and sent as resource_id=1 -- a request for someone else's resource.
        if isinstance(resource_id, bool) or not isinstance(resource_id, int) or resource_id <= 0:
            raise ValueError(f"resource_id must be a positive int, got {resource_id!r}")
        body: dict[str, Any] = {"resource_id": resource_id}
        # Omitted rather than sent as {} when absent, for the reason given in invoke.
        if payload is not None:
            body["payload"] = payload
        return self.execute(body)

    # ─── Peer management (admin only) ─────────────────────────────────────────

    def list_peers(self) -> list[dict[str, Any]]:
        """List registered network peers. Admin-only (see class docstring).

        Returns a list of peers with camelCase keys — id, name, url, status
        ("online" | "offline"), lastSeen, resourceCount, capabilities,
        aipVersion, discoverUrl, latencyMs — unlike the snake_case used
        everywhere else in this SDK.
        """
        data = self._get("/v1/aip/federation/peers")
        self._raise_if_failed(data, "listing network peers failed")
        return data.get("data") or []

    def add_peer(self, domain: str) -> dict[str, Any]:
        """Register a peer domain, to be crawled on the next cycle.

        Admin-only. domain is a bare host or base URL, not a peer id.
        """
        if not domain:
            raise ValueError("domain is required")
        return self._post("/v1/aip/federation/peers", json={"domain": domain})

    def remove_peer(self, domain: str) -> dict[str, Any]:
        """Deregister a peer. Admin-only.

        The peer is identified by domain in the request body, not by id in the
        path.
        """
        if not domain:
            raise ValueError("domain is required")
        return self._delete("/v1/aip/federation/peers", json={"domain": domain})

    def crawl(self) -> dict[str, Any]:
        """Trigger an immediate crawl of every registered peer. Admin-only.

        Takes no seed URLs or depth — the crawl covers all registered peers, so
        register targets with add_peer first.

        Returns dict with: message, peers_crawled, healthy, results.
        """
        return self._post("/v1/aip/federation/crawl", json={})

    @staticmethod
    def _raise_if_failed(data: Any, message: str) -> None:
        """Raise for handlers that report failure in a 200 body."""
        if isinstance(data, dict) and data.get("success") is False:
            from .errors import APIError

            raise APIError(200, data.get("message") or data.get("error") or message, data)
