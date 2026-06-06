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
