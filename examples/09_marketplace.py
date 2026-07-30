"""Marketplace services — blockchain RPC and DeFi data.

The marketplace proxies third-party services through the gateway, so one API key
reaches all of them and each call is metered the same way.

Run: python examples/09_marketplace.py

Billing note: marketplace services settle on-chain over x402 rather than
debiting account quota, so they need a funded HD wallet even when you
authenticate with an API key. On an empty wallet every call answers 403 with
"insufficient HD wallet balance". Check your balance with 03_wallet.py first.
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from jarvisclaw import MarketplaceClient
from jarvisclaw.errors import APIError

mp = MarketplaceClient(api_key=os.environ["JARVISCLAW_API_KEY"], timeout=45)


def show(label, fn):
    """Run one marketplace call, reporting an unfunded wallet as such."""
    try:
        return fn()
    except APIError as e:
        if e.status_code in (402, 403):
            print(f"{label}: needs a funded wallet ({e.status_code})")
        else:
            print(f"{label}: failed [{e.status_code}] {e.message[:80]}")
        return None


# --- DeFi: protocol list ----------------------------------------------------
protocols = show("defi/protocols", mp.defi_protocols)
if protocols is not None:
    items = protocols if isinstance(protocols, list) else protocols.get("data", [])
    print(f"{len(items)} protocols tracked. First few:")
    for p in items[:5]:
        print(f"  {p.get('name', '?'):<22} ${p.get('tvl') or 0:>16,.0f}")

# --- DeFi: one protocol, and total value locked -----------------------------
aave = show("defi/aave", lambda: mp.defi_protocol("aave"))
if aave is not None:
    print(f"aave: {str(aave)[:160]}...")

tvl = show("defi/tvl", mp.defi_tvl)
if tvl is not None:
    print("Total TVL:", tvl)

# --- Blockchain RPC ---------------------------------------------------------
# rpc_call forwards a single JSON-RPC method to the chain of your choice.
block = show("rpc eth_blockNumber", lambda: mp.rpc_call("base", "eth_blockNumber", []))
if block is not None:
    print("Base block number:", block)

# rpc_batch takes (method, params) tuples and sends them in one request.
batch = show("rpc batch", lambda: mp.rpc_batch("base", [
    ("eth_blockNumber", []),
    ("eth_gasPrice", []),
]))
if batch is not None:
    print("Batched:", batch)

# --- Arbitrary services -----------------------------------------------------
# call() reaches any marketplace service by name and path, so you are not
# limited to the convenience wrappers above.
price = show("surf/exchange/price",
             lambda: mp.call("surf", "exchange/price", params={"symbol": "BTC"}))
if price is not None:
    print("BTC price:", price)
