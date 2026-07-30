# Examples

Runnable examples for the JarvisClaw Python SDK. Every one of these was executed
against the live gateway, so the field names and signatures reflect what the
server actually returns rather than what the docs assume.

## Setup

```bash
pip install jarvisclaw
export JARVISCLAW_API_KEY=sk-...
```

Every example reads `JARVISCLAW_API_KEY` from the environment. Nothing here
hardcodes a credential, and you should not add one.

## Running

```bash
python examples/01_chat.py
```

| Example | What it shows | Needs a funded wallet |
|---|---|---|
| [01_chat.py](01_chat.py) | Completions, system prompts, metadata, streaming | no |
| [02_agent.py](02_agent.py) | Autonomous tool loop, budget guards, session cost | no |
| [03_wallet.py](03_wallet.py) | On-chain balance, history, limits, treasury pools | no |
| [04_intent.py](04_intent.py) | Intent types, discovery, ranking, natural language | no |
| [05_embeddings.py](05_embeddings.py) | Single and batch embeddings, cosine similarity | no |
| [06_search.py](06_search.py) | Web search, answer mode, similar pages, contents | **yes** |
| [07_images.py](07_images.py) | Generation, async job polling | no (costs quota) |
| [08_openai_compat.py](08_openai_compat.py) | Drop-in `openai` package replacement | no |
| [09_marketplace.py](09_marketplace.py) | DeFi data, JSON-RPC, arbitrary services | **yes** |
| [10_async.py](10_async.py) | Concurrent requests with `jarvisclaw.aio` | no |
| [11_unified.py](11_unified.py) | Spend analytics, audit, federation discovery | no |

## Two billing paths, and why some examples need a funded wallet

The gateway settles a request one of two ways:

- **Account quota** — you name a model explicitly (`model="openai/gpt-4o-mini"`).
  Deducted from your account balance.
- **x402 on-chain USDC** — anything routed through `auto/*` (smart routing,
  `auto/search`) and every marketplace service. Settled against your HD wallet
  on Base or Solana.

The second path needs USDC in the wallet even when you authenticate with an API
key. Without it you get `payment settlement failed` after a slow retry, or a 403
`insufficient HD wallet balance`. Run [03_wallet.py](03_wallet.py) to see your
balance and addresses.

The examples marked **yes** above only work on a funded wallet; they report the
shortfall clearly rather than dumping a stack trace. The rest name their models
explicitly and run on quota alone.

## Cost

Chat, embeddings, agent and async examples each cost a fraction of a cent.
[07_images.py](07_images.py) is the expensive one — it generates two images.
Wallet, intent and unified are read-only apart from clearly-marked commented
sections.

## x402 mode

Every client also accepts `private_key=` instead of `api_key=`, settling each
request on-chain rather than debiting quota:

```python
agent = Agent(private_key="0x...")                      # Base
agent = Agent(private_key="...", network="solana")      # Solana
```

Requires the `agent` extra (`pip install 'jarvisclaw[agent]'`), or `solana` for
Solana. The examples use API-key auth because x402 spends real funds on every
call.
