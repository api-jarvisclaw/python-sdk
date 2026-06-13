# JarvisClaw Python SDK

AI API SDK with per-capability clients, smart routing, and x402 machine payments.

## Install

```bash
pip install jarvisclaw            # Sync client
pip install jarvisclaw[agent]     # + x402 EVM (Base chain) support
pip install jarvisclaw[solana]    # + Solana USDC support
pip install jarvisclaw[async]     # + asyncio (httpx) support
pip install jarvisclaw[all]       # Everything
```

## Authentication

```python
from jarvisclaw import ChatClient

# Option 1: API Key
client = ChatClient(api_key="sk-your-key")

# Option 2: x402 wallet (EVM / Base chain)
client = ChatClient(private_key="0x<hex-private-key>")

# Option 3: x402 wallet (Solana) — auto-detected from bs58 format
client = ChatClient(private_key="<base58-solana-keypair>")

# Option 4: Environment variables (JARVISCLAW_API_KEY or JARVISCLAW_WALLET_KEY)
client = ChatClient()
```

---

## ChatClient

| Method | Returns | Blocking |
|--------|---------|----------|
| `complete(message)` | `str` | Yes |
| `completion(messages)` | `ChatResponse` | Yes |
| `stream(message)` | `Generator[str]` | Yields chunks |

```python
from jarvisclaw import ChatClient

chat = ChatClient(private_key="0x...")

# ─── complete() — simple one-liner ───
response = chat.complete("What is quantum computing?")
print(response)  # str

# With options
response = chat.complete("Explain gravity", model="openai/gpt-5.4", system="Be concise")

# ─── completion() — full control ───
resp = chat.completion([
    {"role": "system", "content": "You are a tutor."},
    {"role": "user", "content": "Explain gravity."}
], model="auto", temperature=0.5)
print(resp.content)       # str
print(resp.model)         # "openai/gpt-5.4-nano"
print(resp.usage)         # {"prompt_tokens": 12, "completion_tokens": 45, ...}

# ─── stream() — yields text chunks ───
for chunk in chat.stream("Tell me a joke"):
    print(chunk, end="", flush=True)

# With system prompt
for chunk in chat.stream("Explain AI", system="You are a professor"):
    print(chunk, end="")
```

### ChatClient async (asyncio)

```python
import asyncio
from jarvisclaw.aio import ChatClient

async def main():
    async with ChatClient(private_key="0x...") as chat:
        # Simple
        text = await chat.complete("Hello!")
        print(text)

        # Concurrent to multiple models
        results = await asyncio.gather(
            chat.complete("Hi", model="openai/gpt-5.4"),
            chat.complete("Hi", model="anthropic/claude-sonnet-4.6"),
            chat.complete("Hi", model="google/gemini-2.5-flash"),
        )
        for r in results:
            print(r)

        # Async streaming
        async for chunk in chat.stream("Tell me a story"):
            print(chunk, end="")

asyncio.run(main())
```

---

## ImageClient

| Method | Returns | Blocking |
|--------|---------|----------|
| `generate(prompt)` | `ImageResponse` | Yes (default) |
| `generate(prompt, wait=False)` | `ImageResponse` (with raw job data) | No |
| `status(job_id)` | `ImageResponse` | No (single check) |
| `wait(job_id)` | `ImageResponse` | Yes (polls until done) |
| `edit(image, prompt)` | `ImageResponse` | Yes |

```python
from jarvisclaw import ImageClient

image = ImageClient(private_key="0x...")

# ─── generate() — blocking (default) ───
result = image.generate("A cat in space", size="1024x1024")
print(result.url)            # "https://api.jarvisclaw.ai/media/images/..."
print(result.revised_prompt) # model's revised prompt (if any)

# With specific model
result = image.generate("Neon city", model="openai/gpt-image-1", size="1792x1024")

# ─── generate(wait=False) — non-blocking ───
job = image.generate("A futuristic city", wait=False)
print(job.raw["id"])     # "e061906e-04d7-4281-b487-54907344c7c0"
print(job.raw["status"]) # "queued"

# ─── status(job_id) — single check, non-blocking ───
result = image.status(job.raw["id"])
print(result.raw.get("status"))  # "in_progress" or "completed"
if result.url:
    print(result.url)  # only set when completed

# ─── wait(job_id) — block until done ───
result = image.wait(job.raw["id"])
print(result.url)  # guaranteed to have URL (or raises on failure)

# ─── edit() — always blocking ───
result = image.edit(open("photo.png", "rb"), "Remove the background")
print(result.url)
```

---

## VideoClient

