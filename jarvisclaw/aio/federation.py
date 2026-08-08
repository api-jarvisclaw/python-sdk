"""Deprecated module path for the federation→network rename (2026-08).

See ``jarvisclaw.federation`` for the rationale. The async client moved to
``jarvisclaw.aio.network``; this module keeps the old import path working and is
slated for removal in 4.0.
"""
from __future__ import annotations

from .network import AsyncNetworkClient

# Deprecated: use AsyncNetworkClient.
AsyncFederationClient = AsyncNetworkClient

__all__ = ["AsyncFederationClient", "AsyncNetworkClient"]
