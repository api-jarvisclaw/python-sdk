"""Tests for LLMClient."""
import pytest
import responses

from jarvisclaw import LLMClient, APIError, AuthenticationError, RateLimitError


@responses.activate
def test_chat_api_key():
    responses.add(
        responses.POST,
        "https://api.jarvisclaw.ai/v1/chat/completions",
        json={"choices": [{"message": {"content": "Hi there!"}}], "model": "auto", "id": "chatcmpl-1"},
        status=200,
    )
    client = LLMClient(api_key="sk-test")
    result = client.chat("auto", "Hello!")
    assert result == "Hi there!"
    assert "Bearer sk-test" in responses.calls[0].request.headers["Authorization"]


@responses.activate
def test_chat_completion():
    responses.add(
        responses.POST,
        "https://api.jarvisclaw.ai/v1/chat/completions",
        json={"choices": [{"message": {"content": "World"}}], "model": "gpt-5", "id": "x", "usage": {"total_tokens": 10}},
        status=200,
    )
    client = LLMClient(api_key="sk-test")
    resp = client.chat_completion("gpt-5", [{"role": "user", "content": "Hello"}])
    assert resp.content == "World"
    assert resp.model == "gpt-5"
    assert resp.usage["total_tokens"] == 10


@responses.activate
def test_image_generate():
    responses.add(
        responses.POST,
        "https://api.jarvisclaw.ai/v1/images/generations",
        json={"data": [{"url": "https://img.example.com/cat.png"}]},
        status=200,
    )
    client = LLMClient(api_key="sk-test")
    img = client.image_generate("flux/schnell", "A cat")
    assert img.url == "https://img.example.com/cat.png"


@responses.activate
def test_list_models():
    responses.add(
        responses.GET,
        "https://api.jarvisclaw.ai/v1/models",
        json={"data": [{"id": "openai/gpt-5", "object": "model", "owned_by": "openai"}]},
        status=200,
    )
    client = LLMClient(api_key="sk-test")
    models = client.list_models()
    assert len(models) == 1
    assert models[0].id == "openai/gpt-5"


@responses.activate
def test_401_raises_auth_error():
    responses.add(
        responses.POST,
        "https://api.jarvisclaw.ai/v1/chat/completions",
        json={"message": "Invalid API key"},
        status=401,
    )
    client = LLMClient(api_key="sk-bad")
    with pytest.raises(AuthenticationError):
        client.chat("auto", "Hello")


@responses.activate
def test_429_raises_rate_limit():
    responses.add(
        responses.POST,
        "https://api.jarvisclaw.ai/v1/chat/completions",
        json={"message": "Too many requests"},
        status=429,
    )
    client = LLMClient(api_key="sk-test")
    with pytest.raises(RateLimitError):
        client.chat("auto", "Hello")


@responses.activate
def test_prediction():
    responses.add(
        responses.GET,
        "https://api.jarvisclaw.ai/v1/prediction/polymarket/markets",
        json={"markets": [{"slug": "test"}]},
        status=200,
    )
    client = LLMClient(api_key="sk-test")
    data = client.prediction("polymarket/markets")
    assert "markets" in data


def test_no_credentials_raises():
    import os
    os.environ.pop("JARVISCLAW_API_KEY", None)
    os.environ.pop("JARVISCLAW_WALLET_KEY", None)
    with pytest.raises(ValueError, match="Provide api_key or private_key"):
        LLMClient()


@responses.activate
def test_smart_chat():
    responses.add(
        responses.POST,
        "https://api.jarvisclaw.ai/v1/chat/completions",
        json={"choices": [{"message": {"content": "4"}}], "model": "auto"},
        status=200,
    )
    client = LLMClient(api_key="sk-test")
    result = client.smart_chat("What is 2+2?")
    assert result == "4"
    body = responses.calls[0].request.body
    assert b'"model": "auto"' in body or b'"model":"auto"' in body