| Method | Returns | Blocking |
|--------|---------|----------|
| `generate(prompt)` | `VideoJob` | Yes (default) |
| `generate(prompt, wait=False)` | `VideoJob` (queued) | No |
| `status(job_id)` | `VideoJob` | No (single check) |
| `wait(job_id)` | `VideoJob` | Yes (polls until done) |

```python
from jarvisclaw import VideoClient

video = VideoClient(private_key="0x...")

# ─── generate() — blocking (default, waits 1-3 minutes) ───
job = video.generate("A cat walking on a beach", duration=5)
print(job.url)     # MP4 URL
print(job.status)  # "completed"

# ─── generate(wait=False) — non-blocking ───
job = video.generate("Ocean waves at sunset", wait=False)
print(job.id)      # "bytedance:video_c6f42c34..."
print(job.status)  # "queued"

# ─── status(job_id) — single check, non-blocking ───
result = video.status(job.id)
print(result.status)  # "in_progress" or "completed"
if result.url:
    print(result.url)

# ─── wait(job_id) — block until done ───
result = video.wait(job.id)
print(result.url)    # guaranteed MP4 URL
print(result.status) # "completed"
```

### Full non-blocking workflow

```python
from jarvisclaw import VideoClient
import time

video = VideoClient(private_key="0x...")

# Submit job
job = video.generate("A timelapse of a flower blooming", wait=False)
print(f"Submitted: {job.id}")

# Do other work...
print("Doing other work while video generates...")
time.sleep(30)

# Now wait for the result
result = video.wait(job.id)
print(f"Done! URL: {result.url}")
```

---

## AudioClient

| Method | Returns | Blocking |
|--------|---------|----------|
| `music(prompt)` | `AudioResponse` | Yes (1-3 min) |
| `music(prompt, wait=False)` | `MusicJob` | No |
| `MusicJob.result()` | `AudioResponse` | Yes (blocks until ready) |
| `MusicJob.done` | `bool` | No |
| `speech(text)` | `AudioResponse` | Yes (fast) |
| `transcribe(file)` | `str` | Yes |

```python
from jarvisclaw import AudioClient

audio = AudioClient(private_key="0x...")

# ─── music() — blocking (takes 1-3 minutes) ───
result = audio.music("An upbeat electronic track")
with open("music.mp3", "wb") as f:
    f.write(result.content)
print(result.content_type)  # "audio/mpeg"

# ─── music(wait=False) — non-blocking ───
job = audio.music("Lo-fi hip hop beat", wait=False)
print(job.done)  # False

# Do other work...
print("Working on other things...")

# Get result when needed (blocks from this point)
result = job.result()
with open("lofi.mp3", "wb") as f:
    f.write(result.content)

# Check without blocking
if job.done:
    result = job.result()  # instant, already done

# ─── speech() — always blocking (fast, <5s) ───
result = audio.speech("Hello world", voice="alloy")
with open("speech.mp3", "wb") as f:
    f.write(result.content)

# Available voices: alloy, echo, fable, onyx, nova, shimmer, sarah, george
result = audio.speech("Good morning", model="tts-1", voice="nova")

# ─── transcribe() — speech-to-text ───
with open("recording.mp3", "rb") as f:
    text = audio.transcribe(f)
print(text)  # "Hello, this is a test recording."

# With language hint
with open("chinese_audio.mp3", "rb") as f:
    text = audio.transcribe(f, language="zh")
```

---

## SearchClient

| Method | Returns | Blocking |
|--------|---------|----------|
| `query(q)` | `list[SearchResult]` | Yes |
| `find_similar(url)` | `list[SearchResult]` | Yes |
| `contents(urls)` | `list[dict]` | Yes |

```python
from jarvisclaw import SearchClient

search = SearchClient(private_key="0x...")

# ─── query() — web search ───
results = search.query("latest AI news", num_results=5)
for r in results:
    print(f"{r.title}")
    print(f"  {r.url}")
    print(f"  {r.snippet}")

# ─── find_similar() — find pages similar to a URL ───
similar = search.find_similar("https://example.com/article")
for r in similar:
    print(r.title, r.url)

# ─── contents() — extract page content ───
pages = search.contents(["https://example.com/page1", "https://example.com/page2"])
for page in pages:
    print(page)  # full page content dict
```

---

## MarketplaceClient

| Method | Returns | Blocking |
|--------|---------|----------|
| `call(service, path)` | `dict` | Yes |
| `call(service, path, method="POST")` | `dict` | Yes |
| `rpc_call(chain, method, params)` | `dict` | Yes |
| `rpc_batch(chain, calls)` | `list` | Yes |
| `defi_protocols()` | `dict` | Yes |
| `defi_protocol(slug)` | `dict` | Yes |
| `defi_yields()` | `dict` | Yes |

