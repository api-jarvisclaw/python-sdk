"""UserAPIClient — browse and invoke community-published APIs (UAPI)."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient


class UserAPIClient(BaseClient):
    """Client for the UAPI marketplace.

    Two route families are involved: /api/user-api/* to browse (public), and
    /v1/uapi/{slug}/* to invoke (paid).

    Usage:
        from jarvisclaw import UserAPIClient

        uapi = UserAPIClient(api_key="sk-...")
        apis = uapi.list(category="data")
        result = uapi.call("weather", "forecast", method="POST", json={"city": "Tokyo"})
    """

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        """Browse published APIs. Public, no auth required.

        Args:
            page: 1-based page number.
            page_size: Clamped to 1..100 server-side.
            category: Filter by category.
            search: Free-text match on name and description.
            sort: Server-defined sort key.

        Returns dict with: success, data, total, page, page_size.

        Each entry's price_per_call is the post-markup price you actually pay.
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if category is not None:
            params["category"] = category
        if search is not None:
            params["search"] = search
        if sort is not None:
            params["sort"] = sort
        data = self._get("/api/user-api/list", params=params)
        self._raise_if_failed(data, "listing user APIs failed")
        return data

    def detail(self, slug: str) -> dict[str, Any]:
        """Get one published API with its endpoint list. Public, no auth."""
        if not slug:
            raise ValueError("slug is required")
        data = self._get(f"/api/user-api/detail/{slug}")
        self._raise_if_failed(data, "api not found")
        return data

    def leaderboard(self) -> dict[str, Any]:
        """Get the top published APIs by usage. Public, no auth."""
        return self._get("/api/user-api/leaderboard")

    def ratings(self, slug: str) -> dict[str, Any]:
        """Get user ratings for a published API. Public, no auth."""
        if not slug:
            raise ValueError("slug is required")
        return self._get(f"/api/user-api/ratings/{slug}")

    def call(
        self,
        slug: str,
        path: str = "",
        *,
        method: str = "GET",
        **kwargs: Any,
    ) -> Any:
        """Invoke a published API; the gateway pays the provider on your behalf.

        Requires an API key or x402 payment.

        Args:
            slug: The API's slug.
            path: API-relative sub-path, with or without a leading slash.
            method: HTTP method.
            **kwargs: Passed to the request (json, params, data, …).

        Returns the decoded JSON response.
        """
        if not slug:
            raise ValueError("slug is required")
        full = f"/v1/uapi/{slug.strip('/')}/{path.lstrip('/')}"
        return self._request(method.upper(), full, **kwargs)

    def call_raw(self, slug: str, path: str = "", *, method: str = "GET", **kwargs: Any):
        """call() returning the raw response, for non-JSON or streaming payloads."""
        if not slug:
            raise ValueError("slug is required")
        full = f"/v1/uapi/{slug.strip('/')}/{path.lstrip('/')}"
        return self._request_raw(method.upper(), full, **kwargs)

    @staticmethod
    def _raise_if_failed(data: Any, message: str) -> None:
        """Raise for handlers that report failure inside a 200 body."""
        if isinstance(data, dict) and data.get("success") is False:
            from .errors import APIError

            raise APIError(200, data.get("message") or message, data)
