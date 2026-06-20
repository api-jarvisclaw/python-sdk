"""WalletClient — wallet balance, history, limits, and pools."""
from __future__ import annotations

from typing import Any

from ._base import BaseClient


class WalletClient(BaseClient):
    """Wallet management client.

    Usage:
        from jarvisclaw import WalletClient

        wallet = WalletClient(api_key="sk-...")
        print(wallet.balance())
    """

    def balance(self) -> dict[str, Any]:
        """Get wallet balance.

        Returns dict with: quota, quota_usd, hd_wallet, subscription, total_usd
        """
        return self._get("/v1/wallet/balance")

    def history(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        """Get transaction history.

        Returns dict with: transactions, total, page
        """
        return self._get(f"/v1/wallet/history?page={page}&page_size={page_size}")

    def limits(self) -> dict[str, Any]:
        """Get spending limits.

        Returns dict with: user_id, daily_max_usd, per_request_max_usd,
        monthly_max_usd, auto_pause_below_usd, pool_allocation, updated_at
        """
        return self._get("/v1/wallet/limits")

    def update_limits(self, data: dict[str, Any]) -> dict[str, Any]:
        """Update spending limits.

        Args:
            data: dict with keys: daily_max_usd, per_request_max_usd,
                  monthly_max_usd, auto_pause_below_usd, pool_allocation (optional)

        Returns dict with: success
        """
        return self._put("/v1/wallet/limits", json=data)

    def pools(self) -> dict[str, Any]:
        """Get pool allocation and balances.

        Returns dict with: allocation, pool_balances
        """
        return self._get("/v1/wallet/pools")
