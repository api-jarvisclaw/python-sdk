"""Wallet — on-chain balance, transaction history, and spending limits.

Read-only by default. The limit-changing section at the bottom is commented out.

Run: python examples/03_wallet.py
"""
import os

from jarvisclaw import WalletClient

wallet = WalletClient(api_key=os.environ["JARVISCLAW_API_KEY"])

# --- Balance ----------------------------------------------------------------
# This is the HD wallet's on-chain USDC across Base and Solana. It deliberately
# excludes account quota: x402 settles against the wallet and never debits
# quota, so folding quota in would overstate what is actually spendable.
bal = wallet.balance()
print("Total USDC:", bal["balance_usd"])
for chain in ("base", "solana"):
    w = bal["wallets"][chain]
    print(f"  {chain:7} {w['usdc']:>12}  {w['address']}")

# total_usd() is the same figure parsed to a float, for arithmetic.
print("As float:", wallet.total_usd())

# --- History ----------------------------------------------------------------
# page is 1-based; page_size caps at 100.
hist = wallet.history(page=1, page_size=5)
print(f"\n{hist['total']} transactions total. Most recent 5:")
for tx in hist["transactions"]:
    # amount_quota is negated spend, so it is normally negative.
    print(
        f"  #{tx['id']:<6} {tx['category']:<12} {tx['amount_quota']:>10}"
        f"  {tx.get('model') or '-'}"
    )

# --- Limits -----------------------------------------------------------------
limits = wallet.limits()
print("\nSpending limits:")
for k in ("daily_max_usd", "per_request_max_usd", "monthly_max_usd", "auto_pause_below_usd"):
    print(f"  {k:24} {limits.get(k)}")

# --- Treasury pools ---------------------------------------------------------
pools = wallet.pools()
print("\nPool allocation:", pools["allocation"])
print("Pool balances:  ", pools["pool_balances"])

# --- Changing limits (mutates state — uncomment to run) --------------------
#
# The endpoint replaces the whole record, so set_limit() reads the current
# limits first and merges your change in. Passing one field through the raw
# update_limits() would zero the others.
#
# wallet.set_limit(daily_max_usd=25.0)
#
# To change several at once, or to compute from current values:
#
# def halve_daily(limits):
#     limits["daily_max_usd"] = limits["daily_max_usd"] / 2
#
# wallet.update_limits_with(halve_daily)
