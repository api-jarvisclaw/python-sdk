"""OpenAI-compatible client — swap the import, keep your code.

If you already have code written against the `openai` package, changing the
import and the client construction is usually the whole migration.

    - from openai import OpenAI
    + from jarvisclaw import OpenAI

Run: python examples/08_openai_compat.py
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from jarvisclaw import OpenAI

client = OpenAI(api_key=os.environ["JARVISCLAW_API_KEY"])

# --- Standard completion ----------------------------------------------------
# Same call shape as the official SDK: dotted attribute access on the response,
# not dict indexing.
completion = client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "What is a payment facilitator?"},
    ],
    max_tokens=60,
)
print("Content:", completion.choices[0].message.content)
print("Model:  ", completion.model)
print("Tokens: ", completion.usage.total_tokens)
print("Finish: ", completion.choices[0].finish_reason)

# --- Streaming --------------------------------------------------------------
# Yields ChatCompletionChunk objects, again matching the official shape.
print("\nStreaming: ", end="", flush=True)
stream = client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[{"role": "user", "content": "List three chains that support USDC."}],
    max_tokens=60,
    stream=True,
)
for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()

# --- Tool calling -----------------------------------------------------------
tools = [{
    "type": "function",
    "function": {
        "name": "get_balance",
        "description": "Get the USDC balance for a chain",
        "parameters": {
            "type": "object",
            "properties": {"chain": {"type": "string", "enum": ["base", "solana"]}},
            "required": ["chain"],
        },
    },
}]

resp = client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[{"role": "user", "content": "What's my balance on Base?"}],
    tools=tools,
    max_tokens=60,
)
choice = resp.choices[0]
if choice.message.tool_calls:
    tc = choice.message.tool_calls[0]
    print(f"\nModel wants: {tc.function.name}({tc.function.arguments})")
else:
    print("\nNo tool call:", choice.message.content)
