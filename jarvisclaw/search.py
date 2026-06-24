"""SearchClient — web search via chat completions format."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient
from .types import SearchResult


class SearchClient(BaseClient):
    """Web search client using smart routing (auto/search).

    The backend routes /v1/search as a chat completions request to a
    search-capable model, so we send the query as a chat message.

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

        # Try structured results first (some providers return these)
        results = data.get("results", data.get("data", []))
        if isinstance(results, list) and results:
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", r.get("text", "")),
                )
                for r in results
                if isinstance(r, dict)
            ]

        # Search-summary format: {"summary": "...", "citations": [...]}
        summary = data.get("summary", "")
        if summary:
            citations = data.get("citations", [])
            if isinstance(citations, list) and citations:
                return [
                    SearchResult(
                        title=c.get("title", ""),
                        url=c.get("url", ""),
                        snippet=c.get("snippet", c.get("text", "")),
                    )
                    for c in citations
                    if isinstance(c, dict)
                ]
            # No structured citations — return summary as a single result
            return [SearchResult(title="Search Result", url="", snippet=summary)]

        # Chat completion format: {"choices": [{"message": {"content": "..."}}]}
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            if content:
                return [SearchResult(title="Search Result", url="", snippet=content)]

        return []

    def find_similar(
        self, url: str, *, num_results: int = 10
    ) -> list[SearchResult]:
        """Find pages similar to a given URL.

        Routes through the marketplace Exa service for similarity search.

        Args:
            url: URL to find similar pages for.
            num_results: Maximum number of results to return.
        """
        data = self._post(
            "/v1/marketplace/exa/find-similar",
            json={
                "url": url,
                "numResults": num_results,
            },
        )
        results = data.get("results", data.get("data", []))
        if results:
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("text", r.get("snippet", "")),
                )
                for r in results
            ]
        return []

    def contents(self, urls: list[str]) -> list[Any]:
        """Retrieve page contents for a list of URLs.

        Routes through the marketplace Exa service for content extraction.

        Args:
            urls: List of URLs to fetch content from.
        """
        data = self._post(
            "/v1/marketplace/exa/contents",
            json={
                "ids": urls,
            },
        )
        return data.get("results", data.get("data", []))
