"""Regression tests for previously failing scenarios.

Only tests the specific failures from test_report_2026-06-06.md:
- X402 wallet payment (verify + settle via CDP facilitator)
- auto/video smart routing
- auto/music smart routing
- tts-1 channel availability
- Search endpoint
- Marketplace proxy routes
- Async streaming

Run:
  export JARVISCLAW_API_KEY=sk-OtqnrUGuNoROqKbJR9IlUFbQclLSH2vFWsvjMnR5744ZHMF0
  export JARVISCLAW_WALLET_KEY=<your_wallet_private_key>
  export JARVISCLAW_BASE_URL=https://api.jarvisclaw.ai
  pytest tests/test_regression.py -v -s
"""
import os
import asyncio
import time

import pytest

API_KEY = os.environ.get("JARVISCLAW_API_KEY")
WALLET_KEY = os.environ.get("JARVISCLAW_WALLET_KEY")
BASE_URL = os.environ.get("JARVISCLAW_BASE_URL")

skip_no_api_key = pytest.mark.skipif(not API_KEY, reason="JARVISCLAW_API_KEY not set")
skip_no_wallet = pytest.mark.skipif(not WALLET_KEY, reason="JARVISCLAW_WALLET_KEY not set")


def make_client(cls, auth_mode: str):
    kwargs = {}
    if BASE_URL:
        kwargs["base_url"] = BASE_URL
    if auth_mode == "api_key":
        return cls(api_key=API_KEY, **kwargs)
    return cls(private_key=WALLET_KEY, **kwargs)


def log_result(test_name: str, **details):
    print(f"\n{'─' * 60}")
    print(f"  TEST: {test_name}")
    print(f"{'─' * 60}")
    for key, value in details.items():
        if isinstance(value, str) and len(value) > 200:
            value = value[:200] + "..."
        print(f"  {key}: {value}")
    print(f"{'─' * 60}\n")


# ═══════════════════════════════════════════════════════════════
# P0: X402 Wallet Payment (was: 402 payment verification failed)
# ═══════════════════════════════════════════════════════════════

class TestX402WalletPayment:
    """X402 wallet auth — previously ALL failed with 402 verify error."""

    @skip_no_wallet
    def test_chat_x402(self):
        from jarvisclaw import ChatClient
        chat = make_client(ChatClient, "x402")
        start = time.time()
        result = chat.complete("Say 'x402 works' and nothing else", model="auto")
        elapsed = time.time() - start
        log_result("X402 Chat",
                   response=result,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert isinstance(result, str)
        assert len(result) > 0

    @skip_no_wallet
    def test_image_x402(self):
        from jarvisclaw import ImageClient
        img = make_client(ImageClient, "x402")
        start = time.time()
        result = img.generate("A red circle on white background", model="openai/gpt-image-1")
        elapsed = time.time() - start
        log_result("X402 Image",
                   url=result if isinstance(result, str) else str(result)[:100],
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None

    @skip_no_wallet
    def test_search_x402(self):
        from jarvisclaw import SearchClient
        search = make_client(SearchClient, "x402")
        start = time.time()
        result = search.query("What is the current Bitcoin price?")
        elapsed = time.time() - start
        log_result("X402 Search",
                   response=str(result)[:200],
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None


# ═══════════════════════════════════════════════════════════════
# P1: Model Routing (was: 400 Unknown model / 503 No channel)
# ═══════════════════════════════════════════════════════════════

class TestModelRouting:
    """Smart route models that previously returned 400/503."""

    @skip_no_api_key
    def test_auto_video(self):
        """auto/video was returning 'Unknown video model'."""
        from jarvisclaw import VideoClient
        video = make_client(VideoClient, "api_key")
        start = time.time()
        result = video.generate("A cat walking in a garden", model="auto/video")
        elapsed = time.time() - start
        log_result("auto/video routing",
                   result=str(result)[:200],
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None

    @skip_no_api_key
    def test_auto_music(self):
        """auto/music was returning 'Unknown audio model'."""
        from jarvisclaw import AudioClient
        audio = make_client(AudioClient, "api_key")
        start = time.time()
        result = audio.music("A calm lo-fi beat", model="auto/music")
        elapsed = time.time() - start
        log_result("auto/music routing",
                   result=str(result)[:200],
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None

    @skip_no_api_key
    def test_tts(self):
        """tts-1 was returning 'No available channel'."""
        from jarvisclaw import AudioClient
        audio = make_client(AudioClient, "api_key")
        start = time.time()
        result = audio.speech("Hello, this is a test.", model="tts-1")
        elapsed = time.time() - start
        log_result("tts-1 channel",
                   result_type=type(result).__name__,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None

    @skip_no_api_key
    def test_search(self):
        """Search was returning 'No available channel'."""
        from jarvisclaw import SearchClient
        search = make_client(SearchClient, "api_key")
        start = time.time()
        result = search.query("What is Python?")
        elapsed = time.time() - start
        log_result("Search channel",
                   response=str(result)[:200],
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None


# ═══════════════════════════════════════════════════════════════
# P2: Marketplace Routes (was: 404 Not Found)
# ═══════════════════════════════════════════════════════════════

class TestMarketplaceRoutes:
    """Marketplace proxy routes that previously 404'd."""

    @skip_no_api_key
    def test_crypto_price(self):
        """Was 404 on /v1/marketplace/surf/exchange/prices."""
        from jarvisclaw import MarketplaceClient
        mp = make_client(MarketplaceClient, "api_key")
        start = time.time()
        result = mp.search("BTC price")
        elapsed = time.time() - start
        log_result("Marketplace search",
                   response=str(result)[:200],
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None


# ═══════════════════════════════════════════════════════════════
# P3: Async Streaming (was: empty chunks)
# ═══════════════════════════════════════════════════════════════

class TestAsyncStream:
    """Async streaming returned 0 chunks."""

    @skip_no_api_key
    def test_async_stream(self):
        from jarvisclaw.aio import ChatClient as AsyncChatClient

        async def run():
            kwargs = {}
            if BASE_URL:
                kwargs["base_url"] = BASE_URL
            chat = AsyncChatClient(api_key=API_KEY, **kwargs)
            chunks = []
            async for chunk in chat.stream("Count 1 to 3", model="auto"):
                chunks.append(chunk)
            return chunks

        start = time.time()
        chunks = asyncio.run(run())
        elapsed = time.time() - start
        full_text = "".join(chunks)
        log_result("Async stream",
                   chunks=len(chunks),
                   text=full_text[:100],
                   latency_ms=f"{elapsed*1000:.0f}")
        assert len(chunks) > 0, f"Expected chunks > 0, got {len(chunks)}"
