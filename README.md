# JarvisClaw SDK

Python SDK for JarvisClaw AI & Prediction Market APIs with x402 machine payments.

## Install

```bash
pip install jarvisclaw
```

## Quick Start

### AI Agent (x402 direct payment — no API key needed)

```python
from jarvisclaw import JarvisClawClient

# Your agent's wallet (needs USDC on Base chain)
client = JarvisClawClient(private_key="0x<your-wallet-private-key>")

# AI model call — SDK handles 402 → sign → retry automatically
response = client.post("/v1/chat/completions", json={
    "model": "openai/gpt-5.4-nano",
    "messages": [{"role": "user", "content": "Hello!"}]
})
print(response["choices"][0]["message"]["content"])

# Prediction market data
markets = client.get("/v1/prediction/polymarket/markets", params={"limit": 10})
print(markets)

# Sports betting odds
sports = client.get("/v1/prediction/sports/markets", params={"category": "soccer"})
```

### API Key (traditional — for human users)

If you have an API key, you don't need this SDK. Just use the standard OpenAI SDK:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.jarvisclaw.ai/v1",
    api_key="sk-your-api-key"
)
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## Requirements

- Python >= 3.9
- Wallet with USDC on Base chain (Chain ID 8453)
- No ETH needed (facilitator pays gas)

## Pricing

- AI models: per-token (see https://api.jarvisclaw.ai/pricing)
- Prediction GET: $0.001/request
- Prediction POST: $0.005/request
- Zero markup on upstream costs
