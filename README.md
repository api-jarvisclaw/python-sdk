# JarvisClaw Python SDK

The official Python SDK for [JarvisClaw AI](https://jarvisclaw.ai) — intent-based AI routing with x402 micropayments.

## Install

```bash
pip install jarvisclaw
```

## Examples

Eleven runnable scripts under [examples/](examples/), each executed against the
live gateway — so the field names in them reflect what the server actually
returns:

```bash
export JARVISCLAW_API_KEY=sk-...
python examples/01_chat.py
```

Covering chat, agents, wallet, intents, embeddings, search, images, OpenAI
compatibility, marketplace, async, and the unified client.

## Two billing paths

Worth knowing before your first call, because it explains a class of confusing
failures:

- **Account quota** — you name a model explicitly (`model="openai/gpt-4o-mini"`).
- **x402 on-chain USDC** — anything routed through `auto/*` (smart routing,
  `auto/search`) plus every marketplace service, settled against your HD wallet.

The second path needs USDC in the wallet *even with API-key auth*. Without it you
get `payment settlement failed` after a slow retry, or a 403 `insufficient HD
wallet balance` — not an obvious "out of funds" message.

Capping `max_tokens` is also worth the keystrokes on a low balance: the gateway
reserves against the model's full output allowance before the call, so an
uncapped request can be refused even when the reply would have been cheap.

## Quick Start

```python
from jarvisclaw import JarvisClaw

# x402 wallet mode (pay per request, no API key needed)
client = JarvisClaw(private_key="0x...")

# Or API key mode
client = JarvisClaw(api_key="sk-...")

# Execute an intent. The response is the raw provider payload — for
# chat_completion that means an OpenAI-shaped body.
result = client.execute(
    intent="chat_completion",
    payload={"messages": [{"role": "user", "content": "Hello!"}]},
)
print(result["choices"][0]["message"]["content"])
```

## Core API

### Resolve — Find the best provider without executing

```python
options = client.resolve(
    intent="chat_completion",
    constraints={"max_price_usd": 0.01, "max_latency_ms": 3000},
)

for match in options["matches"]:
    print(f"{match['provider_id']} {match['model']} — ${match['estimated_price_usd']:.6f}")
```

`resolve` takes no payload: it ranks providers for an intent, it does not run
anything. Constraint keys are `max_price_usd`, `max_latency_ms` and `features`.

### Execute — Resolve + run in one call

```python
result = client.execute(
    intent="chat_completion",
    payload={
        "messages": [{"role": "user", "content": "Write a haiku about distributed systems"}],
        "temperature": 0.7,
    },
)
print(result["choices"][0]["message"]["content"])
```

Without a budget, `execute` forwards the payload and returns the provider's own
response. Pass a budget (or use `execute_budget`) to get the wrapped form with
cost and settlement metadata instead.

### Execute with Budget Guard

```python
result = client.execute_budget(
    intent="chat_completion",
    payload={"messages": [{"role": "user", "content": "Summarize this paper"}]},
    budget={"max_total_usd": 0.03},
)

print(result["status"])                       # "success" | "rejected" | "error"
print(f"Spent: ${result['actual_cost_usd']:.6f} (limit was $0.03)")
print(result["result"])                       # the provider response
```

A rejected request does not raise — check `status`, and read `reason` when it is
not `"success"`.

### Stream — Server-Sent Events

```python
for event in client.stream(
    intent="chat_completion",
    payload={"messages": [{"role": "user", "content": "Tell me a story"}]},
):
    if event["event"] == "metadata":
        print("provider:", event["data"]["provider"])
        continue
    chunk = event["data"]
    if isinstance(chunk, dict):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        print(delta.get("content", ""), end="", flush=True)
```

`stream` yields `{"event": ..., "data": ...}` dicts, not bare text. The first
event is `metadata` and the last is `done`; in between the gateway relays the
upstream events verbatim, so `data` holds OpenAI-style chunks — including the
literal `"[DONE]"` sentinel, which arrives as a string rather than a dict.

This endpoint takes no budget. Use `execute_budget` when you need a spend cap.
`client.subscribe(...)` is the same call under its documented name.

### Intent Types

`chat_completion`, `image_generation`, `video_generation`, `text_to_speech`,
`web_search`, `knowledge_search`, `prompt_optimization`, `document_processing`,
`translation`, `code_generation`, `code_execution`, `data_analysis`, `utility`.
Call `client.discover()` for the live list plus which providers serve each.

```python
# Image generation
result = client.execute(
    intent="image_generation",
    payload={"prompt": "A cyberpunk city at sunset", "size": "1024x1024"},
    budget={"max_total_usd": 0.08},
)

# Text-to-speech
result = client.execute(
    intent="text_to_speech",
    payload={"input": "Hello world", "voice": "alloy"},
    budget={"max_total_usd": 0.01},
)

# Code generation
result = client.execute(
    intent="code_generation",
    payload={"messages": [{"role": "user", "content": "Write a Python quicksort"}]},
    budget={"max_total_usd": 0.05},
)
```

There is no `embedding` intent — use `EmbeddingsClient` for `/v1/embeddings`.

## Analytics & Audit

```python
# Aggregated spend. Scope comes from your credentials: a non-admin caller only
# ever sees their own rows, so there is no scope parameter.
rows = client.spend(period="30d", group_by=["day", "model"])
for r in rows:
    print(f"{r['day']} {r['model']}: ${r['total_cost_usd']:.4f} ({r['total_reqs']} reqs)")

# Per-model and per-day shortcuts
by_model = client.model_breakdown(period="7d")
trend = client.daily_trend(period="30d")

# Filter to AIP traffic only
aip_only = client.spend(period="7d", filters={"api_source": "aip"})

# Budget utilisation, computed from actual spend
status = client.budget_status(daily_budget=5.0, monthly_budget=100.0)
print(f"Today: ${status['daily_spent']:.2f} / $5.00 ({status['daily_pct']:.0f}%)")
for alert in status["alerts"]:
    print("!", alert)

# Request-level audit trail (events, not costs)
history = client.audit_log()
for entry in history["entries"]:
    print(entry["event_type"], entry["request_id"])
```

The standalone `/v1/aip/analytics/*` endpoints were removed from the gateway and
folded into `/api/analytics/aggregate`; `spend()` reads that, and AIP usage shows
up tagged `api_source="aip"`. The gateway has no budget endpoint, so
`budget_status` derives its figures locally from `spend()` — the limits you pass
are the ones compared against, not values stored server-side.

## Federation — Peer Discovery

```python
# Public registry — no auth needed
peers = client.discover_peers()
for peer in peers["data"]:
    print(f"{peer['name']} — {peer['base_url']} (healthy={peer['healthy']})")

# Search callable resources across the federation
found = client.search_federation("crypto price", limit=10)
for r in found["data"]:
    print(f"{r['server_name']} {r['method']} {r['path']} — ${r['sell_price']}")

# Invoke one; the gateway settles with the peer on your behalf
result = client.federation_execute({"resource_id": 42, "payload": {...}})
```

Peer *management* is admin-only:

```python
from jarvisclaw import FederationClient

fed = FederationClient(api_key="sk-...")
fed.add_peer("peer.example.com")     # POST, domain in the body
fed.remove_peer("peer.example.com")  # DELETE, domain in the body — not an id
fed.crawl()                          # crawls every registered peer; takes no seeds
```

Those four sit behind `AdminAuth`, which needs a dashboard session or an access
token plus a `New-Api-User` header — an API key or wallet gets 401. The public
registry methods above work with any credentials.

## Other Endpoints

```python
from jarvisclaw import EmbeddingsClient, SearchClient, UserAPIClient

emb = EmbeddingsClient(api_key="sk-...")
vector = emb.embed("text-embedding-3-small", "hello world")
vectors = emb.embed_batch("text-embedding-3-small", ["a", "b"])
ranked = emb.rerank_texts("rerank-v1", "cats", ["dogs bark", "cats purr"])
flags = emb.moderate("some text")

search = SearchClient(api_key="sk-...")
results = search.query("latest AI news")          # /v1/search via a search model
neural = search.exa_search("latest AI news")      # Exa, structured results
answer = search.answer("what is a transformer")   # Exa, grounded answer

uapi = UserAPIClient(api_key="sk-...")
listing = uapi.list(category="data")
out = uapi.call("weather", "forecast", method="POST", json={"city": "Tokyo"})
```

## Wallet

```python
from jarvisclaw import WalletClient

wallet = WalletClient(api_key="sk-...")

# On-chain USDC across Base and Solana. Account quota is deliberately excluded:
# x402 settles against the wallet and never debits quota.
bal = wallet.balance()
print(bal["balance_usd"], bal["wallets"]["base"]["usdc"])
print(wallet.total_usd())

# Limits: the PUT replaces the whole record, so change one field via set_limit
# rather than update_limits, or the others are stored as zero.
wallet.set_limit(daily_max_usd=30)

print(wallet.pools())
print(wallet.history(page=1, page_size=20))
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

# Check balance — reads the wallet's on-chain USDC directly, on Base for an EVM
# key and on Solana mainnet for a base58 key.
balance = client.get_balance()
print(f"Wallet balance: ${balance:.2f} USDC")
```

Solana support needs the extra: `pip install jarvisclaw[solana]`. EVM x402 needs
`pip install jarvisclaw[agent]`. `pip install jarvisclaw[all]` covers both plus
the async client.

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

## What's new in 3.1.0

Mostly additive. The one behaviour change is `network_stats()` — see below.

**Fixed:** `Agent.stream()` crashed with `IndexError` after yielding all its
content. The gateway's final SSE frame reports token usage with an empty
`choices` array, which the code indexed unconditionally. It also required a space
after `data:`, which the SSE spec makes optional.

**Fixed:** `Agent.ask(budget=...)` never enforced the budget. Cost was recorded
after the response arrived, so `BudgetExceededError` could not fire. A budget
that cannot cover any call is now refused before the request goes out, and an
overspend raises rather than returning quietly.

**Fixed:** transport failures escaped as raw `requests`/`httpx` exceptions, so
you could not catch every SDK failure through `JarvisClawError`. Timeouts and
connection errors are now `TimeoutError` and `ConnectionError` (both SDK types,
exported), each carrying `.cause` and `.is_timeout`.

**Fixed:** `ChatClient.complete()` had no `**kwargs`, so `max_tokens` and friends
were unreachable — you had to drop to `completion()`. Same for the async client.

**Changed:** `network_stats()` now unwraps the `{"success", "data"}` envelope and
returns the stats directly, matching the Go SDK. If you were reading
`result["data"]["total_providers"]`, drop the `["data"]`.

**Added:** `list_models()` on every client. The `Model` type existed but nothing
populated it.

**Added:** eleven runnable [examples/](examples/), and a README section on the two
billing paths.

## Migration to v3

v3 removes methods that called gateway routes which no longer exist, and corrects
response shapes that had drifted. All client classes keep their names, so imports
do not change — but the methods and shapes below do.

```bash
pip install --upgrade jarvisclaw
```

**Analytics.** `/v1/aip/analytics/*` was consolidated into
`/api/analytics/aggregate`, so these were 404ing:

| Removed | Use instead |
|---|---|
| `IntentClient.cost_summary()` | `spend()` |
| `IntentClient.cost_trend()` | `daily_trend()` |
| `IntentClient.roi()` | `spend()` and compute from `total_quota` / `total_cost_usd` |
| `IntentClient.budget_status()` | `JarvisClaw.budget_status()` (derived locally) |
| `IntentClient.model_breakdown()` | `cost_by_model()` |

There is no `scope` parameter any more — scope comes from your credentials.

**Wallet balance.** `/v1/wallet/balance` dropped the quota fields. `quota`,
`quota_usd`, `hd_wallet` and `subscription` are gone; read `balance_usd` and
`wallets.{base,solana}.{usdc,address}`.

**Wallet limits.** `update_limits()` replaces the whole record, so it zeroes
anything you omit. Use `set_limit(daily_max_usd=30)` for single-field changes.
`Agent.set_limits()` now does that read-modify-write internally.

**Prompt coach.** `/v1/prompt-coach/score` never existed. `score()` now returns
an `int` on a 1-100 scale, derived from `optimize()`. `optimize()` returns the
unwrapped data object with `score_before` / `score_after` as ints.

**Discover.** The body keys are `intent`, `features` and `max_price` — the old
`intent_type`, `protocol` and `min_uptime` were never read by the server.

**Federation.** `crawl()` takes no arguments; the server crawls every registered
peer. `remove_peer(domain)` sends the domain in the body. `list_peers()` returns
the list directly, with camelCase keys.

**Streaming.** `stream()` and `subscribe()` accept `constraints`, `preferences`
and `optimize_for`, not `budget` — the endpoint never read a budget. Both yield
`{"event", "data"}` dicts.

**Solana balances.** `get_balance()` with a Solana key used to raise; it now
queries Solana mainnet.

### Per-capability clients still work

The unified `JarvisClaw` client is the recommended entry point, but the older
per-capability classes are unchanged and stay supported:

```python
from jarvisclaw import IntentClient
client = IntentClient(private_key="0x...")
client.execute("chat_completion", payload={...})
```

## Links

- [AIP Protocol Spec](https://docs.jarvisclaw.ai/aip)
- [SDK Reference](https://docs.jarvisclaw.ai/sdk)
- [Telegram](https://t.me/JarvisClawai)

## License

MIT