```python
from jarvisclaw import MarketplaceClient

mp = MarketplaceClient(private_key="0x...")

# ─── Generic service call ───
prices = mp.call("surf", "/exchange/price?pair=BTC-USDT")
print(prices)

# ─── POST request ───
results = mp.call("exa", "/search", method="POST", json={
    "query": "latest AI news",
    "numResults": 5,
})

# ─── Blockchain RPC ───
block = mp.rpc_call("ethereum", "eth_blockNumber")
print(int(block["result"], 16))  # current block number

gas = mp.rpc_call("base", "eth_gasPrice")
print(f"Gas: {int(gas['result'], 16)} wei")

# Batch RPC (multiple calls in one request)
results = mp.rpc_batch("ethereum", [
    ("eth_blockNumber", []),
    ("eth_gasPrice", []),
])

# ─── DeFi Data (DefiLlama) ───
protocols = mp.defi_protocols()
aave = mp.defi_protocol("aave")
yields = mp.defi_yields()
```

---

## Error Handling

```python
from jarvisclaw import (
    ChatClient, APIError, AuthenticationError,
    RateLimitError, InsufficientBalanceError, PaymentError,
)

chat = ChatClient()

try:
    response = chat.complete("Hello")
except AuthenticationError:
    print("Invalid API key or wallet key")
except RateLimitError as e:
    print(f"Rate limited — retry after {e.retry_after}s")
except InsufficientBalanceError:
    print("Balance too low — top up USDC")
except PaymentError as e:
    print(f"x402 payment signing failed: {e}")
except APIError as e:
    print(f"API error {e.status_code}: {e.message}")
    print(f"Response body: {e.body}")
```

---

## Balance & Wallet

```python
from jarvisclaw import ChatClient

client = ChatClient(private_key="0x...")

# On-chain USDC balance (Base chain or Solana depending on key type)
print(f"Balance: ${client.get_balance():.2f}")

# Session spending (tracked locally in ~/.jarvisclaw/cost_log.jsonl)
print(f"Spent: ${client.get_spending():.4f}")

# Wallet address
print(f"Wallet: {client.address}")
```

---

## Async Clients (all capabilities)

```python
import asyncio
from jarvisclaw.aio import (
    ChatClient, ImageClient, VideoClient,
    AudioClient, SearchClient, MarketplaceClient,
)

async def main():
    async with ChatClient(private_key="0x...") as chat:
        text = await chat.complete("Hello!")
        print(text)

        # Streaming
        async for chunk in chat.stream("Tell me a story"):
            print(chunk, end="")

    async with ImageClient(private_key="0x...") as image:
        result = await image.generate("A cat on Mars")
        print(result.url)

    async with AudioClient(api_key="sk-...") as audio:
        result = await audio.speech("Hello world", voice="nova")
        # result.content is bytes

        # Transcribe
        with open("recording.mp3", "rb") as f:
            text = await audio.transcribe(f)

    async with MarketplaceClient(api_key="sk-...") as mp:
        data = await mp.call("surf", "/exchange/price?pair=ETH-USDT")
        print(data)

asyncio.run(main())
```

---

## Concurrent Batch Processing (ThreadPool)

```python
from concurrent.futures import ThreadPoolExecutor
from jarvisclaw import ImageClient

image = ImageClient(private_key="0x...")
prompts = ["A cat", "A dog", "A bird", "A fish", "A horse"]

with ThreadPoolExecutor(max_workers=5) as pool:
    futures = [pool.submit(image.generate, p) for p in prompts]
    for f in futures:
        print(f.result().url)
```

---

## Solana Payments

```python
from jarvisclaw import ChatClient, ImageClient

# Auto-detected from bs58 key format
chat = ChatClient(private_key="<base58-solana-keypair>")
print(chat.complete("Hello from Solana!"))

# Explicit network
chat = ChatClient(private_key="<key>", network="solana")

# All clients work identically — only payment chain differs
image = ImageClient(private_key="<base58-solana-keypair>")
result = image.generate("Cyberpunk city")
print(result.url)
```

---

## Configuration

| Env Variable | Description |
|---|---|
| `JARVISCLAW_API_KEY` | API key (auto-used if no args passed) |
| `JARVISCLAW_WALLET_KEY` | x402 private key (EVM hex or Solana bs58) |
| `JARVISCLAW_BASE_URL` | Override API endpoint (default: `https://api.jarvisclaw.ai`) |

---

## Requirements

- Python >= 3.9
- USDC on Base chain (EVM) or Solana (SPL)
- No ETH/SOL needed for gas (facilitator pays)

## Links

- API Reference: https://api.jarvisclaw.ai/docs
- Pricing: https://api.jarvisclaw.ai/pricing
- PyPI: https://pypi.org/project/jarvisclaw/
