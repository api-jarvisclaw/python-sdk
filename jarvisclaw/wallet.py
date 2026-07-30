"""WalletClient — wallet balance, history, limits, and pools."""
from __future__ import annotations

from typing import Any, Callable

from ._base import BaseClient


class WalletClient(BaseClient):
    """Wallet management client.

    Usage:
        from jarvisclaw import WalletClient

        wallet = WalletClient(api_key="sk-...")
        print(wallet.balance()["balance_usd"])
    """

    def balance(self) -> dict[str, Any]:
        """Get the HD wallet's on-chain USDC balance across Base and Solana.

        Returns dict with:
            - balance_usd (str): Base + Solana total, decimal string with 6 places
            - wallets (dict): {"base": {...}, "solana": {...}}, each with
              "usdc" (decimal string) and "address"

        This deliberately excludes the account's quota column: x402 settles
        against the wallet and never debits quota, so including it overstated the
        spendable balance by the lifetime deposit total.
        """
        return self._get("/v1/wallet/balance")

    def total_usd(self) -> float:
        """Get balance()["balance_usd"] as a float, or 0.0 if unparseable."""
        try:
            return float(self.balance().get("balance_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def history(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        """Get transaction history. page is 1-based; page_size is capped at 100.

        Returns dict with: transactions, total, page.

        Each transaction has id, amount_quota (negated spend, so normally
        negative), category ("inference" | "topup" | "refund" | "marketplace" |
        "other"), model, use_time_seconds, created_at.
        """
        return self._get(
            "/v1/wallet/history", params={"page": page, "page_size": page_size}
        )

    def limits(self) -> dict[str, Any]:
        """Get spending limits.

        Returns dict with: user_id, daily_max_usd, per_request_max_usd,
        monthly_max_usd, auto_pause_below_usd, pool_allocation, updated_at
        """
        return self._get("/v1/wallet/limits")

    def update_limits(self, data: dict[str, Any]) -> dict[str, Any]:
        """Replace the spending limits.

        WARNING: this is a full replacement, not a patch. The server persists it
        with a full-row write, so any field you omit is stored as 0 — including
        pool_allocation, which makes pools() fall back to its defaults. Use
        set_limit() to change one value safely.

        Args:
            data: daily_max_usd, per_request_max_usd, monthly_max_usd,
                auto_pause_below_usd, pool_allocation (JSON string whose values
                must sum to 1.0).

        Returns dict with: success
        """
        return self._put("/v1/wallet/limits", json=data)

    def set_limit(self, **changes: Any) -> dict[str, Any]:
        """Change specific limits, preserving the rest.

        Reads the current limits, applies the given changes, and writes the whole
        record back — the read-modify-write the replacing PUT requires.

        Example:
            wallet.set_limit(daily_max_usd=30)
        """
        current = dict(self.limits())
        # user_id and updated_at are server-assigned; sending them back is
        # harmless (the handler overwrites user_id from the auth context) but
        # dropping updated_at keeps the write honest.
        current.pop("updated_at", None)
        current.update(changes)
        return self.update_limits(current)

    def update_limits_with(self, mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        """set_limit() with a callback, for computed updates.

        Example:
            wallet.update_limits_with(lambda l: l.__setitem__(
                "daily_max_usd", l["daily_max_usd"] * 2))
        """
        current = dict(self.limits())
        current.pop("updated_at", None)
        mutate(current)
        return self.update_limits(current)

    def pools(self) -> dict[str, Any]:
        """Get pool allocation ratios and the resulting balances.

        Returns dict with:
            - allocation: {"operations", "insurance", "savings", "dividends"} as
              fractions summing to 1.0
            - pool_balances: the same keys, each a decimal string with 4 places

        Pools are slices of the same on-chain balance that balance() reports, not
        separate accounts.
        """
        return self._get("/v1/wallet/pools")
