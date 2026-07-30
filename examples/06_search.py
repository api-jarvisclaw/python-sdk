"""Web search and content retrieval.

Run: python examples/06_search.py

Heads up on billing: search routes through the gateway's `auto/search` model,
which settles on-chain over x402 rather than debiting account quota. On an
unfunded wallet every call here fails with "payment settlement failed" after a
lengthy retry — fund the wallet (see 03_wallet.py) before running this.
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from jarvisclaw import SearchClient
from jarvisclaw.errors import APIError

# The default timeout is generous because search can legitimately take a while.
# A failing settlement also burns most of it retrying, so this example shortens
# it to fail fast rather than hang for two minutes.
search = SearchClient(api_key=os.environ["JARVISCLAW_API_KEY"], timeout=45)

# --- Plain search -----------------------------------------------------------
# Returns a list of SearchResult objects with .title, .url and .snippet.
try:
    results = search.query("x402 payment protocol specification", num_results=5)
except APIError as e:
    print(f"Search unavailable ({e}). Is the wallet funded?")
    raise SystemExit(1)

print("Results:")
for r in results:
    print(f"  {r.title}")
    print(f"    {r.url}")

# --- Answer mode ------------------------------------------------------------
# Returns {answer, citations, raw} — a synthesized answer plus its sources —
# rather than a link list. Routed through the marketplace Exa service.
result = search.answer("What problem does the x402 protocol solve?", num_results=3)
print("\nAnswer:", result["answer"][:300])
print("Citations:")
for c in result["citations"][:3]:
    print(f"  {c.title} — {c.url}")

# --- Similar pages ----------------------------------------------------------
similar = search.find_similar("https://www.x402.org/", num_results=3)
print("\nSimilar to x402.org:")
for r in similar:
    print(f"  {r.title} — {r.url}")

# --- Page contents ----------------------------------------------------------
# Fetch and clean the text of specific URLs.
pages = search.contents(["https://www.x402.org/"])
for p in pages:
    text = (p.get("text") or "")[:200].replace("\n", " ")
    print(f"\nContents of {p.get('url')}:\n  {text}...")
