# JarvisClaw SDK v2.0 — Agent-Native AIP

The fastest way to build AI agents with automatic intent routing, budget control, and crypto payments.

## Install

```bash
pip install jarvisclaw
```

## 3-Line Quickstart

```python
from jarvisclaw import Agent

agent = Agent()  # uses JARVISCLAW_API_KEY env var
print(agent.ask("explain quantum computing in one sentence"))
```

That's it. AIP resolves the best model for your intent, routes the request, handles payment (API key or x402 crypto), and returns the result.

## Autonomous Agent with Tools

```python
from jarvisclaw import Agent
import requests

agent = Agent(default_budget=0.50)  # max $0.50 per run

@agent.tool
def search(query: str) -> str:
    """Search the web for current information."""
    resp = requests.get(f"https://api.search.com/v1?q={query}")
    return resp.json()["results"][0]["snippet"]

@agent.tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression."""
    return str(eval(expression))  # sandboxed in production

# The agent autonomously decides when to use tools
result = agent.run("What's the mass of Jupiter in kg, and what's that divided by Earth's mass?")
print(result.text)           # Final answer
print(result.cost.spent_usd) # How much it cost
print(result.iterations)     # How many LLM calls
```

## Streaming

```python
from jarvisclaw import Agent

agent = Agent()
for chunk in agent.stream("write a haiku about distributed systems"):
    print(chunk, end="", flush=True)
```

## OpenAI Drop-in Replacement

Zero code changes. Just swap the import:

```python
# Before:
# from openai import OpenAI

# After:
from jarvisclaw.openai_compat import OpenAI

client = OpenAI()  # uses JARVISCLAW_API_KEY
resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
)
print(resp.choices[0].message.content)
```

You get AIP intent routing, automatic provider failover, and optional x402 crypto payments — all invisible to your existing code.

## Budget Guards

Never overspend. Set limits at any level:

```python
# Per-agent default
agent = Agent(default_budget=5.00)

# Per-run override
result = agent.run("analyze this dataset", budget=1.00)

# Session tracking
print(agent.cost_summary())
# {'budget_usd': 5.0, 'spent_usd': 0.0342, 'remaining_usd': 4.9658, 'requests': 3}

# Server-side limits
agent.set_limits(daily_max_usd=10.0, per_request_max_usd=0.50)
```

If budget is exceeded, `BudgetExceededError` is raised — your agent stops cleanly, never runs away.

## x402 Crypto Payments (Wallet Mode)

Pay per-request with on-chain USDC. No API key needed:

```python
from jarvisclaw import Agent

# EVM wallet
agent = Agent(private_key="0x...")

# Solana wallet  
agent = Agent(private_key="base58...", network="solana")

# Works identically — AIP handles payment signing
result = agent.ask("summarize this research paper")
print(agent.session_cost.spent_usd)  # exact cost
```

## Intent Resolution

See what AIP routes look like under the hood:

```python
resolution = agent.resolve(
    "image_generation",
    max_price=0.05,
    features=["high_resolution"],
    optimize="quality"
)
print(resolution["matches"][0]["provider_id"])  # e.g. "dall-e-3"
```

## All Capabilities

| Feature | Method | Description |
|---------|--------|-------------|
| Single Q&A | `agent.ask(prompt)` | One-shot, returns text |
| Autonomous | `agent.run(task)` | Multi-turn with tools |
| Streaming | `agent.stream(prompt)` | Yields chunks |
| OpenAI compat | `OpenAI().chat.completions.create(...)` | Drop-in |
| Balance | `agent.balance()` | Wallet/quota info |
| History | `agent.history()` | Transaction log |
| Providers | `agent.list_providers()` | Available models |
| Limits | `agent.set_limits(...)` | Spending caps |

## Configuration

| Env Variable | Purpose |
|---|---|
| `JARVISCLAW_API_KEY` | API key authentication |
| `JARVISCLAW_WALLET_KEY` | x402 private key (EVM or Solana) |
| `JARVISCLAW_BASE_URL` | Custom endpoint (default: `https://api.jarvisclaw.ai`) |

## Architecture: How AIP Works

```
Your Code → Agent SDK → Intent Resolution → Risk Check → Route to Best Provider
                              ↓                                    ↓
                       Budget Guard                         Execute + Settle
                              ↓                                    ↓
                       Cost Tracking ←←←←←←←←←←←←←←←← Audit Trail
```

The Agent Intent Protocol (AIP) resolves your request to the optimal provider based on:
- **Cost**: cheapest model that meets quality threshold
- **Quality**: best model within budget
- **Latency**: fastest response time

## Migration from v1.x

```python
# v1.x — still works!
from jarvisclaw import ChatClient
client = ChatClient(api_key="sk-...")
resp = client.chat("hello")

# v2.0 — recommended
from jarvisclaw import Agent
agent = Agent(api_key="sk-...")
print(agent.ask("hello"))
```

All v1.x client classes (`ChatClient`, `ImageClient`, etc.) remain available and unchanged.

## License

MIT
