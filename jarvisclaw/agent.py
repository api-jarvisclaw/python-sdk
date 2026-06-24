"""High-level Agent class — Agent-Native AIP experience.

3-line quickstart:
    agent = Agent(api_key="sk-...")
    result = agent.ask("explain quantum computing")

Full autonomous agent with tools:
    @agent.tool
    def search(query: str) -> str:
        return requests.get(f"https://api.search.com?q={query}").text

    result = agent.run("research latest AI papers and summarize", budget=0.50)
"""
from __future__ import annotations

import inspect
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Generator, Optional

from ._base import BaseClient, DEFAULT_BASE_URL


@dataclass
class CostTracker:
    """Tracks spending per-session and per-run with budget enforcement."""
    budget_usd: float = float("inf")
    spent_usd: float = 0.0
    requests_made: int = 0
    _history: list[dict] = field(default_factory=list)

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget_usd - self.spent_usd)

    @property
    def over_budget(self) -> bool:
        return self.spent_usd >= self.budget_usd

    def record(self, cost_usd: float, model: str, tokens: int = 0):
        self.spent_usd += cost_usd
        self.requests_made += 1
        self._history.append({
            "model": model,
            "cost_usd": cost_usd,
            "tokens": tokens,
            "timestamp": time.time(),
        })

    def summary(self) -> dict:
        return {
            "budget_usd": self.budget_usd if self.budget_usd != float("inf") else None,
            "spent_usd": round(self.spent_usd, 6),
            "remaining_usd": round(self.remaining, 6) if self.budget_usd != float("inf") else None,
            "requests": self.requests_made,
            "history": self._history[-10:],  # last 10
        }


@dataclass
class ToolDef:
    """Internal representation of a registered tool."""
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable


class BudgetExceededError(Exception):
    """Raised when a run exceeds its budget."""
    def __init__(self, budget: float, spent: float):
        self.budget = budget
        self.spent = spent
        super().__init__(f"Budget exceeded: ${spent:.4f} spent of ${budget:.4f} allowed")


