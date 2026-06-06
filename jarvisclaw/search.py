"""SearchClient — web search via chat completions format."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient
from .types import SearchResult


class SearchClient(BaseClient):
    """Web search client using smart routing (auto/search).

    The backend treats /v1/search as a chat completions request,
    so we send the query as a chat message and extract the response content.

    Usage:
        from jarvisclaw import SearchClient

        search = SearchClient(api_key="sk-...")
        results = search.query("latest AI news")
        for r in results:
            print(r.title, r.url)
    """

    def query(
        self, query: str, *, num_results: int = 10
    ) -> list[SearchResult]:
        """Search the web for a query.

        Args:
            query: Search query string.
            num_results: Maximum number of results to return.
        """
        data = self._post(
            "/v1/search",
            json={
                "model": "auto/search",
                "messages": [{"role": "user", "content": query}],
                "max_results": num_results,
            },
        )
        # Response is chat completion format — extract content
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        # Try to parse structured results from the response
        results = data.get("results", data.get("data", []))
        if results:
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                )
                for r in results
            ]

        # If no structured results, return the content as a single result
        if content:
            return [SearchResult(title="Search Result", url="", snippet=content)]
        return []

    def find_similar(
        self, url: str, *, num_results: int = 10
    ) -> list[SearchResult]:
        """Find pages similar to a given URL.

        Args:
            url: URL to find similar pages for.
            num_results: Maximum number of results to return.
        """
        data = self._post(
            "/v1/search/similar",
            json={
                "model": "auto/search",
                "messages": [{"role": "user", "content": f"Find pages similar to: {url}"}],
                "max_results": num_results,
            },
        )
        results = data.get("results", data.get("data", []))
        if results:
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                )
                for r in results
            ]
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        if content:
            return [SearchResult(title="Search Result", url="", snippet=content)]
        return []

    def contents(self, urls: list[str]) -> list[Any]:
        """Retrieve page contents for a list of URLs.

        Note: Some URLs may fail to fetch server-side; partial results are
        returned depending on upstream behavior (no client-side error raised).

        Args:
            urls: List of URLs to fetch content from.
        """
        data = self._post(
            "/v1/search/contents",
            json={
                "model": "auto/search",
                "messages": [{"role": "user", "content": f"Get contents of: {', '.join(urls)}"}],
                "urls": urls,
            },
        )
        return data.get("results", data.get("data", []))
