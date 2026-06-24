"""Tests for IntentClient."""
from unittest.mock import patch, MagicMock

import pytest

from jarvisclaw.intent import IntentClient


@pytest.fixture
def intent():
    return IntentClient(api_key="sk-test")


def _mock_response(data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.headers = {"content-type": "application/json"}
    return resp


class TestIntentResolve:
    def test_resolve_basic(self, intent):
        expected = {
            "matches": [
                {"provider_id": "gpt-4o", "score": 0.95, "estimated_price_usd": 0.003,
                 "endpoint": "/v1/chat/completions", "model": "gpt-4o", "reason": "lowest cost"}
            ],
            "intent_type": "chat_completion",
            "total_available": 142,
        }
        with patch.object(intent._session, "request", return_value=_mock_response(expected)):
            result = intent.resolve("chat_completion", constraints={"max_price_usd": 0.01})
        assert len(result["matches"]) == 1
        assert result["matches"][0]["provider_id"] == "gpt-4o"
        assert result["intent_type"] == "chat_completion"

    def test_resolve_without_constraints(self, intent):
        expected = {"matches": [], "intent_type": "image_generation", "total_available": 0}
        with patch.object(intent._session, "request", return_value=_mock_response(expected)):
            result = intent.resolve("image_generation")
        assert result["total_available"] == 0


class TestIntentExecute:
    def test_execute_returns_raw_response(self, intent):
        upstream_response = {
            "id": "chatcmpl-123",
            "choices": [{"message": {"role": "assistant", "content": "Hello!"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 10},
        }
        with patch.object(intent._session, "request", return_value=_mock_response(upstream_response)):
            result = intent.execute(
                "chat_completion",
                payload={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert result["choices"][0]["message"]["content"] == "Hello!"


class TestIntentExecuteBudget:
    def test_execute_budget_success(self, intent):
        expected = {
            "request_id": "req-123",
            "status": "success",
            "provider": "gpt-4o-mini",
            "model": "gpt-4o-mini",
            "actual_cost_usd": 0.002,
            "duration_ms": 1250,
            "risk_level": "low",
        }
        with patch.object(intent._session, "request", return_value=_mock_response(expected)):
            result = intent.execute_budget(
                "chat_completion",
                payload={"messages": [{"role": "user", "content": "hi"}]},
                budget={"max_total_usd": 0.05},
            )
        assert result["status"] == "success"
        assert result["actual_cost_usd"] == 0.002

    def test_execute_budget_rejected(self, intent):
        expected = {
            "request_id": "req-456",
            "status": "rejected",
            "reason": "critical risk: request blocked",
            "risk_level": "critical",
            "duration_ms": 15,
        }
        with patch.object(intent._session, "request", return_value=_mock_response(expected)):
            result = intent.execute_budget(
                "chat_completion",
                payload={"messages": [{"role": "user", "content": "hack the planet"}]},
                budget={"max_total_usd": 100},
            )
        # Rejected status does NOT raise — returns normally
        assert result["status"] == "rejected"
        assert "critical risk" in result["reason"]


class TestIntentAudit:
    def test_audit_returns_entries(self, intent):
        expected = {
            "entries": [
                {"timestamp": "2026-06-20T10:00:00Z", "request_id": "req-1",
                 "user_id": 42, "event_type": "settlement_confirmed", "details": {}}
            ],
            "count": 1,
        }
        with patch.object(intent._session, "request", return_value=_mock_response(expected)):
            result = intent.audit()
        assert result["count"] == 1
        assert result["entries"][0]["event_type"] == "settlement_confirmed"


class TestIntentTypes:
    def test_types_returns_list(self, intent):
        expected = {"intent_types": ["chat_completion", "image_generation", "video_generation"]}
        with patch.object(intent._session, "request", return_value=_mock_response(expected)):
            result = intent.types()
        assert isinstance(result, list)
        assert "chat_completion" in result
        assert len(result) == 3


class TestIntentProviders:
    def test_providers_returns_list(self, intent):
        expected = {
            "providers": [
                {"id": "gpt-4o", "name": "gpt-4o", "intent_types": ["chat_completion"],
                 "pricing": {"input_per_million": 2.5}, "features": [], "endpoint": "/v1/chat/completions", "source": "internal"}
            ],
            "total": 1,
        }
        with patch.object(intent._session, "request", return_value=_mock_response(expected)):
            result = intent.providers()
        assert result["total"] == 1
        assert result["providers"][0]["id"] == "gpt-4o"
