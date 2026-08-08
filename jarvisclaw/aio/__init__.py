"""jarvisclaw.aio — async (asyncio) versions of all JarvisClaw clients.

Usage:
    import asyncio
    from jarvisclaw.aio import ChatClient, ImageClient, VideoClient

    async def main():
        chat = ChatClient(api_key="sk-...")
        image = ImageClient(private_key="0x...")

        # Concurrent requests
        text, img = await asyncio.gather(
            chat.complete("Hello!"),
            image.generate("A cat on Mars"),
        )
        print(text)
        print(img.url)

    asyncio.run(main())

Requires: pip install jarvisclaw[async]  (installs httpx)
"""
from .client import AsyncChatClient as ChatClient
from .client import AsyncImageClient as ImageClient
from .client import AsyncVideoClient as VideoClient
from .client import AsyncAudioClient as AudioClient
from .client import AsyncSearchClient as SearchClient
from .client import AsyncMarketplaceClient as MarketplaceClient
from .client import AsyncWalletClient as WalletClient
from .client import AsyncIntentClient as IntentClient
from .network import AsyncNetworkClient as NetworkClient
# Deprecated: FederationClient is the pre-rename name for NetworkClient. Importable
# but kept out of __all__ on purpose -- __all__ is the recommended surface, and
# tests/test_dual_credentials.py requires every name there to have its own coverage.
from .network import AsyncNetworkClient as FederationClient  # noqa: F401

__all__ = [
    "ChatClient",
    "ImageClient",
    "VideoClient",
    "AudioClient",
    "SearchClient",
    "MarketplaceClient",
    "WalletClient",
    "IntentClient",
    "NetworkClient",
]
