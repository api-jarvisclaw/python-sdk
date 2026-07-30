"""PromptCoachClient — AI-powered prompt optimization."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient


class PromptCoachClient(BaseClient):
    """Prompt Coach client for optimizing prompts.

    The coaching model is chosen by the gateway; the `model` argument only tells
    the coach which model your prompt is destined for.

    Usage:
        from jarvisclaw import PromptCoachClient

        # API Key mode
        coach = PromptCoachClient(api_key="sk-...")
        result = coach.optimize("make me a website", context="portfolio site")

        # x402 mode (agent wallet pays directly)
        coach = PromptCoachClient(private_key="0x...")
        result = coach.optimize("explain AI", context="for a physics undergrad")
    """

    def optimize(
        self,
        prompt: str,
        *,
        context: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Optimize a prompt and return suggestions plus before/after scores.

        Args:
            prompt: The original prompt to optimize.
            context: Optional context about the use case (e.g. "technical blog
                for developers").
            model: The model the prompt will be used with (e.g. "gpt-4o"). This
                is passed to the coach as information only — it does not select
                the coaching model.
            **kwargs: Additional params forwarded in the request body.

        Returns:
            dict with keys:
                - original_prompt (str)
                - optimized_prompt (str): the improved prompt
                - explanation (str): what changed and why
                - score_before (int): quality of the original, 1-100
                - score_after (int): quality after optimization, 1-100
                - suggestions (list[str]): specific improvements
                - model_used (str): the coaching model the gateway picked

            Note the scores are integers on a 1-100 scale, not 0-10.

        There is no separate score-only endpoint: to grade a prompt without
        rewriting it, call this and read score_before.
        """
        body: dict[str, Any] = {"prompt": prompt, **kwargs}
        if context is not None:
            body["context"] = context
        if model is not None:
            body["model"] = model

        data = self._post("/v1/prompt-coach/optimize", json=body)
        # The handler wraps its result as {"success": true, "data": {...}} rather
        # than returning the object at the top level.
        if isinstance(data, dict) and "data" in data:
            if not data.get("success", True):
                from .errors import APIError

                raise APIError(200, "prompt optimization failed", data)
            return data["data"]
        return data

    def score(self, prompt: str, *, model: str | None = None, **kwargs: Any) -> int:
        """Score a prompt's quality on a 1-100 scale.

        Convenience wrapper over optimize() returning score_before. The gateway
        has no score-only endpoint — /v1/prompt-coach/score does not exist — so
        this costs the same as a full optimize call.
        """
        result = self.optimize(prompt, model=model, **kwargs)
        return int(result.get("score_before", 0))
