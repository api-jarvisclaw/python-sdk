"""MarketplaceClient — generic API for marketplace services."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient


class MarketplaceClient(BaseClient):
    """Generic marketplace client for services without dedicated clients.

    Covers: DEX, phone verification, compute, prediction markets, etc.

    Usage:
        from jarvisclaw import MarketplaceClient

        mp = MarketplaceClient(api_key="sk-...")
        result = mp.call("polymarket", "markets", method="GET")
    """

    def call(
        self,
        service: str,
        path: str,
        *,
        method: str = "GET",
        **kwargs: Any,
    ) -> Any:
        """Make a generic marketplace API call.

        Args:
            service: Service name (e.g., "polymarket", "dex", "phone").
            path: API path within the service.
            method: HTTP method (GET, POST, etc.).
            **kwargs: Additional request params (json, data, params, etc.).
        """
        full_path = f"/v1/marketplace/{service.strip('/')}/{path.lstrip('/')}"
        m = method.upper()
        if m == "GET":
            return self._get(full_path, **kwargs)
        if m == "POST":
            return self._post(full_path, **kwargs)
        # PUT, DELETE, PATCH, etc.
        return self._request(m, full_path, **kwargs)

    # ─── RPC Convenience Methods ────────────────────────────────────────────

    def rpc_call(
        self,
        chain: str,
        method: str,
        params: Any = None,
    ) -> Any:
        """Send a JSON-RPC 2.0 request to a blockchain.

        Args:
            chain: Chain identifier (e.g., "ethereum", "solana", "base").
            method: JSON-RPC method (e.g., "eth_blockNumber", "getBalance").
            params: Method parameters (list or dict).

        Returns:
            Parsed JSON-RPC response.
        """
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or [],
        }
        return self.call("rpc", chain, method="POST", json=body)

    def rpc_batch(
        self,
        chain: str,
        calls: list[tuple[str, Any]],
    ) -> Any:
        """Send multiple JSON-RPC requests in a single batch.

        Args:
            chain: Chain identifier.
            calls: List of (method, params) tuples.

        Returns:
            List of JSON-RPC responses.
        """
        batch = [
            {"jsonrpc": "2.0", "id": i + 1, "method": m, "params": p or []}
            for i, (m, p) in enumerate(calls)
        ]
        return self.call("rpc", chain, method="POST", json=batch)

    # ─── DeFi Convenience Methods ───────────────────────────────────────────

    def defi_protocols(self, **kwargs: Any) -> Any:
        """Get TVL data for DeFi protocols."""
        return self.call("defi", "protocols", method="GET", **kwargs)

    def defi_protocol(self, slug: str, **kwargs: Any) -> Any:
        """Get data for a specific DeFi protocol by slug."""
        return self.call("defi", f"protocol/{slug}", method="GET", **kwargs)

    def defi_yields(self, **kwargs: Any) -> Any:
        """Get current yield/APY data across DeFi protocols."""
        return self.call("defi", "yields", method="GET", **kwargs)

    def defi_tvl(self, **kwargs: Any) -> Any:
        """Get TVL data (alias for protocols)."""
        return self.call("defi", "protocols", method="GET", **kwargs)

