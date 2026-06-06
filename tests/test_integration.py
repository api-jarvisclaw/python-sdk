"""Integration tests for JarvisClaw Python SDK.

Requires environment variables:
  JARVISCLAW_API_KEY     — API key for testing (sk-...)
  JARVISCLAW_WALLET_KEY  — x402 EVM wallet private key (0x...)

Run:
  pytest tests/test_integration.py -v -s
  pytest tests/test_integration.py -v -s -k "api_key"    # only API key tests
  pytest tests/test_integration.py -v -s -k "x402"       # only x402 tests

The -s flag enables print output so you can see detailed results.
"""
import os
import asyncio
import time

import pytest

# ─── Auth fixtures ──────────────────────────────────────────

API_KEY = os.environ.get("JARVISCLAW_API_KEY")
WALLET_KEY = os.environ.get("JARVISCLAW_WALLET_KEY")
BASE_URL = os.environ.get("JARVISCLAW_BASE_URL")

skip_no_api_key = pytest.mark.skipif(not API_KEY, reason="JARVISCLAW_API_KEY not set")
skip_no_wallet = pytest.mark.skipif(not WALLET_KEY, reason="JARVISCLAW_WALLET_KEY not set")


def make_client(cls, auth_mode: str):
    """Create a client with the specified auth mode."""
    kwargs = {}
    if BASE_URL:
        kwargs["base_url"] = BASE_URL
    if auth_mode == "api_key":
        return cls(api_key=API_KEY, **kwargs)
    return cls(private_key=WALLET_KEY, **kwargs)


def log_result(test_name: str, **details):
    """Print detailed test result for logging."""
    print(f"\n{'─' * 60}")
    print(f"  TEST: {test_name}")
    print(f"{'─' * 60}")
    for key, value in details.items():
        if isinstance(value, str) and len(value) > 200:
            value = value[:200] + "..."
        print(f"  {key}: {value}")
    print(f"{'─' * 60}\n")


# ─── ChatClient Tests ───────────────────────────────────────

