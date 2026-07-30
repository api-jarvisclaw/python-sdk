"""Chat completions — smart routing, explicit models, and streaming.

Run: python examples/01_chat.py

Every call here caps max_tokens to keep the cost to a fraction of a cent.
Without a cap the gateway reserves against your balance for the model's full
context window, which fails on a nearly-empty account even though the actual
response would have been cheap.
"""
import os

from jarvisclaw import ChatClient

chat = ChatClient(api_key=os.environ["JARVISCLAW_API_KEY"])

# --- Simplest form: one string in, one string out ---------------------------
answer = chat.complete(
    "Explain the x402 payment protocol in one sentence.",
    model="openai/gpt-4o-mini",
    max_tokens=60,
)
print("Direct:", answer)

# Omitting `model` entirely selects smart routing ("auto"), where the gateway
# picks a provider for you. Note that auto settles on-chain over x402 rather
# than debiting account quota, so it needs a funded wallet — on an empty wallet
# it fails after a lengthy settlement retry. Uncomment once yours is funded:
#
# answer = chat.complete("Explain x402 in one sentence.", max_tokens=60)

# --- A specific model, with a system prompt --------------------------------
answer = chat.complete(
    "Write a haiku about settlement latency.",
    model="openai/gpt-4o-mini",
    system="You are a terse poet who likes financial plumbing.",
    temperature=0.9,
    max_tokens=60,
)
print("\nHaiku:\n" + answer)

# --- Full message list, when you need the response metadata ----------------
# completion() returns a ChatResponse rather than a bare string, so you can read
# token usage and which model actually served the request.
resp = chat.completion(
    [
        {"role": "system", "content": "Answer in exactly one word."},
        {"role": "user", "content": "Name the default settlement chain here."},
    ],
    model="openai/gpt-4o-mini",
    max_tokens=5,
)
print("\nContent:", resp.content)
print("Model:   ", resp.model)
print("Usage:   ", resp.usage)

# --- Streaming --------------------------------------------------------------
print("\nStreaming: ", end="", flush=True)
for chunk in chat.stream(
    "Count from one to five, words only.",
    model="openai/gpt-4o-mini",
    max_tokens=30,
):
    print(chunk, end="", flush=True)
print()
