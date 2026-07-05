"""PromptCoachClient — AI-powered prompt optimization and scoring."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient


class PromptCoachClient(BaseClient):
    """Prompt Coach client for optimizing and scoring prompts.

    Fixed pricing: $0.002 USDC per request regardless of options.

    Usage:
        from jarvisclaw import PromptCoachClient

        # API Key mode
        coach = PromptCoachClient(api_key="sk-...")
        result = coach.optimize("make me a website", context="portfolio site")

        # x402 mode (Agent wallet pays directly)
        coach = PromptCoachClient(private_key="0x...")
        result = coach.optimize("explain AI", optimize_for="technical")
    """

    def optimize(
        self,
        prompt: str,
        *,
        context: str | None = None,
        model: str | None = None,
        optimize_for: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Optimize a prompt and return suggestions.

        Args:
            prompt: The original prompt to optimize.
            context: Optional context about usage (e.g., "technical blog for developers").
            model: Target model the prompt will be used with (e.g., "gpt-4o").
            optimize_for: Optimization strategy — "clarity", "technical", "creative".
            **kwargs: Additional params passed to the API.

        Returns:
            dict with keys:
                - optimized_prompt (str): The improved prompt.
                - suggestions (list[str]): Specific improvement suggestions.
                - score (float): Quality score of the optimized prompt (0-10).
                - score_before (float): Quality score of the original prompt.
                - score_after (float): Quality score after optimization.
        """
        body: dict[str, Any] = {"prompt": prompt, **kwargs}
        if context is not None:
            body["context"] = context
        if model is not None:
            body["model"] = model
        if optimize_for is not None:
            body["optimize_for"] = optimize_for

        return self._request("POST", "/v1/prompt-coach/optimize", json=body)

    def score(
        self,
        prompt: str,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Score a prompt without optimizing it.

        Args:
            prompt: The prompt to evaluate.
            model: Target model context for scoring.
            **kwargs: Additional params passed to the API.

        Returns:
            dict with keys:
                - score (float): Quality score (0-10).
                - breakdown (dict): Per-dimension scores (clarity, specificity, etc.).
        """
        body: dict[str, Any] = {"prompt": prompt, **kwargs}
        if model is not None:
            body["model"] = model

        return self._request("POST", "/v1/prompt-coach/score", json=body)
