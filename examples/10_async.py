"""Async clients — concurrent requests with asyncio.

Requires the async extra:  pip install 'jarvisclaw[async]'

Run: python examples/10_async.py
"""
import asyncio
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# jarvisclaw.aio exports the async clients under the same short names as the
# sync package, so the only difference is the import path and the awaits.
from jarvisclaw.aio import ChatClient, WalletClient

KEY = os.environ["JARVISCLAW_API_KEY"]


async def main() -> None:
    # --- Concurrency is the point -------------------------------------------
    # Three prompts issued together take about as long as the slowest one,
    # rather than the sum of all three.
    questions = [
        "What is a stablecoin, in one sentence?",
        "What is an HD wallet, in one sentence?",
        "What is a facilitator, in one sentence?",
    ]

    async with ChatClient(api_key=KEY) as chat:
        started = time.perf_counter()
        answers = await asyncio.gather(*(
            chat.complete(q, model="openai/gpt-4o-mini", max_tokens=50)
            for q in questions
        ))
        elapsed = time.perf_counter() - started

        for q, a in zip(questions, answers):
            print(f"Q: {q}\nA: {a}\n")
        print(f"Three calls concurrently in {elapsed:.1f}s")

        # --- Streaming ------------------------------------------------------
        print("\nStreaming: ", end="", flush=True)
        async for chunk in chat.stream(
            "Count to five, words only.",
            model="openai/gpt-4o-mini",
            max_tokens=30,
        ):
            print(chunk, end="", flush=True)
        print()

    # --- Other clients follow the same pattern ------------------------------
    # The context manager closes the underlying connection pool on exit; without
    # it you would need an explicit aclose().
    async with WalletClient(api_key=KEY) as wallet:
        bal = await wallet.balance()
        print("\nWallet:", bal["balance_usd"], "USDC")


if __name__ == "__main__":
    asyncio.run(main())
