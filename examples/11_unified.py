"""The unified client — one object for intents, analytics, and federation.

JarvisClaw() is the agent-facing surface: rather than composing per-capability
clients, it exposes intent execution, spend analytics and federation discovery
from a single handle.

Run: python examples/11_unified.py
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from jarvisclaw import JarvisClaw
from jarvisclaw.errors import APIError

jc = JarvisClaw(api_key=os.environ["JARVISCLAW_API_KEY"], timeout=45)

# --- Where the money went ---------------------------------------------------
# All of these read /api/analytics/aggregate with a different grouping. Scope is
# enforced server-side from your auth context, so you only ever see your own.
spend = jc.spend(period="7d")
print("Spend rows (7d):", len(spend))
for row in spend[:5]:
    print(f"  {row.get('model', '?'):<40} ${row.get('revenue_usd', 0)}")

by_model = jc.model_breakdown(period="7d")
print("\nBy model:", len(by_model), "rows")

trend = jc.daily_trend(period="7d")
print("Daily trend:", len(trend), "days")

# budget_status is derived locally from the spend figures rather than being its
# own endpoint — the gateway has no budget-status route. The limits you pass are
# the ones compared against; they are not read from the server, so pass your
# real ones (wallet.limits() has them) if you want a meaningful reading.
status = jc.budget_status(daily_budget=50.0, monthly_budget=500.0)
print(f"\nBudget: ${status['daily_spent']:.4f} today "
      f"({status['daily_pct']:.1f}% of ${status['daily_budget']})")
for alert in status["alerts"]:
    print("  !", alert)

# --- Audit trail ------------------------------------------------------------
audit = jc.audit_log()
print(f"\nAudit entries: {audit.get('count', 0)}")

# --- Discovery --------------------------------------------------------------
net = jc.network_stats()
print(f"\nNetwork: {net['total_providers']} providers, "
      f"{net['intent_types']} intent types")

peers = jc.discover_peers(page=1, page_size=5)
rows = peers.get("data") or []
print(f"\nFederation peers (showing {len(rows)}):")
for p in rows:
    health = "up" if p.get("healthy") else "down"
    print(f"  {p.get('name', '?'):<32} {health:<5} {p.get('resource_count', 0)} resources")

# --- Federated search -------------------------------------------------------
# Search across every peer's advertised resources at once.
try:
    hits = jc.search_federation("video generation", limit=5)
    found = hits.get("data") or []
    print(f"\nFederated search hits: {len(found)}")
    for h in found[:5]:
        print(f"  {str(h.get('name'))[:60]}")
except APIError as e:
    print(f"\nFederated search failed [{e.status_code}]: {e.message[:80]}")

# --- Executing work (spends — uncomment to run) -----------------------------
#
# result = jc.execute(
#     "chat_completion",
#     payload={"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 10},
# )
#
# With a hard spend ceiling and settlement detail returned:
#
# result = jc.execute_budget(
#     "chat_completion",
#     payload={"messages": [{"role": "user", "content": "Hi"}]},
#     budget={"max_total_usd": 0.01},
# )
