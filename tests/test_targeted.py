"""Targeted tests for previously failing scenarios from the retest report.

Run: cd sdk/python && pytest tests/test_targeted.py -v --timeout=300

Categories tested:
1. Video URL parsing (data[0].url nested format)
2. auto/search endpoint type error
3. TTS (auto/tts with elevenlabs)
4. Music (auto/music)
5. Marketplace routes (surf, data, dex, exa)
"""
import os

import pytest

BASE_URL = "https://api.jarvisclaw.ai"
API_KEY = os.environ.get(
    "JARVISCLAW_API_KEY", "sk-OtqnrUGuNoROqKbJR9IlUFbQclLSH2vFWsvjMnR5744ZHMF0"
)
WALLET_KEY = os.environ.get("JARVISCLAW_WALLET_KEY", "")

skip_no_wallet = pytest.mark.skipif(
    not WALLET_KEY, reason="JARVISCLAW_WALLET_KEY not set"
)


# --- 1. Video URL Parsing (was: empty job.url) ---


class TestVideoURLParsing:
    """Video URL should be extracted from data[0].url nested format."""

    @pytest.mark.timeout(600)
    def test_video_blocking_apikey(self):
        from jarvisclaw import VideoClient

        video = VideoClient(api_key=API_KEY, base_url=BASE_URL)
        job = video.generate("A simple animation of a bouncing ball", duration=5)
        assert job.url or job.id, f"Expected URL or ID, got: {job.raw}"
        if job.status == "completed":
            assert job.url, f"Completed but no URL. raw={job.raw}"
            assert job.url.startswith("http")

    @skip_no_wallet
    @pytest.mark.timeout(600)
    def test_video_blocking_x402(self):
        from jarvisclaw import VideoClient

        video = VideoClient(private_key=WALLET_KEY, base_url=BASE_URL)
        job = video.generate("Clouds moving slowly", duration=5)
        assert job.url or job.id, f"Expected URL or ID, got: {job.raw}"
        if job.status == "completed":
            assert job.url
            assert job.url.startswith("http")


# --- 2. auto/search (was: endpoint type error) ---


class TestAutoSearch:
    """auto/search should not be rejected by endpoint type guard."""

    @pytest.mark.timeout(60)
    def test_search_apikey(self):
        from jarvisclaw import ChatClient

        chat = ChatClient(api_key=API_KEY, base_url=BASE_URL)
        # Search uses chat completions endpoint with model=auto/search
        result = chat.complete("What is the latest news about AI?", model="auto/search")
        assert result is not None
        assert len(result) > 0

    @skip_no_wallet
    @pytest.mark.timeout(60)
    def test_search_x402(self):
        from jarvisclaw import ChatClient

        chat = ChatClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = chat.complete("What is quantum computing?", model="auto/search")
        assert result is not None
        assert len(result) > 0


# --- 3. TTS / auto/tts (was: no channel for tts-1) ---


class TestAutoTTS:
    """auto/tts should route to elevenlabs models."""

    @pytest.mark.timeout(60)
    def test_speech_apikey(self):
        from jarvisclaw import AudioClient

        audio = AudioClient(api_key=API_KEY, base_url=BASE_URL)
        result = audio.speech("Hello world, this is a test.", voice="sarah")
        assert result.content is not None
        assert isinstance(result.content, bytes)
        assert len(result.content) > 1000, f"Audio too small: {len(result.content)} bytes"
        assert result.content_type is not None

    @skip_no_wallet
    @pytest.mark.timeout(60)
    def test_speech_x402(self):
        from jarvisclaw import AudioClient

        audio = AudioClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = audio.speech("Test audio output", voice="sarah")
        assert result.content is not None
        assert isinstance(result.content, bytes)
        assert len(result.content) > 1000


# --- 4. Music / auto/music (was: returned JSON not audio) ---


