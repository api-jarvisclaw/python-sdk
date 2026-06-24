"""JarvisClaw AI SDK — Agent-Native AIP experience with intent routing, tools, and budget control.

Quickstart:
    from jarvisclaw import Agent
    agent = Agent()
    print(agent.ask("what is AIP?"))
"""
from .agent import Agent, BudgetExceededError, CostTracker
from .audio import AudioClient
from .chat import ChatClient
from .errors import (
    APIError,
    AuthenticationError,
    InsufficientBalanceError,
    JarvisClawError,
    PaymentError,
    RateLimitError,
)
from .image import ImageClient
from .intent import IntentClient
from .marketplace import MarketplaceClient
from .openai_compat import OpenAI
from .search import SearchClient
from .types import MusicJob
from .video import VideoClient
from .wallet import WalletClient

__all__ = [
    "Agent",
    "OpenAI",
    "CostTracker",
    "BudgetExceededError",
    "ChatClient",
    "VideoClient",
    "ImageClient",
    "AudioClient",
    "SearchClient",
    "MarketplaceClient",
    "WalletClient",
    "IntentClient",
    "MusicJob",
    "JarvisClawError",
    "APIError",
    "AuthenticationError",
    "RateLimitError",
    "InsufficientBalanceError",
    "PaymentError",
]
__version__ = "2.0.0"
