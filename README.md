# JarvisClaw Python SDK

The official Python SDK for [JarvisClaw AI](https://jarvisclaw.ai) — intent-based AI routing with x402 micropayments.

## Install

```bash
pip install jarvisclaw
```

## Quick Start

```python
from jarvisclaw import JarvisClaw

# x402 wallet mode (pay per request, no API key needed)
client = JarvisClaw(private_key="0x...")

# Or API key mode
client = JarvisClaw(api_key="sk-...")

# Execute an intent
result = client.execute(
    intent="chat_completion",
    payload={"messages": [{"role": "user", "content": "Hello!"}]},
    budget={"max_total_usd": 0.05}
)
print(result["result"]["content"])
```

## Core API

### Resolve — Find the best provider without executing

```python
options = client.resolve(
    intent="chat_completion",
    payload={"messages": [{"role": "user", "content": "Explain AIP"}]},
    constraints={"optimize": "cost", "max_latency_ms": 3000}
)

for match in options["matches"]:
    print(f"{match['provider_id']} — ${match['estimated_cost_usd']:.4f}")
```

### Execute — Resolve + run in one call

```python
result = client.execute(
    intent="chat_completion",
    payload={
        "messages": [{"role": "user", "content": "Write a haiku about distributed systems"}],
        "temperature": 0.7,
    },
    budget={"max_total_usd": 0.10}
)

print(result["result"]["content"])
print(f"Cost: ${result['actual_cost_usd']:.6f}")
print(f"Provider: {result['provider']}")
```

### Execute with Budget Guard

```python
result = client.execute_budget(
    intent="chat_completion",
    payload={"messages": [{"role": "user", "content": "Summarize this paper"}]},
    budget={"max_total_usd": 0.03},
    constraints={"optimize": "cost"}
)

# Server enforces budget — will pick cheapest provider that fits
print(f"Spent: ${result['actual_cost_usd']:.6f} (limit was $0.03)")
```

### Stream — Server-Sent Events

```python
for chunk in client.stream(
    intent="chat_completion",
    payload={"messages": [{"role": "user", "content": "Tell me a story"}]},
    budget={"max_total_usd": 0.05}
):
    print(chunk, end="", flush=True)
```

### All Intent Types

```python
# Image generation
result = client.execute(
    intent="image_generation",
    payload={"prompt": "A cyberpunk city at sunset", "size": "1024x1024"},
    budget={"max_total_usd": 0.08}
)
print(result["result"]["url"])

# Text-to-speech
result = client.execute(
    intent="text_to_speech",
    payload={"text": "Hello world", "voice": "alloy"},
    budget={"max_total_usd": 0.01}
)
# result["result"]["audio_url"]

# Code generation
result = client.execute(
    intent="code_generation",
    payload={"messages": [{"role": "user", "content": "Write a Python quicksort"}]},
    budget={"max_total_usd": 0.05}
)

# Embeddings
result = client.execute(
    intent="embedding",
    payload={"input": ["hello world", "goodbye world"]},
    budget={"max_total_usd": 0.001}
)
```

## Streaming Subscribe (Long-running)

```python
subscription = client.subscribe(
    intent="chat_completion",
    payload={"messages": [{"role": "user", "content": "Write an essay"}]},
    budget={"max_total_usd": 0.10},
    stream=True,
)

for event in subscription:
    print(event, end="", flush=True)
```

## Analytics & Audit

```python
# Budget utilization
status = client.budget_status(daily_budget=5.0, monthly_budget=100.0)
print(f"Today: ${status['data']['daily_spent']:.2f} / $5.00")

# Recent transactions
history = client.audit_log(limit=20)
for entry in history["entries"]:
    print(f"{entry['intent']} → {entry['provider']} ${entry['cost_usd']:.4f}")

# Cost breakdown by model
breakdown = client.model_breakdown(days=7)
for model in breakdown["models"]:
    print(f"{model['model_id']}: ${model['total_cost']:.2f} ({model['requests']} reqs)")
```

## Federation — Peer Discovery

```python
# Discover other AIP-compatible platforms
peers = client.discover_peers()
for peer in peers["peers"]:
    print(f"{peer['name']} — {peer['url']}")

# Crawl the AIP network
result = client.crawl_network(seed_urls=["https://peer.example.com/.well-known/aip.json"])
print(f"Discovered {result['discovered']} new peers")
```

## Agent Mode — Autonomous with Tools

For multi-step autonomous tasks with tool use and budget control:

```python
from jarvisclaw import Agent

agent = Agent(private_key="0x...", default_budget=1.00)

@agent.tool
def search(query: str) -> str:
    """Search the web for current information."""
    import requests
    resp = requests.get(f"https://api.search.com/v1?q={query}")
    return resp.json()["results"][0]["snippet"]

@agent.tool
def calculator(expression: str) -> str:
    """Evaluate a math expression."""
    return str(eval(expression))

result = agent.run("What's Jupiter's mass divided by Earth's mass?")
print(result.text)
print(f"Cost: ${result.cost.spent_usd:.4f}")
print(f"Iterations: {result.iterations}")
```

### Agent Streaming

```python
agent = Agent(private_key="0x...")
for chunk in agent.stream("Write a haiku about distributed systems"):
    print(chunk, end="", flush=True)
```

### Agent Budget Guards

```python
from jarvisclaw import Agent, BudgetExceededError

agent = Agent(default_budget=2.00)

try:
    result = agent.run("analyze this massive dataset", budget=0.50)
except BudgetExceededError as e:
    print(f"Stopped at ${e.spent:.4f} — limit was ${e.budget:.2f}")
```

## x402 Wallet Payments

Pay per-request with on-chain USDC. No API key, no account needed:

```python
# EVM (Base network)
client = JarvisClaw(private_key="0x...")

# Solana
client = JarvisClaw(private_key="base58...", network="solana")

# Check balance
balance = client.get_balance()
print(f"Wallet balance: ${balance:.2f} USDC")
```

## OpenAI / Anthropic SDK Compatibility

Use official SDKs directly against JarvisClaw — just change the base URL:

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-your-jarvisclaw-key",
    base_url="https://api.jarvisclaw.ai/v1"
)

resp = client.chat.completions.create(
    model="anthropic/claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(resp.choices[0].message.content)
```

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-your-jarvisclaw-key",
    base_url="https://api.jarvisclaw.ai"
)

message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}]
)
print(message.content[0].text)
```

> **When to use which?**
> - `JarvisClaw` — intent routing, x402 payments, budget control, federation
> - `Agent` — autonomous multi-step tasks with tools
> - `openai`/`anthropic` SDK — drop-in for existing code, Claude/GPT native features

## Configuration

| Env Variable | Purpose |
|---|---|
| `JARVISCLAW_API_KEY` | API key authentication |
| `JARVISCLAW_WALLET_KEY` | x402 private key (EVM or Solana) |
| `JARVISCLAW_BASE_URL` | Custom endpoint (default: `https://api.jarvisclaw.ai`) |

## Migration from v2.x

```python
# v2.x — still works
from jarvisclaw import IntentClient
client = IntentClient(private_key="0x...")
client.execute(...)

# v2.3+ — recommended unified interface
from jarvisclaw import JarvisClaw
client = JarvisClaw(private_key="0x...")
client.execute(...)
```

All existing classes (`IntentClient`, `Agent`, `ChatClient`, etc.) remain available and unchanged.

## Links

- [AIP Protocol Spec](https://docs.jarvisclaw.ai/aip)
- [SDK Reference](https://docs.jarvisclaw.ai/sdk)
- [Telegram](https://t.me/JarvisClawai)

## License

MIT