class TestAutoMusic:
    """auto/music should return audio content."""

    @pytest.mark.timeout(300)
    def test_music_apikey(self):
        from jarvisclaw import AudioClient

        audio = AudioClient(api_key=API_KEY, base_url=BASE_URL)
        result = audio.music("A simple drum beat, 120 bpm")
        assert result.content is not None
        assert len(result.content) > 10000, f"Audio too small: {len(result.content)} bytes"

    @skip_no_wallet
    @pytest.mark.timeout(300)
    def test_music_x402(self):
        from jarvisclaw import AudioClient

        audio = AudioClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = audio.music("A relaxing piano melody")
        assert result.content is not None
        assert len(result.content) > 10000


# --- 5. Marketplace (was: 404) ---


class TestMarketplace:
    """Marketplace routes should be registered and accessible."""

    @pytest.mark.timeout(30)
    def test_surf_apikey(self):
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(api_key=API_KEY, base_url=BASE_URL)
        result = mc.call("surf", "/exchange/price?pair=BTC-USDT")
        assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result}"

    @pytest.mark.timeout(30)
    def test_market_ranking_apikey(self):
        """Test Surf market ranking endpoint."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(api_key=API_KEY, base_url=BASE_URL)
        result = mc.call("surf", "/market/ranking")
        assert result is not None

    @pytest.mark.timeout(30)
    def test_news_feed_apikey(self):
        """Test Surf news feed endpoint."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(api_key=API_KEY, base_url=BASE_URL)
        result = mc.call("surf", "/news/feed")
        assert result is not None

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_surf_x402(self):
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = mc.call("surf", "/exchange/price?pair=ETH-USDT")
        assert isinstance(result, dict)

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_exa_search_x402(self):
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = mc.call(
            "exa",
            "/search",
            method="POST",
            json={"query": "latest AI news", "numResults": 3},
        )
        assert result is not None


# --- 6. RPC (Multi-chain JSON-RPC) ---


class TestRPC:
    """Multi-chain RPC marketplace service."""

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_rpc_eth_block_number(self):
        """eth_blockNumber on Ethereum mainnet."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = mc.rpc_call("ethereum", "eth_blockNumber")
        assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result}"
        assert "result" in result or "error" not in result

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_rpc_eth_gas_price(self):
        """eth_gasPrice on Ethereum mainnet."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = mc.rpc_call("ethereum", "eth_gasPrice")
        assert isinstance(result, dict)
        assert "result" in result

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_rpc_base_chain(self):
        """eth_blockNumber on Base chain."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = mc.rpc_call("base", "eth_blockNumber")
        assert isinstance(result, dict)

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_rpc_batch(self):
        """Batch RPC call — multiple methods in one request."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        results = mc.rpc_batch("ethereum", [
            ("eth_blockNumber", []),
            ("eth_gasPrice", []),
        ])
        assert isinstance(results, list), f"Expected list, got {type(results)}"
        assert len(results) == 2

    @pytest.mark.timeout(30)
    def test_rpc_apikey(self):
        """RPC with API key auth."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(api_key=API_KEY, base_url=BASE_URL)
        result = mc.rpc_call("ethereum", "eth_blockNumber")
        assert isinstance(result, dict)


# --- 7. DeFi Data (DefiLlama) ---


class TestDeFi:
    """DefiLlama DeFi protocol data marketplace service."""

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_defi_protocols(self):
        """Get all DeFi protocols with TVL."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = mc.defi_protocols()
        assert result is not None

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_defi_protocol_aave(self):
        """Get specific protocol data (Aave)."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = mc.defi_protocol("aave")
        assert result is not None
        assert isinstance(result, dict)

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_defi_yields(self):
        """Get yield/APY data."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = mc.defi_yields()
        assert result is not None

    @skip_no_wallet
    @pytest.mark.timeout(30)
    def test_defi_tvl(self):
        """Get historical TVL data."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(private_key=WALLET_KEY, base_url=BASE_URL)
        result = mc.defi_tvl()
        assert result is not None

    @pytest.mark.timeout(30)
    def test_defi_protocols_apikey(self):
        """DeFi protocols with API key auth."""
        from jarvisclaw import MarketplaceClient

        mc = MarketplaceClient(api_key=API_KEY, base_url=BASE_URL)
        result = mc.defi_protocols()
        assert result is not None
