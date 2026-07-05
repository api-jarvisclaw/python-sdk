"""FederationClient — federated peer discovery and crawling."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient


class FederationClient(BaseClient):
    """Client for AIP federation endpoints.

    Enables discovery of remote AIP-compatible platforms and crawling
    for new peers.

    Usage:
        from jarvisclaw import FederationClient

        fed = FederationClient(api_key="sk-...")
        peers = fed.list_peers()
    """

    def list_peers(
        self,
        *,
        status: str | None = None,
        protocol: str | None = None,
    ) -> dict[str, Any]:
        """List known federation peers.

        Args:
            status: Filter by status ("active", "unreachable")
            protocol: Filter by protocol ("aip", "a2a", "mcp")

        Returns dict with: peers (list of peer objects)
        """
        params: dict[str, Any] = {}
        if status is not None:
            params["status"] = status
        if protocol is not None:
            params["protocol"] = protocol
        return self._get("/v1/aip/federation/peers", params=params)

    def crawl(
        self,
        *,
        seed_urls: list[str] | None = None,
        max_depth: int = 2,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Trigger a federation crawl to discover new peers.

        Args:
            seed_urls: Optional seed URLs to start crawling from
            max_depth: Maximum crawl depth (default: 2)
            timeout: Per-peer timeout in seconds (default: 30)

        Returns dict with: discovered (count), new_peers (list), errors (list)
        """
        body: dict[str, Any] = {
            "max_depth": max_depth,
            "timeout": timeout,
        }
        if seed_urls is not None:
            body["seed_urls"] = seed_urls
        return self._post("/v1/aip/federation/crawl", json=body)
