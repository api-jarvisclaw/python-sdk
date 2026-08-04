"""Tests for FederationClient's search -> call flow.

search() returned results without a resource_id and call() did not exist, so the
obvious flow -- search the catalogue, invoke a hit -- could not be expressed: execute()
is keyed by resource_id and nothing in a search result carried one. The gateway's
public DTO omitted the field and this SDK mirrors that DTO.
"""
from unittest.mock import patch

import pytest

from jarvisclaw.federation import FederationClient


@pytest.fixture
def fed():
    return FederationClient(api_key="sk-test")


def _mock_response(data, status_code=200):
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.headers = {"content-type": "application/json"}
    return resp


class TestSearchToCallFlow:
    def test_search_result_carries_the_handle_call_needs(self, fed):
        payload = {
            "success": True,
            "data": [
                {
                    "resource_id": 31,
                    "name": "Google Search",
                    "path": "/google-search",
                    "method": "POST",
                    "sell_price": 0.002875,
                }
            ],
        }
        with patch.object(fed._session, "request", return_value=_mock_response(payload)):
            hits = fed.search("google")

        assert hits, "search must return the seeded hit"
        assert hits[0]["resource_id"] == 31, (
            "without resource_id the result cannot be passed to call()/execute()"
        )

    def test_call_sends_resource_id_and_payload(self, fed):
        with patch.object(
            fed._session, "request", return_value=_mock_response({"result": "ok"})
        ) as req:
            fed.call(31, {"query": "x402"})

        _, kwargs = req.call_args
        assert kwargs["json"] == {"resource_id": 31, "payload": {"query": "x402"}}, (
            "the gateway keys the request on resource_id, not id"
        )

    def test_call_omits_payload_when_there_is_none(self, fed):
        # This asserted payload == {} and that was the wrong shape to send.
        #
        # The gateway distinguishes an absent payload from an empty one: execute only
        # marshals a body for the upstream when Payload is non-nil, and its own
        # readFederationPayload keeps an empty request body nil for the stated reason
        # that sending "{}" to an endpoint expecting no body is a real difference to
        # some upstreams. Defaulting to {} collapsed that distinction, so a caller had
        # no way to express "no body" at all.
        #
        # Still not null, which is what the old assertion was guarding against: the key
        # is absent rather than present-and-nil.
        with patch.object(
            fed._session, "request", return_value=_mock_response({"result": "ok"})
        ) as req:
            fed.call(7)

        _, kwargs = req.call_args
        assert kwargs["json"] == {"resource_id": 7}, "an absent payload must not be invented"
        assert "payload" not in kwargs["json"]

    def test_call_still_forwards_an_explicitly_empty_payload(self, fed):
        # The other half of the distinction above: {} passed deliberately must reach
        # the upstream as {}, not be dropped as if it were absent.
        with patch.object(
            fed._session, "request", return_value=_mock_response({"result": "ok"})
        ) as req:
            fed.call(7, {})

        _, kwargs = req.call_args
        assert kwargs["json"] == {"resource_id": 7, "payload": {}}

    @pytest.mark.parametrize("bad", [0, -1, "31", None, 3.0, True, False])
    def test_call_rejects_a_non_positive_or_non_int_id(self, fed, bad):
        # Fails locally rather than sending a request the gateway will reject, so the
        # error names the actual mistake.
        #
        # True/False are in the list because bool subclasses int in Python: without an
        # explicit check, call(True) would be sent as resource_id=1 — a silent request
        # for an unrelated resource rather than an error.
        with pytest.raises(ValueError):
            fed.call(bad)

    def test_execute_still_accepts_a_raw_body(self, fed):
        # call() is a convenience wrapper; the escape hatch must keep working for
        # fields this SDK does not model.
        with patch.object(
            fed._session, "request", return_value=_mock_response({"result": "ok"})
        ) as req:
            fed.execute({"resource_id": 9, "payload": {}, "extra": "passthrough"})

        _, kwargs = req.call_args
        assert kwargs["json"]["extra"] == "passthrough"


class TestInvokePayloadShape:
    """invoke() targets the marketplace path, where the same absent/empty
    distinction applies."""

    def test_invoke_omits_the_body_when_there_is_no_payload(self, fed):
        with patch.object(
            fed._session, "request", return_value=_mock_response({"ok": True})
        ) as req:
            fed.invoke(476)

        args, kwargs = req.call_args
        assert args[1].endswith("/v1/marketplace/api/476")
        assert kwargs.get("json") is None, "no payload must mean no body, not {}"

    def test_invoke_forwards_an_explicit_payload(self, fed):
        with patch.object(
            fed._session, "request", return_value=_mock_response({"ok": True})
        ) as req:
            fed.invoke(476, payload={"url": "x"})

        _, kwargs = req.call_args
        assert kwargs["json"] == {"url": "x"}

    def test_invoke_get_sends_the_payload_as_query_params(self, fed):
        # A GET resource takes its input in the query string; the gateway's own
        # method wins over this one, but the params still have to travel.
        with patch.object(
            fed._session, "request", return_value=_mock_response({"ok": True})
        ) as req:
            fed.invoke(476, payload={"pair": "BTC-USDT"}, method="GET")

        _, kwargs = req.call_args
        assert kwargs["params"] == {"pair": "BTC-USDT"}


class TestUnifiedFederationSurface:
    """The unified JarvisClaw client is the documented entry point, so the
    discovery-to-invocation path has to be expressible there too — it had
    search_federation and a raw federation_execute, and nothing between them."""

    @pytest.fixture
    def jc(self):
        from jarvisclaw import JarvisClaw

        return JarvisClaw(api_key="sk-test")

    def test_list_apis_unwraps_the_envelope(self, jc):
        body = {
            "success": True,
            "data": {
                "items": [{"resource_id": 64, "name": "Summarize Text"}],
                "total": 2720,
                "page": 1,
                "page_size": 1,
                "categories": [{"category": "ai tools", "count": 312}],
            },
        }
        with patch.object(jc._session, "request", return_value=_mock_response(body)) as req:
            page = jc.list_apis(page_size=1, keyword="summar")

        args, kwargs = req.call_args
        assert args[1].endswith("/api/marketplace/apis")
        # The gateway names this parameter q, not keyword or search.
        assert kwargs["params"]["q"] == "summar"
        assert page["total"] == 2720, "the {success,data} envelope must be unwrapped"
        assert page["items"][0]["resource_id"] == 64

    def test_call_resource_builds_the_execute_body(self, jc):
        with patch.object(
            jc._session, "request", return_value=_mock_response({"success": True})
        ) as req:
            jc.call_resource(476, {"url": "x"})

        args, kwargs = req.call_args
        assert args[1].endswith("/v1/federation/execute")
        assert kwargs["json"] == {"resource_id": 476, "payload": {"url": "x"}}

    def test_invoke_resource_targets_the_marketplace_path(self, jc):
        with patch.object(
            jc._session, "request", return_value=_mock_response({"decoded": []})
        ) as req:
            jc.invoke_resource(476, {"url": "x"})

        args, kwargs = req.call_args
        assert args[1].endswith("/v1/marketplace/api/476")
        assert kwargs["json"] == {"url": "x"}

    @pytest.mark.parametrize("bad", [0, -1, "31", None, 3.0, True, False])
    def test_both_wrappers_reject_a_bad_id(self, jc, bad):
        with pytest.raises(ValueError):
            jc.call_resource(bad)
        with pytest.raises(ValueError):
            jc.invoke_resource(bad)
