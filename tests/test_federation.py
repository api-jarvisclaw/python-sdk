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

    def test_call_defaults_payload_to_empty_object(self, fed):
        with patch.object(
            fed._session, "request", return_value=_mock_response({"result": "ok"})
        ) as req:
            fed.call(7)

        _, kwargs = req.call_args
        assert kwargs["json"]["payload"] == {}, "a None payload must not be sent as null"

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