class Agent(BaseClient):
    """Autonomous AI agent with intent resolution, tool use, budget control, and streaming.

    Quickstart (3 lines):
        from jarvisclaw import Agent

        agent = Agent()  # uses JARVISCLAW_API_KEY env var
        print(agent.ask("what is AIP?"))

    With budget + tools:
        agent = Agent(api_key="sk-...", default_budget=1.00)

        @agent.tool
        def calculator(expression: str) -> str:
            \"\"\"Evaluate a math expression.\"\"\"
            return str(eval(expression))

        result = agent.run("what's 2^100 + 3^50?")
        print(result.text)
        print(result.cost)  # shows how much was spent

    x402 crypto payment mode:
        agent = Agent(private_key="0x...")
        result = agent.ask("summarize this paper", budget=0.02)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        private_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 120,
        network: str | None = None,
        default_model: str | None = None,
        default_budget: float = float("inf"),
        max_iterations: int = 10,
        system_prompt: str | None = None,
    ):
        super().__init__(
            api_key=api_key,
            private_key=private_key,
            base_url=base_url,
            timeout=timeout,
            network=network,
        )
        self.default_model = default_model
        self.default_budget = default_budget
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt or (
            "You are a helpful AI assistant. Use the available tools when needed "
            "to accomplish the user's task. Be concise and accurate."
        )
        self._tools: dict[str, ToolDef] = {}
        self._session_cost = CostTracker()

    # ═══════════════════════════════════════════════════════════════════
    # Tool Registration
    # ═══════════════════════════════════════════════════════════════════

    def tool(self, fn: Callable | None = None, *, name: str | None = None, description: str | None = None):
        """Register a function as an agent tool. Use as decorator:

            @agent.tool
            def search(query: str) -> str:
                \"\"\"Search the web for information.\"\"\"
                return requests.get(f"https://search.api?q={query}").text

        Or with explicit metadata:
            @agent.tool(name="web_search", description="Search the internet")
            def search(query: str) -> str:
                ...
        """
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or func.__doc__ or f"Tool: {tool_name}"
            # Extract parameter schema from type hints
            params = self._extract_params(func)
            self._tools[tool_name] = ToolDef(
                name=tool_name,
                description=tool_desc.strip(),
                parameters=params,
                fn=func,
            )
            return func

        if fn is not None:
            # Used as @agent.tool without parens
            return decorator(fn)
        return decorator

    def _extract_params(self, func: Callable) -> dict[str, Any]:
        """Extract JSON Schema parameters from function signature."""
        sig = inspect.signature(func)
        hints = func.__annotations__
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            prop: dict[str, Any] = {}
            hint = hints.get(param_name)
            if hint == str:
                prop["type"] = "string"
            elif hint == int:
                prop["type"] = "integer"
            elif hint == float:
                prop["type"] = "number"
            elif hint == bool:
                prop["type"] = "boolean"
            elif hint == list:
                prop["type"] = "array"
            elif hint == dict:
                prop["type"] = "object"
            else:
                prop["type"] = "string"

            properties[param_name] = prop
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def _tools_as_openai_format(self) -> list[dict]:
        """Convert registered tools to OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    # ═══════════════════════════════════════════════════════════════════
    # Core: ask() — single-turn (simple)
    # ═══════════════════════════════════════════════════════════════════

    def ask(
        self,
        prompt: str,
        *,
        budget: float | None = None,
        model: str | None = None,
        optimize: str = "cost",
        **kwargs,
    ) -> str:
        """Ask a single question. Simplest interface — returns text directly.

        Args:
            prompt: Your question or instruction
            budget: Max USD for this request (default: self.default_budget)
            model: Override model (skip intent resolution if provided)
            optimize: "cost", "quality", or "latency"
            **kwargs: Extra params passed to chat completion

        Returns:
            The assistant's response text
        """
        effective_budget = budget if budget is not None else self.default_budget
        tracker = CostTracker(budget_usd=effective_budget)

        resolved_model = model or self.default_model
        if resolved_model is None:
            resolved_model = self._resolve_model("chat_completion", effective_budget, optimize)

        payload = {
            "model": resolved_model,
            "messages": [{"role": "user", "content": prompt}],
            **kwargs,
        }
        resp = self._request("POST", "/v1/chat/completions", json=payload)
        text = self._extract_text(resp)

        # Track cost
        cost = self._estimate_cost(resp, resolved_model)
        tracker.record(cost, resolved_model)
        self._session_cost.record(cost, resolved_model)

        return text

    # ═══════════════════════════════════════════════════════════════════
    # Core: run() — autonomous multi-turn with tool use
    # ═══════════════════════════════════════════════════════════════════

    @dataclass
    class RunResult:
        """Result of an autonomous agent run."""
        text: str
        cost: CostTracker
        iterations: int
        tool_calls: list[dict] = field(default_factory=list)

        def __str__(self):
            return self.text

    def run(
        self,
        task: str,
        *,
        budget: float | None = None,
        model: str | None = None,
        optimize: str = "cost",
        max_iterations: int | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> "Agent.RunResult":
        """Run an autonomous agent loop: resolve → execute → tool calls → iterate.

        The agent will use registered tools as needed, iterating until the task
        is complete or budget/iteration limits are reached.

        Args:
            task: The task description / goal
            budget: Max USD for entire run (default: self.default_budget)
            model: Override model
            optimize: "cost", "quality", or "latency"
            max_iterations: Override self.max_iterations
            stream_callback: Optional callback for streaming tokens

        Returns:
            RunResult with .text, .cost, .iterations, .tool_calls
        """
        effective_budget = budget if budget is not None else self.default_budget
        max_iter = max_iterations or self.max_iterations
        tracker = CostTracker(budget_usd=effective_budget)
        tool_call_log: list[dict] = []

        resolved_model = model or self.default_model
        if resolved_model is None:
            resolved_model = self._resolve_model("chat_completion", effective_budget, optimize)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task},
        ]

        tools_payload = self._tools_as_openai_format() if self._tools else None

        for iteration in range(max_iter):
            # Budget guard
            if tracker.over_budget:
                raise BudgetExceededError(tracker.budget_usd, tracker.spent_usd)

            # Build request
            req_body: dict[str, Any] = {
                "model": resolved_model,
                "messages": messages,
            }
            if tools_payload:
                req_body["tools"] = tools_payload
                req_body["tool_choice"] = "auto"

            resp = self._request("POST", "/v1/chat/completions", json=req_body)
            cost = self._estimate_cost(resp, resolved_model)
            tracker.record(cost, resolved_model)
            self._session_cost.record(cost, resolved_model)

            choice = resp.get("choices", [{}])[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")

            # Stream callback for partial text
            if stream_callback and message.get("content"):
                stream_callback(message["content"])

            # Check for tool calls
            tool_calls = message.get("tool_calls")
            if tool_calls and finish_reason == "tool_calls":
                messages.append(message)
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    fn_args_str = tc["function"].get("arguments", "{}")
                    try:
                        fn_args = json.loads(fn_args_str)
                    except json.JSONDecodeError:
                        fn_args = {}

                    # Execute tool
                    result_str = self._execute_tool(fn_name, fn_args)
                    tool_call_log.append({
                        "tool": fn_name,
                        "args": fn_args,
                        "result": result_str[:500],
                        "iteration": iteration,
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str,
                    })
                continue  # Next iteration with tool results

            # No tool calls — task complete
            final_text = message.get("content", "")
            return Agent.RunResult(
                text=final_text,
                cost=tracker,
                iterations=iteration + 1,
                tool_calls=tool_call_log,
            )

        # Max iterations reached
        last_content = messages[-1].get("content", "") if messages else ""
        return Agent.RunResult(
            text=f"[max iterations reached] {last_content}",
            cost=tracker,
            iterations=max_iter,
            tool_calls=tool_call_log,
        )

    def _execute_tool(self, name: str, args: dict) -> str:
        """Execute a registered tool and return its string result."""
        tool_def = self._tools.get(name)
        if not tool_def:
            return f"Error: unknown tool '{name}'"
        try:
            result = tool_def.fn(**args)
            return str(result) if result is not None else ""
        except Exception as e:
            return f"Error executing {name}: {type(e).__name__}: {e}"

    # ═══════════════════════════════════════════════════════════════════
    # Core: stream() — streaming response
    # ═══════════════════════════════════════════════════════════════════

    def stream(
        self,
        prompt: str,
        *,
        budget: float | None = None,
        model: str | None = None,
        optimize: str = "cost",
    ) -> Generator[str, None, None]:
        """Stream a response token by token. Yields text chunks.

        Usage:
            for chunk in agent.stream("write a poem"):
                print(chunk, end="", flush=True)
        """
        effective_budget = budget if budget is not None else self.default_budget
        resolved_model = model or self.default_model
        if resolved_model is None:
            resolved_model = self._resolve_model("chat_completion", effective_budget, optimize)

        payload = {
            "model": resolved_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }

        resp = self._post_raw("/v1/chat/completions", json=payload, stream=True)
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content
            except json.JSONDecodeError:
                continue

    # ═══════════════════════════════════════════════════════════════════
    # Intent Resolution
    # ═══════════════════════════════════════════════════════════════════

    def resolve(self, intent: str, *, max_price: float | None = None,
                features: list[str] | None = None, optimize: str = "cost") -> dict:
        """Resolve an intent to the best provider match via AIP protocol."""
        payload: dict[str, Any] = {
            "intent": intent,
            "constraints": {},
            "preferences": {"optimize_for": optimize},
        }
        if max_price is not None:
            payload["constraints"]["max_price_usd"] = max_price
        if features:
            payload["constraints"]["features"] = features
        return self._request("POST", "/v1/intent/resolve", json=payload)

    def _resolve_model(self, intent: str, budget: float, optimize: str) -> str:
        """Resolve best model for intent within budget."""
        max_price = budget if budget != float("inf") else None
        try:
            resolved = self.resolve(intent, max_price=max_price, optimize=optimize)
            matches = resolved.get("matches", [])
            if matches:
                return matches[0].get("model", matches[0].get("provider_id", "auto/smart"))
        except Exception:
            pass
        return "auto/smart"  # fallback to auto-routing

    # ═══════════════════════════════════════════════════════════════════
    # Wallet & Treasury
    # ═══════════════════════════════════════════════════════════════════

    def balance(self) -> dict:
        """Get wallet balance (quota + HD wallet + subscription)."""
        return self._request("GET", "/v1/wallet/balance")

    def history(self, page: int = 1, page_size: int = 20, category: str | None = None) -> dict:
        """Get transaction history."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if category:
            params["category"] = category
        return self._request("GET", "/v1/wallet/history", params=params)

    def spending_limits(self) -> dict:
        """Get current spending limits."""
        return self._request("GET", "/v1/wallet/limits")

    def set_limits(self, *, daily_max_usd: float | None = None,
                   per_request_max_usd: float | None = None,
                   monthly_max_usd: float | None = None) -> dict:
        """Update spending limits."""
        payload = {}
        if daily_max_usd is not None:
            payload["daily_max_usd"] = daily_max_usd
        if per_request_max_usd is not None:
            payload["per_request_max_usd"] = per_request_max_usd
        if monthly_max_usd is not None:
            payload["monthly_max_usd"] = monthly_max_usd
        return self._request("PUT", "/v1/wallet/limits", json=payload)

    # ═══════════════════════════════════════════════════════════════════
    # Providers
    # ═══════════════════════════════════════════════════════════════════

    def list_providers(self) -> dict:
        """List all available providers."""
        return self._request("GET", "/v1/providers")

    def list_intent_types(self) -> list[str]:
        """List supported intent types."""
        resp = self._request("GET", "/v1/intent/types")
        return resp.get("intent_types", [])

    # ═══════════════════════════════════════════════════════════════════
    # Session Cost Tracking
    # ═══════════════════════════════════════════════════════════════════

    @property
    def session_cost(self) -> CostTracker:
        """Access session-level cost tracking."""
        return self._session_cost

    def cost_summary(self) -> dict:
        """Get spending summary for this session."""
        return self._session_cost.summary()

    # ═══════════════════════════════════════════════════════════════════
    # Internal Helpers
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _extract_text(resp: dict) -> str:
        """Extract text from OpenAI-format chat completion response."""
        choices = resp.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""

    @staticmethod
    def _estimate_cost(resp: dict, model: str) -> float:
        """Estimate cost from usage field in response."""
        usage = resp.get("usage", {})
        if not usage:
            return 0.0
        # Use server-reported cost if available
        if "total_cost_usd" in usage:
            return usage["total_cost_usd"]
        # Fallback: estimate from tokens (rough per-token pricing)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        # Conservative estimate: $0.01/1K tokens average
        total_tokens = prompt_tokens + completion_tokens
        return total_tokens * 0.00001
