"""EmbeddingsClient — embeddings, reranking, moderation, and the Responses API."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient


class EmbeddingsClient(BaseClient):
    """Client for the non-chat text endpoints.

    Usage:
        from jarvisclaw import EmbeddingsClient

        emb = EmbeddingsClient(api_key="sk-...")
        vector = emb.embed("text-embedding-3-small", "hello world")
    """

    def create(
        self,
        model: str,
        input: Any,
        *,
        encoding_format: str | None = None,
        dimensions: int | None = None,
        user: str | None = None,
    ) -> dict[str, Any]:
        """Create embedding vectors.

        Args:
            model: Embedding model id. Required.
            input: A string, a list of strings, or a token-id array.
            encoding_format: "float" (default) or "base64". Note "base64" makes
                the response carry strings rather than float lists.
            dimensions: Truncate the output vector. Only some models support it.
            user: Optional end-user identifier.

        Returns dict with: object, data (list of {object, index, embedding}),
        model, usage.
        """
        if not model:
            raise ValueError("model is required")
        if input is None:
            raise ValueError("input is required")
        body: dict[str, Any] = {"model": model, "input": input}
        if encoding_format is not None:
            body["encoding_format"] = encoding_format
        if dimensions is not None:
            body["dimensions"] = dimensions
        if user is not None:
            body["user"] = user
        return self._post("/v1/embeddings", json=body)

    def embed(self, model: str, text: str, **kwargs: Any) -> list[float]:
        """Get a single embedding vector for one string."""
        data = self.create(model, text, **kwargs)
        items = data.get("data") or []
        if not items:
            from .errors import APIError

            raise APIError(200, "server returned no vectors", data)
        return items[0].get("embedding") or []

    def embed_batch(self, model: str, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """Get one vector per input string, in input order.

        Results are sorted by the response's `index` field rather than trusting
        array order, which the API does not guarantee.
        """
        data = self.create(model, texts, **kwargs)
        items = data.get("data") or []
        ordered = sorted(items, key=lambda d: d.get("index", 0))
        return [d.get("embedding") or [] for d in ordered]

    def rerank(
        self,
        model: str,
        query: str,
        documents: list[Any],
        *,
        top_n: int | None = None,
        return_documents: bool | None = None,
        max_chunk_per_doc: int | None = None,
        overlap_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Reorder documents by relevance to a query.

        Args:
            model: Rerank model id.
            query: The query to rank against.
            documents: Plain strings or objects, depending on the model.
            top_n: Limit how many ranked results come back.
            return_documents: Echo the documents back in the results.
            max_chunk_per_doc: Chunking limit for long documents.
            overlap_tokens: Token overlap between chunks.

        Returns dict with: results (list of {index, relevance_score, document?}),
        model, usage.
        """
        if not model:
            raise ValueError("model is required")
        if not query:
            raise ValueError("query is required")
        if not documents:
            raise ValueError("documents is required")
        body: dict[str, Any] = {"model": model, "query": query, "documents": documents}
        if top_n is not None:
            body["top_n"] = top_n
        if return_documents is not None:
            body["return_documents"] = return_documents
        if max_chunk_per_doc is not None:
            body["max_chunk_per_doc"] = max_chunk_per_doc
        if overlap_tokens is not None:
            body["overlap_tokens"] = overlap_tokens
        return self._post("/v1/rerank", json=body)

    def rerank_texts(
        self, model: str, query: str, texts: list[str], **kwargs: Any
    ) -> list[dict[str, Any]]:
        """rerank() for plain-string documents, returning just the results list."""
        data = self.rerank(model, query, list(texts), **kwargs)
        return data.get("results") or []

    def moderate(self, input: Any, *, model: str | None = None) -> dict[str, Any]:
        """Classify text against the content policy.

        Args:
            input: A string or list of strings.
            model: Optional moderation model id.

        The result shape is provider-specific and returned as-is.
        """
        if input is None:
            raise ValueError("input is required")
        body: dict[str, Any] = {"input": input}
        if model is not None:
            body["model"] = model
        return self._post("/v1/moderations", json=body)

    def responses(self, request: dict[str, Any]) -> dict[str, Any]:
        """Call the OpenAI-compatible Responses API for multi-turn agent runs.

        The request and response schemas track OpenAI's and change often, so both
        are passed through untyped rather than pinned to a struct that would drift.
        """
        if not request:
            raise ValueError("request is required")
        return self._post("/v1/responses", json=request)
