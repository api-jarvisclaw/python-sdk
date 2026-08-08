"""JarvisClaw AI SDK — Unified AIP client with intent routing, streaming, and budget control.

Quickstart:
    from jarvisclaw import JarvisClaw

    client = JarvisClaw(private_key="0x...")
    result = client.execute("chat_completion", payload={"messages": [...]}, budget={"max_total_usd": 0.05})

Agent mode (autonomous with tools):
    from jarvisclaw import Agent
    agent = Agent(private_key="0x...")
    print(agent.ask("explain quantum computing"))
"""
from .unified import JarvisClaw
from .agent import Agent, BudgetExceededError, CostTracker
from .audio import AudioClient
from .chat import ChatClient
from .prompt_coach import PromptCoachClient
from .errors import (
    APIError,
    AuthenticationError,
    ConnectionError,
    InsufficientBalanceError,
    JarvisClawError,
    PaymentError,
    RateLimitError,
    TimeoutError,
)
from .embeddings import EmbeddingsClient
from .image import ImageClient
from .network import NetworkClient
# Deprecated: FederationClient is the pre-rename name for NetworkClient. Importable
# but kept out of __all__ on purpose -- __all__ is the recommended surface, and
# tests/test_dual_credentials.py requires every name there to have its own coverage.
from .network import NetworkClient as FederationClient  # noqa: F401
from .intent import IntentClient
from .marketplace import MarketplaceClient
from .openai_compat import OpenAI
from .search import SearchClient
from .types import MusicJob
from .uapi import UserAPIClient
from .video import VideoClient
from .wallet import WalletClient

__all__ = [
    "JarvisClaw",
    "Agent",
    "OpenAI",
    "CostTracker",
    "BudgetExceededError",
    "ChatClient",
    "VideoClient",
    "ImageClient",
    "AudioClient",
    "SearchClient",
    "EmbeddingsClient",
    "MarketplaceClient",
    "UserAPIClient",
    "WalletClient",
    "IntentClient",
    "NetworkClient",
    "PromptCoachClient",
    "MusicJob",
    "JarvisClawError",
    "APIError",
    "AuthenticationError",
    "RateLimitError",
    "InsufficientBalanceError",
    "PaymentError",
    "ConnectionError",
    "TimeoutError",
]
__version__ = "3.1.1"
