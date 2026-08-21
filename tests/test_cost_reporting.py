"""What a call reported spending, versus what it actually cost.

The cost log used a flat ``tokens * 0.00001`` for every model. That is not an estimate
of anything: measured against the gateway, one turn on google/gemini-3.5-flash at
max_tokens=1536 is charged $0.207405, while the formula reports about $0.0012 —
under-reporting by roughly 170x.

A real session printed ``spent: $0.001150`` after the wallet had paid $1.47. That is
worse than printing nothing, because it reads as reassurance.
"""

import json

import pytest

from jarvisclaw._base import _quoted_usd


class FakeResponse:
    """Minimal stand-in for requests.Response for the quote parser."""

    def __init__(self, payload, raises=False):
        self._payload = payload
        self._raises = raises

    def json(self):
        if self._raises:
            raise ValueError("not json")
        return self._payload


def challenge(amount, field="amount", version="accepts"):
    return {version: [{field: amount, "network": "eip155:8453"}]}


class TestQuotedUsd:
    def test_reads_the_v2_amount(self):
        # 207405 base units is the real measured charge for one 1536-token turn.
        assert _quoted_usd(FakeResponse(challenge("207405"))) == pytest.approx(0.207405)

    def test_reads_the_v1_field_name(self):
        assert _quoted_usd(
            FakeResponse(challenge("13545", field="maxAmountRequired"))
        ) == pytest.approx(0.013545)

    def test_reads_the_v1_container(self):
        assert _quoted_usd(
            FakeResponse(challenge("1000", version="payments"))
        ) == pytest.approx(0.001)

    def test_accepts_an_integer_amount(self):
        assert _quoted_usd(FakeResponse(challenge(207405))) == pytest.approx(0.207405)

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"accepts": []},
            {"accepts": [{}]},
            {"accepts": [{"amount": ""}]},
            {"accepts": [{"amount": "not-a-number"}]},
            {"accepts": [{"amount": None}]},
        ],
    )
    def test_unreadable_quote_is_none_not_zero(self, payload):
        # None, never 0.0. Zero would be recorded as "this call was free", which is the
        # one reading that is certainly wrong for a 402 — and it would silently
        # under-report instead of falling back to estimation.
        assert _quoted_usd(FakeResponse(payload)) is None

    def test_unparseable_body_is_none(self):
        assert _quoted_usd(FakeResponse(None, raises=True)) is None


class Tracker:
    """The cost-tracking half of BaseClient, isolated from HTTP."""

    def __init__(self, tmp_home, monkeypatch):
        from jarvisclaw import _base

        monkeypatch.setattr(_base.Path, "home", staticmethod(lambda: tmp_home))
        self._total_spent = 0.0
        self._last_quoted_usd = None
        self._track_cost = _base.BaseClient._track_cost.__get__(self)
        self._log = tmp_home / ".jarvisclaw" / "cost_log.jsonl"

    def entries(self):
        if not self._log.exists():
            return []
        return [json.loads(line) for line in self._log.read_text().splitlines() if line]


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    return Tracker(tmp_path, monkeypatch)


class TestTrackCost:
    def test_records_what_was_actually_paid(self, tracker):
        tracker._last_quoted_usd = 0.207405
        tracker._track_cost("google/gemini-3.5-flash", "/v1/chat/completions", {"total_tokens": 115})

        entry = tracker.entries()[0]
        assert entry["usd"] == pytest.approx(0.207405)
        assert entry["source"] == "x402_quote"
        # The old formula would have reported $0.00115 for these 115 tokens — the exact
        # number a real session printed while $1.47 left the wallet.
        assert "estimated_usd" not in entry
        assert tracker._total_spent == pytest.approx(0.207405)

    def test_falls_back_to_estimation_when_nothing_was_paid(self, tracker):
        # API-key mode and free models never see a 402, so there is no quote to use.
        tracker._track_cost("free/chat", "/v1/chat/completions", {"total_tokens": 500})

        entry = tracker.entries()[0]
        assert entry["estimated_usd"] == pytest.approx(0.005)
        assert entry["source"] == "token_estimate"
        assert "usd" not in entry

    def test_the_two_kinds_are_labelled_so_they_cannot_be_confused(self, tracker):
        tracker._last_quoted_usd = 0.05
        tracker._track_cost("paid/model", "/v1/chat/completions", {"total_tokens": 10})
        tracker._track_cost("free/model", "/v1/chat/completions", {"total_tokens": 10})

        sources = [e["source"] for e in tracker.entries()]
        assert sources == ["x402_quote", "token_estimate"]

    def test_a_quote_is_consumed_not_carried(self, tracker):
        # The failure this prevents: one paid call making every later free call report
        # the same charge, inflating the session total without limit.
        tracker._last_quoted_usd = 0.207405
        tracker._track_cost("paid/model", "/v1/chat/completions", {"total_tokens": 100})
        tracker._track_cost("free/model", "/v1/chat/completions", {"total_tokens": 100})

        first, second = tracker.entries()
        assert first["usd"] == pytest.approx(0.207405)
        assert second["source"] == "token_estimate"
        assert tracker._total_spent == pytest.approx(0.207405 + 0.001)

    def test_session_total_accumulates_real_charges(self, tracker):
        # Six turns, the shape of the reported incident.
        for _ in range(6):
            tracker._last_quoted_usd = 0.207405
            tracker._track_cost("google/gemini-3.5-flash", "/v1/chat/completions", {"total_tokens": 200})

        assert tracker._total_spent == pytest.approx(1.24443)
        # Which is the bill the user actually saw, rather than the $0.012 the old
        # formula would have reported for the same six turns.
        assert tracker._total_spent > 1.0
