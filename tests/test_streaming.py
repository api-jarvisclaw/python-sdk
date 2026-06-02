"""Tests for SSE streaming parser."""
from unittest.mock import MagicMock

from jarvisclaw.streaming import stream_chat_response


def make_sse_response(lines: list[str]):
    """Create a mock response with iter_lines."""
    resp = MagicMock()
    resp.iter_lines.return_value = iter(lines)
    return resp


def test_stream_basic():
    resp = make_sse_response([
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        'data: [DONE]',
    ])
    chunks = list(stream_chat_response(resp))
    assert chunks == ["Hello", " world"]


def test_stream_skips_empty_lines():
    resp = make_sse_response([
        '',
        'data: {"choices":[{"delta":{"content":"Hi"}}]}',
        '',
        'data: [DONE]',
    ])
    chunks = list(stream_chat_response(resp))
    assert chunks == ["Hi"]


def test_stream_skips_non_data_lines():
    resp = make_sse_response([
        'event: ping',
        'data: {"choices":[{"delta":{"content":"OK"}}]}',
        'data: [DONE]',
    ])
    chunks = list(stream_chat_response(resp))
    assert chunks == ["OK"]


def test_stream_handles_empty_delta():
    resp = make_sse_response([
        'data: {"choices":[{"delta":{}}]}',
        'data: {"choices":[{"delta":{"content":"X"}}]}',
        'data: [DONE]',
    ])
    chunks = list(stream_chat_response(resp))
    assert chunks == ["X"]


def test_stream_handles_malformed_json():
    resp = make_sse_response([
        'data: {invalid json',
        'data: {"choices":[{"delta":{"content":"OK"}}]}',
        'data: [DONE]',
    ])
    chunks = list(stream_chat_response(resp))
    assert chunks == ["OK"]
