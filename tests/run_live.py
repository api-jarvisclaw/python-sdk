"""Live SDK test — exercises all client capabilities."""
import os
import sys
import time

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_KEY = os.environ.get("JARVISCLAW_API_KEY", "sk-OtqnrUGuNoROqKbJR9IlUFbQclLSH2vFWsvjMnR5744ZHMF0")
WALLET_KEY = os.environ.get("JARVISCLAW_WALLET_KEY", "7cZPrSVhfVX7Ny8XRcsnkjfDHZNW926oUajAUpFaVgi7ADABRqLX1wVyc5Wgn89EuUrPkJVtKYVVpks5ZUsgoyt")

PASS = 0
FAIL = 0


def test(name, fn):
    global PASS, FAIL
    print(f"\n{'─'*60}")
    print(f"  {name}")
    print(f"{'─'*60}")
    start = time.time()
    try:
        fn()
        elapsed = (time.time() - start) * 1000
        print(f"  [PASS] ({elapsed:.0f}ms)")
        PASS += 1
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"  [FAIL] ({elapsed:.0f}ms): {type(e).__name__}: {e}")
        FAIL += 1


# ═══════════════════════════════════════════════════════════════
# 1. Chat
# ═══════════════════════════════════════════════════════════════

def test_chat_apikey():
    from jarvisclaw import ChatClient
    chat = ChatClient(api_key=API_KEY)
    result = chat.complete("Say 'hello' and nothing else", model="auto")
    print(f"  Response: {result}")
    assert isinstance(result, str) and len(result) > 0


def test_chat_solana():
    from jarvisclaw import ChatClient
    chat = ChatClient(private_key=WALLET_KEY)
    print(f"  Wallet: {chat.address}")
    result = chat.complete("Say 'solana works' and nothing else", model="auto")
    print(f"  Response: {result}")
    assert isinstance(result, str) and len(result) > 0


def test_chat_stream():
    from jarvisclaw import ChatClient
    chat = ChatClient(api_key=API_KEY)
    chunks = list(chat.stream("Count 1 to 3", model="auto"))
    full = "".join(chunks)
    print(f"  Chunks: {len(chunks)}, Text: {full[:100]}")
    assert len(chunks) > 0


# ═══════════════════════════════════════════════════════════════
# 2. Balance
# ═══════════════════════════════════════════════════════════════

def test_balance_apikey():
    from jarvisclaw import ChatClient
    chat = ChatClient(api_key=API_KEY)
    balance = chat.get_balance()
    print(f"  Balance: ${balance:.4f}")
    assert isinstance(balance, (int, float)) and balance >= 0


def test_balance_solana():
    from jarvisclaw import ChatClient
    chat = ChatClient(private_key=WALLET_KEY)
    balance = chat.get_balance()
    print(f"  USDC Balance: ${balance:.6f}")
    assert isinstance(balance, float) and balance >= 0


# ═══════════════════════════════════════════════════════════════
# 3. Search
# ═══════════════════════════════════════════════════════════════

def test_search_apikey():
    from jarvisclaw import SearchClient
    search = SearchClient(api_key=API_KEY)
    results = search.query("Python programming", num_results=3)
    print(f"  Results: {len(results)}")
    if results:
        print(f"  First: {results[0].title[:60]} | {results[0].url[:60]}")
    assert len(results) > 0


def test_search_solana():
    from jarvisclaw import SearchClient
    search = SearchClient(private_key=WALLET_KEY)
    results = search.query("Bitcoin price", num_results=3)
    print(f"  Results: {len(results)}")
    assert len(results) > 0


# ═══════════════════════════════════════════════════════════════
# 4. Marketplace
# ═══════════════════════════════════════════════════════════════

def test_marketplace_surf():
    from jarvisclaw import MarketplaceClient
    mp = MarketplaceClient(api_key=API_KEY)
    result = mp.call("surf", "/exchange/price?pair=BTC-USDT")
    print(f"  Result type: {type(result).__name__}")
    print(f"  Keys: {list(result.keys())[:5] if isinstance(result, dict) else str(result)[:80]}")
    assert result is not None


def test_marketplace_rpc():
    from jarvisclaw import MarketplaceClient
    mp = MarketplaceClient(private_key=WALLET_KEY)
    result = mp.rpc_call("ethereum", "eth_blockNumber")
    block = int(result.get("result", "0x0"), 16)
    print(f"  Ethereum block: {block}")
    assert block > 0


# ═══════════════════════════════════════════════════════════════
# 5. Audio (TTS)
# ═══════════════════════════════════════════════════════════════

def test_speech():
    from jarvisclaw import AudioClient
    audio = AudioClient(api_key=API_KEY)
    result = audio.speech("Hello world", voice="sarah")
    print(f"  Content-Type: {result.content_type}")
    print(f"  Audio size: {len(result.content)} bytes")
    assert len(result.content) > 1000


# ═══════════════════════════════════════════════════════════════
# 6. Async
# ═══════════════════════════════════════════════════════════════

def test_async_chat():
    import asyncio
    from jarvisclaw.aio import ChatClient as AsyncChat

    async def run():
        async with AsyncChat(api_key=API_KEY) as chat:
            result = await chat.complete("Say 'async works'", model="auto")
            print(f"  Response: {result}")
            assert len(result) > 0

    asyncio.run(run())


def test_async_stream():
    import asyncio
    from jarvisclaw.aio import ChatClient as AsyncChat

    async def run():
        async with AsyncChat(api_key=API_KEY) as chat:
            chunks = []
            async for chunk in chat.stream("Say hello", model="auto"):
                chunks.append(chunk)
            full = "".join(chunks)
            print(f"  Chunks: {len(chunks)}, Text: {full[:80]}")
            assert len(chunks) > 0

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════
# Run all
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print(" JarvisClaw Python SDK v1.3.1 — Live Integration Test")
    print("=" * 60)

    test("1. Chat (API Key)", test_chat_apikey)
    test("2. Chat (Solana x402)", test_chat_solana)
    test("3. Chat Stream (API Key)", test_chat_stream)
    test("4. Balance (API Key)", test_balance_apikey)
    test("5. Balance (Solana on-chain)", test_balance_solana)
    test("6. Search (API Key)", test_search_apikey)
    test("7. Search (Solana x402)", test_search_solana)
    test("8. Marketplace Surf", test_marketplace_surf)
    test("9. Marketplace RPC (Solana x402)", test_marketplace_rpc)
    test("10. TTS Speech", test_speech)
    test("11. Async Chat", test_async_chat)
    test("12. Async Stream", test_async_stream)

    print("\n" + "=" * 60)
    print(f" Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)
