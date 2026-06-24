"""Tests for WalletClient."""
import json
from unittest.mock import patch, MagicMock

import pytest

from jarvisclaw.wallet import WalletClient


@pytest.fixture
def wallet():
    return WalletClient(api_key="sk-test")


def _mock_response(data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.headers = {"content-type": "application/json"}
    return resp


class TestWalletBalance:
    def test_returns_balance(self, wallet):
        expected = {
            "quota": 25000000,
            "quota_usd": "50.0000",
            "hd_wallet": {"base_usdc": "available", "solana_usdc": "available"},
            "subscription": {"active": False, "remaining_quota": 0},
            "total_usd": "50.0000",
        }
        with patch.object(wallet._session, "request", return_value=_mock_response(expected)):
            result = wallet.balance()
        assert result["quota"] == 25000000
        assert result["quota_usd"] == "50.0000"
        assert result["hd_wallet"]["base_usdc"] == "available"


class TestWalletHistory:
    def test_returns_paginated_history(self, wallet):
        expected = {
            "transactions": [
                {"id": 1, "amount_quota": 5000, "category": "inference", "model": "gpt-4o", "created_at": 1718841600}
            ],
            "total": 1,
            "page": 1,
        }
        with patch.object(wallet._session, "request", return_value=_mock_response(expected)):
            result = wallet.history(page=1, page_size=20)
        assert result["total"] == 1
        assert result["transactions"][0]["category"] == "inference"


class TestWalletLimits:
    def test_get_limits(self, wallet):
        expected = {
            "user_id": 42,
            "daily_max_usd": 50,
            "per_request_max_usd": 1,
            "monthly_max_usd": 500,
            "auto_pause_below_usd": 2,
            "pool_allocation": None,
            "updated_at": 1718841600,
        }
        with patch.object(wallet._session, "request", return_value=_mock_response(expected)):
            result = wallet.limits()
        assert result["daily_max_usd"] == 50

    def test_update_limits(self, wallet):
        with patch.object(wallet._session, "request", return_value=_mock_response({"success": True})):
            result = wallet.update_limits({"daily_max_usd": 100, "per_request_max_usd": 5})
        assert result["success"] is True


class TestWalletPools:
    def test_returns_pools(self, wallet):
        expected = {
            "allocation": {"operations": 0.60, "insurance": 0.15},
            "pool_balances": {"operations": "30.0000", "insurance": "7.5000"},
        }
        with patch.object(wallet._session, "request", return_value=_mock_response(expected)):
            result = wallet.pools()
        assert result["allocation"]["operations"] == 0.60
        assert result["pool_balances"]["operations"] == "30.0000"
