"""Tests for WalletClient."""
from unittest.mock import MagicMock, patch

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
    def test_returns_onchain_balance(self, wallet):
        # controller/wallet/balance.go GetBalance. The old {quota, quota_usd,
        # hd_wallet, subscription, total_usd} shape was removed by the
        # "remove quota entirely" change — balance is HD wallet USDC only.
        expected = {
            "balance_usd": "5.960000",
            "wallets": {
                "base": {"usdc": "5.910000", "address": "0xabc0000000000000000000000000000000000001"},
                "solana": {"usdc": "0.050000", "address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"},
            },
        }
        with patch.object(wallet._session, "request", return_value=_mock_response(expected)):
            result = wallet.balance()
        assert result["balance_usd"] == "5.960000"
        assert result["wallets"]["base"]["usdc"] == "5.910000"
        assert result["wallets"]["solana"]["address"].startswith("7xK")

    def test_total_usd_parses_float(self, wallet):
        expected = {"balance_usd": "5.960000", "wallets": {}}
        with patch.object(wallet._session, "request", return_value=_mock_response(expected)):
            assert wallet.total_usd() == 5.96

    def test_total_usd_survives_missing_field(self, wallet):
        with patch.object(wallet._session, "request", return_value=_mock_response({})):
            assert wallet.total_usd() == 0.0


class TestWalletHistory:
    def test_returns_paginated_history(self, wallet):
        expected = {
            "transactions": [
                {"id": 1, "amount_quota": -5000, "category": "inference",
                 "model": "gpt-4o", "use_time_seconds": 3, "created_at": 1718841600}
            ],
            "total": 1,
            "page": 1,
        }
        with patch.object(wallet._session, "request", return_value=_mock_response(expected)) as m:
            result = wallet.history(page=1, page_size=20)
        assert result["total"] == 1
        assert result["transactions"][0]["category"] == "inference"
        # amount_quota is negated spend, so it is legitimately negative.
        assert result["transactions"][0]["amount_quota"] == -5000
        # Pagination goes through params, not a hand-built query string.
        assert m.call_args.kwargs["params"] == {"page": 1, "page_size": 20}


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

    def test_update_limits_sends_body_verbatim(self, wallet):
        with patch.object(wallet._session, "request", return_value=_mock_response({"success": True})) as m:
            result = wallet.update_limits({"daily_max_usd": 100, "per_request_max_usd": 5})
        assert result["success"] is True
        assert m.call_args.kwargs["json"] == {"daily_max_usd": 100, "per_request_max_usd": 5}

    def test_set_limit_preserves_untouched_fields(self, wallet):
        # PUT replaces the whole record (model.UpsertUserWalletLimits uses
        # DB.Save), so a one-field change must read-modify-write or the rest is
        # stored as zero.
        current = {
            "user_id": 42,
            "daily_max_usd": 50,
            "per_request_max_usd": 1,
            "monthly_max_usd": 500,
            "auto_pause_below_usd": 2,
            "pool_allocation": '{"operations":0.6,"insurance":0.15,"savings":0.15,"dividends":0.1}',
            "updated_at": 1718841600,
        }
        responses = [_mock_response(current), _mock_response({"success": True})]
        with patch.object(wallet._session, "request", side_effect=responses) as m:
            wallet.set_limit(daily_max_usd=30)

        sent = m.call_args.kwargs["json"]
        assert sent["daily_max_usd"] == 30
        assert sent["monthly_max_usd"] == 500, "monthly limit must survive the replacing PUT"
        assert sent["per_request_max_usd"] == 1
        assert sent["auto_pause_below_usd"] == 2
        assert "pool_allocation" in sent, "dropping this makes pools() fall back to defaults"
        # updated_at is server-assigned and should not be echoed back.
        assert "updated_at" not in sent


class TestWalletPools:
    def test_returns_pools(self, wallet):
        expected = {
            "allocation": {"operations": 0.60, "insurance": 0.15, "savings": 0.15, "dividends": 0.10},
            "pool_balances": {"operations": "3.5760", "insurance": "0.8940",
                              "savings": "0.8940", "dividends": "0.5960"},
        }
        with patch.object(wallet._session, "request", return_value=_mock_response(expected)):
            result = wallet.pools()
        assert result["allocation"]["operations"] == 0.60
        assert result["pool_balances"]["dividends"] == "0.5960"
