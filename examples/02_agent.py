"""Autonomous agent — tool calling, budget guards, and streaming.

Run: python examples/02_agent.py
"""
import os
import sys

# Model output can contain characters the Windows console codepage cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from jarvisclaw import Agent, BudgetExceededError

# default_budget caps spend for every call made through this agent unless a call
# overrides it. It is a ceiling, not a reservation.
agent = Agent(
    api_key=os.environ["JARVISCLAW_API_KEY"],
    default_model="openai/gpt-4o-mini",
    default_budget=0.10,
)

# --- One-shot question ------------------------------------------------------
answer = agent.ask("What does the 402 status code mean in HTTP?", max_tokens=60)
print("Answer:", answer)

# --- Registering tools ------------------------------------------------------
# The @agent.tool decorator exposes a Python function to the model. The
# docstring becomes the tool description, so write it for the model to read.


@agent.tool
def usdc_balance(chain: str) -> str:
    """Look up the agent's USDC balance on a chain. chain is 'base' or 'solana'."""
    bal = agent.balance()
    w = bal["wallets"].get(chain.lower())
    if not w:
        return f"unknown chain {chain!r}"
    return f"{w['usdc']} USDC at {w['address']}"


@agent.tool
def convert_to_cents(usd: float) -> str:
    """Convert a US dollar amount to whole cents."""
    return str(int(round(float(usd) * 100)))


# --- Autonomous run ---------------------------------------------------------
# run() loops: the model calls tools, reads results, and iterates until it can
# answer or hits the budget / iteration ceiling.
result = agent.run(
    "What is my USDC balance on base, expressed in cents?",
    budget=0.05,
    max_iterations=4,
)
print("\nRun result:", result.text)
print(f"Spent ${result.cost.spent_usd:.6f} over {result.iterations} iterations")
if result.tool_calls:
    print("Tools used:", [tc["tool"] for tc in result.tool_calls])

# --- Budget enforcement -----------------------------------------------------
# A budget too small to cover even one call raises rather than silently
# overspending.
try:
    agent.ask("Write a 2000-word essay on settlement finality.", budget=0.000001)
    print("\n(unexpectedly completed)")
except BudgetExceededError as e:
    print(f"\nBudget stopped it: spent ${e.spent:.6f} of ${e.budget:.6f}")

# --- Streaming --------------------------------------------------------------
print("\nStreaming: ", end="", flush=True)
for chunk in agent.stream("Name three things a payment protocol must guarantee."):
    print(chunk, end="", flush=True)
print()

# --- Session accounting -----------------------------------------------------
print("\nSession:", agent.cost_summary())
