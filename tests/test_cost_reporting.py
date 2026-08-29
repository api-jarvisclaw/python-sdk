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


class TestAgentCostFeedsTheBudgetGate:
    """Agent._estimate_cost had the same flat rate, and it is load-bearing there.

    BaseClient._track_cost only writes a log. Agent._estimate_cost feeds
    CostTracker.over_budget, which raises BudgetExceededError — so under-reporting
    does not merely misinform, it disables the budget the caller asked for.
    """

    @pytest.fixture()
    def agent(self):
        from jarvisclaw import Agent

        return Agent(api_key="sk-test")

    def test_prefers_the_paid_quote_over_token_math(self, agent):
        agent._last_quoted_usd = 0.207405
        # Token math on this usage yields $0.002 — off by ~100x if it wins.
        cost = agent._estimate_cost(
            {"usage": {"prompt_tokens": 100, "completion_tokens": 100}},
            "google/gemini-3.5-flash",
        )
        assert cost == pytest.approx(0.207405)

    def test_a_budget_is_breached_by_real_prices_not_estimated_ones(self, agent):
        from jarvisclaw import BudgetExceededError
        from jarvisclaw.agent import CostTracker

        tracker = CostTracker(budget_usd=0.50)
        # Three paid turns at the measured price = $0.62, over a $0.50 budget.
        for _ in range(3):
            agent._last_quoted_usd = 0.207405
            tracker.record(
                agent._estimate_cost({"usage": {"total_tokens": 200}}, "m"), "m"
            )

        assert tracker.over_budget, (
            "three turns at the real $0.207405 exceed a $0.50 budget; under the old "
            "flat rate they reported $0.006 and the gate never tripped, so an agent "
            "given budget=0.50 would keep spending"
        )
        # And the error a caller sees carries the real figure.
        err = BudgetExceededError(tracker.budget_usd, tracker.spent_usd)
        assert err.spent > 0.6

    def test_server_reported_cost_beats_token_math(self, agent):
        agent._last_quoted_usd = None
        cost = agent._estimate_cost(
            {"usage": {"total_tokens": 200, "total_cost_usd": 0.05}}, "m"
        )
        assert cost == pytest.approx(0.05)

    def test_a_quote_is_consumed_not_carried(self, agent):
        # Note the usage shape: this path sums prompt_tokens + completion_tokens.
        # total_tokens is _track_cost's field and is ignored here.
        usage = {"usage": {"prompt_tokens": 50, "completion_tokens": 50}}
        agent._last_quoted_usd = 0.207405
        first = agent._estimate_cost(usage, "m")
        second = agent._estimate_cost(usage, "m")

        assert first == pytest.approx(0.207405)
        assert second == pytest.approx(0.001), (
            "the second call was not paid per request, so it must fall back to the "
            "estimate rather than inherit the first call's price"
        )

    def test_unpaid_calls_still_fall_back_to_token_math(self, agent):
        # API-key mode and free models produce no quote; reporting 0.0 there would
        # hide real (if cheap) usage.
        agent._last_quoted_usd = None
        cost = agent._estimate_cost(
            {"usage": {"prompt_tokens": 600, "completion_tokens": 400}}, "m"
        )
        assert cost == pytest.approx(0.01)

    def test_usage_without_the_expected_token_fields_reports_nothing(self, agent):
        # Documents a real sharp edge rather than asserting it is fine: a usage dict
        # carrying only total_tokens yields 0.0 here, because this path reads
        # prompt_tokens/completion_tokens. Worth knowing before reusing this helper.
        agent._last_quoted_usd = None
        assert agent._estimate_cost({"usage": {"total_tokens": 1000}}, "m") == 0.0

    def test_no_usage_reports_nothing(self, agent):
        agent._last_quoted_usd = None
        assert agent._estimate_cost({}, "m") == 0.0
