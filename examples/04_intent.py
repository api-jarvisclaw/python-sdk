"""AIP intent protocol — describe what you want, let the gateway pick a provider.

Read-only: resolves and discovers without executing a paid intent. The execute
section at the bottom is commented out.

Run: python examples/04_intent.py
"""
import os

from jarvisclaw import IntentClient

intent = IntentClient(api_key=os.environ["JARVISCLAW_API_KEY"])

# --- What can I ask for? ----------------------------------------------------
types = intent.types()  # already unwrapped to a plain list of strings
print(f"{len(types)} intent types available.")
print("Sample:", ", ".join(types[:8]))

# --- Discovery: browse intents and their providers --------------------------
# Public endpoint — works without auth too.
found = intent.discover(intent="chat_completion")
for i in found.get("intents", [])[:3]:
    print(f"\n{i['type']}: {i.get('description')}")
    print(f"  providers: {i.get('provider_count')}")

# --- Resolve: rank providers for a specific need ----------------------------
# Constraints are hard filters; preferences are soft ranking hints.
ranked = intent.resolve(
    "chat_completion",
    constraints={"max_price_usd": 0.01},
    preferences={"optimize_for": "cost"},
)
print(f"\nTop matches for chat_completion under $0.01 "
      f"({ranked['total_available']} available):")
for m in ranked["matches"][:5]:
    print(f"  {m['provider_id']:<44} ${m['estimated_price_usd']:<10} score={m['score']:.3f}")

# --- Natural language resolution -------------------------------------------
# Describe the goal in prose instead of naming an intent type. If the request is
# ambiguous the response carries a clarify payload rather than a match.
nat = intent.resolve_natural("I need to turn a paragraph into a short video")
if nat["status"] == "resolved":
    print(f"\nRead as {nat['intent']!r} (confidence {nat['confidence']:.2f}):")
    for m in nat["matches"][:3]:
        print(f"  {m['provider_name']:<44} score={m['score']:.3f}")
else:
    # Ambiguous phrasing comes back as status="clarify" with a question.
    print("\nNeeds clarification:", nat.get("clarify", {}).get("question"))

# --- Network size -----------------------------------------------------------
stats = intent.network_stats()
print(f"\n{stats['total_providers']} providers "
      f"({stats['by_source']['internal']} internal, "
      f"{stats['by_source']['federation']} federated) "
      f"across {stats['intent_types']} intent types")

# --- Executing an intent (spends quota — uncomment to run) -----------------
#
# execute() resolves and forwards in one call, returning the provider's raw
# response.
#
# result = intent.execute(
#     "chat_completion",
#     payload={"messages": [{"role": "user", "content": "Hello"}], "max_tokens": 10},
#     constraints={"max_price_usd": 0.005},
# )
# print(result)
#
# execute_budget() caps total spend and returns settlement detail alongside the
# result. max_total_usd is required.
#
# result = intent.execute_budget(
#     "chat_completion",
#     payload={"messages": [{"role": "user", "content": "Hello"}]},
#     budget={"max_total_usd": 0.01},
# )
# print(result["actual_cost_usd"], result["settlement"])