class TestChatClientAPIKey:
    """ChatClient integration tests with API key auth."""

    @skip_no_api_key
    def test_complete(self):
        from jarvisclaw import ChatClient
        chat = make_client(ChatClient, "api_key")
        start = time.time()
        result = chat.complete("Say 'hello' and nothing else", model="auto")
        elapsed = time.time() - start
        log_result("Chat.complete (APIKey)",
                   response=result,
                   model_used="auto → smart-route",
                   latency_ms=f"{elapsed*1000:.0f}",
                   auth="API Key")
        assert isinstance(result, str)
        assert len(result) > 0

    @skip_no_api_key
    def test_completion_with_messages(self):
        from jarvisclaw import ChatClient
        chat = make_client(ChatClient, "api_key")
        start = time.time()
        resp = chat.completion([
            {"role": "system", "content": "Reply with exactly one word."},
            {"role": "user", "content": "What color is the sky?"},
        ], model="auto")
        elapsed = time.time() - start
        log_result("Chat.completion (APIKey)",
                   content=resp.content,
                   model=resp.model,
                   usage=resp.usage,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert resp.content is not None
        assert isinstance(resp.content, str)
        assert len(resp.content) > 0
        assert resp.model is not None
        assert "/" in resp.model  # smart-route resolves to vendor/model format
        assert resp.id is not None  # response ID
        assert isinstance(resp.usage, dict)
        assert "prompt_tokens" in resp.usage or "total_tokens" in resp.usage

    @skip_no_api_key
    def test_stream(self):
        from jarvisclaw import ChatClient
        chat = make_client(ChatClient, "api_key")
        start = time.time()
        chunks = list(chat.stream("Count from 1 to 3", model="auto"))
        elapsed = time.time() - start
        full_text = "".join(chunks)
        log_result("Chat.stream (APIKey)",
                   chunk_count=len(chunks),
                   full_response=full_text,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert len(chunks) > 0
        assert "1" in full_text


class TestChatClientX402:
    """ChatClient integration tests with x402 wallet auth."""

    @skip_no_wallet
    def test_complete(self):
        from jarvisclaw import ChatClient
        chat = make_client(ChatClient, "x402")
        start = time.time()
        result = chat.complete("Say 'hello' and nothing else", model="auto")
        elapsed = time.time() - start
        log_result("Chat.complete (X402)",
                   response=result,
                   latency_ms=f"{elapsed*1000:.0f}",
                   auth="x402 wallet")
        assert isinstance(result, str)
        assert len(result) > 0

    @skip_no_wallet
    def test_stream(self):
        from jarvisclaw import ChatClient
        chat = make_client(ChatClient, "x402")
        start = time.time()
        chunks = list(chat.stream("Say 'test'", model="auto"))
        elapsed = time.time() - start
        full_text = "".join(chunks)
        log_result("Chat.stream (X402)",
                   chunk_count=len(chunks),
                   full_response=full_text,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert len(chunks) > 0


# ─── ImageClient Tests ──────────────────────────────────────

class TestImageClientAPIKey:
    """ImageClient integration tests with API key auth."""

    @skip_no_api_key
    @pytest.mark.timeout(120)
    def test_generate_blocking(self):
        from jarvisclaw import ImageClient
        image = make_client(ImageClient, "api_key")
        start = time.time()
        result = image.generate("A simple red circle on white background", size="1024x1024")
        elapsed = time.time() - start
        log_result("Image.generate blocking (APIKey)",
                   url=result.url,
                   revised_prompt=result.revised_prompt,
                   latency_s=f"{elapsed:.1f}",
                   raw_keys=list(result.raw.keys()) if result.raw else None)
        assert result.url
        assert result.url.startswith("https://")
        assert "." in result.url  # valid domain
        assert result.raw is not None
        assert isinstance(result.raw, dict)
        # Check for expected response structure
        if result.raw.get("data"):
            img_data = result.raw["data"][0]
            assert "url" in img_data or "b64_json" in img_data

    @skip_no_api_key
    def test_generate_non_blocking(self):
        from jarvisclaw import ImageClient
        image = make_client(ImageClient, "api_key")
        start = time.time()
        job = image.generate("A blue square", wait=False)
        elapsed = time.time() - start
        log_result("Image.generate non-blocking (APIKey)",
                   has_url=bool(job.url),
                   raw_status=job.raw.get("status") if job.raw else None,
                   raw_id=job.raw.get("id") if job.raw else None,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert job.raw


class TestImageClientX402:
    """ImageClient integration tests with x402 wallet auth."""

    @skip_no_wallet
    @pytest.mark.timeout(120)
    def test_generate_blocking(self):
        from jarvisclaw import ImageClient
        image = make_client(ImageClient, "x402")
        start = time.time()
        result = image.generate("A simple red circle", size="1024x1024")
        elapsed = time.time() - start
        log_result("Image.generate blocking (X402)",
                   url=result.url,
                   latency_s=f"{elapsed:.1f}")
        assert result.url
        assert result.url.startswith("https://")
        assert "." in result.url  # valid domain
        assert result.raw is not None
        assert isinstance(result.raw, dict)
        # Check for expected response structure
        if result.raw.get("data"):
            img_data = result.raw["data"][0]
            assert "url" in img_data or "b64_json" in img_data

    @skip_no_wallet
    def test_generate_non_blocking(self):
        from jarvisclaw import ImageClient
        image = make_client(ImageClient, "x402")
        start = time.time()
        job = image.generate("A yellow star", wait=False)
        elapsed = time.time() - start
        log_result("Image.generate non-blocking (X402)",
                   has_url=bool(job.url),
                   raw_status=job.raw.get("status") if job.raw else None,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert job.raw


# ─── VideoClient Tests ──────────────────────────────────────

class TestVideoClientAPIKey:
    """VideoClient integration tests with API key auth."""

    @skip_no_api_key
    @pytest.mark.timeout(600)
    def test_generate_blocking(self):
        from jarvisclaw import VideoClient
        video = make_client(VideoClient, "api_key")
        start = time.time()
        job = video.generate("A ball bouncing slowly", duration=5)
        elapsed = time.time() - start
        log_result("Video.generate blocking (APIKey)",
                   status=job.status,
                   url=job.url,
                   job_id=job.id,
                   latency_s=f"{elapsed:.1f}")
        assert job.status == "completed"
        assert job.url

    @skip_no_api_key
    def test_generate_non_blocking(self):
        from jarvisclaw import VideoClient
        video = make_client(VideoClient, "api_key")
        start = time.time()
        job = video.generate("A leaf falling", wait=False, duration=5)
        elapsed = time.time() - start
        log_result("Video.generate non-blocking (APIKey)",
                   job_id=job.id,
                   status=job.status,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert job.id is not None
        assert isinstance(job.id, str)
        assert len(job.id) > 0
        assert job.status in ("queued", "in_progress", "completed")
        assert job.raw is not None
        # If completed, check URL
        if job.status == "completed":
            assert job.url
            assert job.url.startswith("https://")


class TestVideoClientX402:
    """VideoClient integration tests with x402 wallet auth."""

    @skip_no_wallet
    @pytest.mark.timeout(600)
    def test_generate_blocking(self):
        from jarvisclaw import VideoClient
        video = make_client(VideoClient, "x402")
        start = time.time()
        job = video.generate("A simple wave", duration=5)
        elapsed = time.time() - start
        log_result("Video.generate blocking (X402)",
                   status=job.status,
                   url=job.url,
                   job_id=job.id,
                   latency_s=f"{elapsed:.1f}")
        assert job.status == "completed"
        assert job.url

    @skip_no_wallet
    def test_generate_non_blocking(self):
        from jarvisclaw import VideoClient
        video = make_client(VideoClient, "x402")
        start = time.time()
        job = video.generate("Clouds moving", wait=False, duration=5)
        elapsed = time.time() - start
        log_result("Video.generate non-blocking (X402)",
                   job_id=job.id,
                   status=job.status,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert job.id is not None
        assert isinstance(job.id, str)
        assert len(job.id) > 0
        assert job.status in ("queued", "in_progress", "completed")
        assert job.raw is not None
        # If completed, check URL
        if job.status == "completed":
            assert job.url
            assert job.url.startswith("https://")


# ─── AudioClient Tests ──────────────────────────────────────

class TestAudioClientAPIKey:
    """AudioClient integration tests with API key auth."""

    @skip_no_api_key
    def test_speech(self):
        from jarvisclaw import AudioClient
        audio = make_client(AudioClient, "api_key")
        start = time.time()
        result = audio.speech("Hello world, this is a test.", voice="alloy")
        elapsed = time.time() - start
        log_result("Audio.speech (APIKey)",
                   content_length=len(result.content),
                   content_type=result.content_type,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result.content is not None
        assert isinstance(result.content, bytes)
        assert len(result.content) > 1000  # at least 1KB for valid audio
        assert result.content_type is not None
        assert "audio" in result.content_type  # audio/mpeg, audio/mp3, etc.
        # Check it's actually audio (magic bytes)
        # MP3 starts with 0xFF 0xFB or ID3 tag
        assert result.content[:3] == b'ID3' or result.content[:2] == b'\xff\xfb' or result.content[:2] == b'\xff\xf3'

    @skip_no_api_key
    @pytest.mark.timeout(300)
    def test_music(self):
        from jarvisclaw import AudioClient
        audio = make_client(AudioClient, "api_key")
        start = time.time()
        result = audio.music("A simple drum beat, 120 bpm")
        elapsed = time.time() - start
        log_result("Audio.music (APIKey)",
                   content_length=len(result.content),
                   content_type=result.content_type,
                   latency_s=f"{elapsed:.1f}")
        assert result.content
        assert len(result.content) > 10000


class TestAudioClientX402:
    """AudioClient integration tests with x402 wallet auth."""

    @skip_no_wallet
    def test_speech(self):
        from jarvisclaw import AudioClient
        audio = make_client(AudioClient, "x402")
        start = time.time()
        result = audio.speech("Test audio output", voice="nova")
        elapsed = time.time() - start
        log_result("Audio.speech (X402)",
                   content_length=len(result.content),
                   content_type=result.content_type,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result.content is not None
        assert isinstance(result.content, bytes)
        assert len(result.content) > 1000  # at least 1KB for valid audio
        assert result.content_type is not None
        assert "audio" in result.content_type  # audio/mpeg, audio/mp3, etc.
        # Check it's actually audio (magic bytes)
        # MP3 starts with 0xFF 0xFB or ID3 tag
        assert result.content[:3] == b'ID3' or result.content[:2] == b'\xff\xfb' or result.content[:2] == b'\xff\xf3'

    @skip_no_wallet
    @pytest.mark.timeout(300)
    def test_music(self):
        from jarvisclaw import AudioClient
        audio = make_client(AudioClient, "x402")
        start = time.time()
        result = audio.music("A relaxing piano melody")
        elapsed = time.time() - start
        log_result("Audio.music (X402)",
                   content_length=len(result.content),
                   content_type=result.content_type,
                   latency_s=f"{elapsed:.1f}")
        assert result.content
        assert len(result.content) > 10000


# ─── SearchClient Tests ─────────────────────────────────────

class TestSearchClientAPIKey:
    """SearchClient integration tests with API key auth."""

    @skip_no_api_key
    def test_query(self):
        from jarvisclaw import SearchClient
        search = make_client(SearchClient, "api_key")
        start = time.time()
        results = search.query("Python programming language", num_results=3)
        elapsed = time.time() - start
        log_result("Search.query (APIKey)",
                   result_count=len(results),
                   first_title=results[0].title if results else None,
                   first_url=results[0].url if results else None,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert len(results) > 0


class TestSearchClientX402:
    """SearchClient integration tests with x402 wallet auth."""

    @skip_no_wallet
    def test_query(self):
        from jarvisclaw import SearchClient
        search = make_client(SearchClient, "x402")
        start = time.time()
        results = search.query("Bitcoin price today", num_results=3)
        elapsed = time.time() - start
        log_result("Search.query (X402)",
                   result_count=len(results),
                   first_title=results[0].title if results else None,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert len(results) > 0


# ─── Async Client Tests ─────────────────────────────────────

class TestAsyncChatClient:
    """Async ChatClient integration tests."""

    @skip_no_wallet
    def test_async_complete(self):
        async def _run():
            from jarvisclaw.aio import ChatClient
            async with ChatClient(private_key=WALLET_KEY) as chat:
                start = time.time()
                result = await chat.complete("Say 'async works'", model="auto")
                elapsed = time.time() - start
                log_result("AsyncChat.complete (X402)",
                           response=result,
                           latency_ms=f"{elapsed*1000:.0f}")
                assert len(result) > 0
        asyncio.run(_run())

    @skip_no_wallet
    def test_async_stream(self):
        async def _run():
            from jarvisclaw.aio import ChatClient
            async with ChatClient(private_key=WALLET_KEY) as chat:
                start = time.time()
                chunks = []
                async for chunk in chat.stream("Count to 3", model="auto"):
                    chunks.append(chunk)
                elapsed = time.time() - start
                full_text = "".join(chunks)
                log_result("AsyncChat.stream (X402)",
                           chunk_count=len(chunks),
                           full_response=full_text,
                           latency_ms=f"{elapsed*1000:.0f}")
                assert len(chunks) > 0
        asyncio.run(_run())

    @skip_no_wallet
    def test_async_concurrent(self):
        async def _run():
            from jarvisclaw.aio import ChatClient
            async with ChatClient(private_key=WALLET_KEY) as chat:
                start = time.time()
                results = await asyncio.gather(
                    chat.complete("Say 'one'", model="auto"),
                    chat.complete("Say 'two'", model="auto"),
                )
                elapsed = time.time() - start
                log_result("AsyncChat.concurrent (X402)",
                           result_count=len(results),
                           results=results,
                           latency_ms=f"{elapsed*1000:.0f}")
                assert len(results) == 2
                assert all(isinstance(r, str) for r in results)
        asyncio.run(_run())


class TestAsyncImageClient:
    """Async ImageClient integration tests."""

    @skip_no_wallet
    @pytest.mark.timeout(120)
    def test_async_generate(self):
        async def _run():
            from jarvisclaw.aio import ImageClient
            async with ImageClient(private_key=WALLET_KEY) as image:
                start = time.time()
                result = await image.generate("A red dot", size="1024x1024")
                elapsed = time.time() - start
                log_result("AsyncImage.generate (X402)",
                           url=result.url,
                           latency_s=f"{elapsed:.1f}")
                assert result.url
        asyncio.run(_run())


# ─── Balance & Utility Tests ────────────────────────────────

class TestUtility:
    """Utility method tests."""

    @skip_no_wallet
    def test_get_balance(self):
        from jarvisclaw import ChatClient
        chat = ChatClient(private_key=WALLET_KEY)
        start = time.time()
        balance = chat.get_balance()
        elapsed = time.time() - start
        log_result("Utility.get_balance (X402)",
                   balance_usd=f"${balance:.4f}",
                   latency_ms=f"{elapsed*1000:.0f}")
        assert isinstance(balance, float)
        assert balance >= 0

    @skip_no_wallet
    def test_wallet_address(self):
        from jarvisclaw import ChatClient
        chat = ChatClient(private_key=WALLET_KEY)
        log_result("Utility.wallet_address (X402)",
                   address=chat.address)
        assert chat.address
        assert chat.address.startswith("0x")
        assert len(chat.address) == 42

    @skip_no_api_key
    def test_get_balance_api_key(self):
        from jarvisclaw import ChatClient
        chat = ChatClient(api_key=API_KEY)
        start = time.time()
        balance = chat.get_balance()
        elapsed = time.time() - start
        log_result("Utility.get_balance (APIKey)",
                   balance_usd=f"${balance:.4f}",
                   latency_ms=f"{elapsed*1000:.0f}")
        assert isinstance(balance, float)
        assert balance >= 0


# ─── Error Handling Tests ───────────────────────────────────

class TestErrors:
    """Error handling tests."""

    def test_invalid_api_key(self):
        from jarvisclaw import ChatClient, AuthenticationError
        chat = ChatClient(api_key="sk-invalid-key-12345")
        start = time.time()
        with pytest.raises(AuthenticationError) as exc_info:
            chat.complete("Hello")
        elapsed = time.time() - start
        log_result("Error.invalid_api_key",
                   error_type=type(exc_info.value).__name__,
                   error_msg=str(exc_info.value)[:100],
                   latency_ms=f"{elapsed*1000:.0f}")

    def test_no_credentials(self):
        from jarvisclaw import ChatClient
        old_key = os.environ.pop("JARVISCLAW_API_KEY", None)
        old_pk = os.environ.pop("JARVISCLAW_WALLET_KEY", None)
        try:
            with pytest.raises(ValueError) as exc_info:
                ChatClient()
            log_result("Error.no_credentials",
                       error_type="ValueError",
                       error_msg=str(exc_info.value)[:100])
        finally:
            if old_key:
                os.environ["JARVISCLAW_API_KEY"] = old_key
            if old_pk:
                os.environ["JARVISCLAW_WALLET_KEY"] = old_pk


# ─── MarketplaceClient Tests ─────────────────────────────────

class TestMarketplaceClientAPIKey:
    """Marketplace integration tests with API key auth."""

    @skip_no_api_key
    def test_crypto_data(self):
        """Test Surf crypto data endpoint."""
        from jarvisclaw import MarketplaceClient
        mc = make_client(MarketplaceClient, "api_key")
        start = time.time()
        result = mc.call("surf", "/exchange/prices?symbol=BTC")
        elapsed = time.time() - start
        log_result("Marketplace.surf/exchange/prices (APIKey)",
                   result_type=type(result).__name__,
                   result_keys=list(result.keys()) if isinstance(result, dict) else None,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert isinstance(result, dict)

    @skip_no_api_key
    def test_financial_data(self):
        """Test financial data endpoint."""
        from jarvisclaw import MarketplaceClient
        mc = make_client(MarketplaceClient, "api_key")
        start = time.time()
        result = mc.call("data", "/crypto/price/BTC-USD")
        elapsed = time.time() - start
        log_result("Marketplace.data/crypto/price (APIKey)",
                   result=result,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None

    @skip_no_api_key
    def test_dex_price(self):
        """Test DEX price quote (free endpoint)."""
        from jarvisclaw import MarketplaceClient
        mc = make_client(MarketplaceClient, "api_key")
        start = time.time()
        # 0x API price endpoint — WETH → USDC on Base
        result = mc.call("dex", "/price?chainId=8453&sellToken=0x4200000000000000000000000000000000000006&buyToken=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913&sellAmount=1000000000000000000")
        elapsed = time.time() - start
        log_result("Marketplace.dex/price (APIKey)",
                   result_type=type(result).__name__,
                   result=str(result)[:200] if result else None,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None


class TestMarketplaceClientX402:
    """Marketplace integration tests with x402 wallet auth."""

    @skip_no_wallet
    def test_crypto_data(self):
        """Test Surf crypto data with x402."""
        from jarvisclaw import MarketplaceClient
        mc = make_client(MarketplaceClient, "x402")
        start = time.time()
        result = mc.call("surf", "/exchange/prices?symbol=ETH")
        elapsed = time.time() - start
        log_result("Marketplace.surf/exchange/prices (X402)",
                   result_type=type(result).__name__,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert isinstance(result, dict)

    @skip_no_wallet
    def test_search(self):
        """Test Exa search via marketplace."""
        from jarvisclaw import MarketplaceClient
        mc = make_client(MarketplaceClient, "x402")
        start = time.time()
        result = mc.call("exa", "/search", method="POST", json={
            "query": "latest AI news",
            "num_results": 3,
        })
        elapsed = time.time() - start
        log_result("Marketplace.exa/search (X402)",
                   result_type=type(result).__name__,
                   result_keys=list(result.keys()) if isinstance(result, dict) else None,
                   latency_ms=f"{elapsed*1000:.0f}")
        assert result is not None
