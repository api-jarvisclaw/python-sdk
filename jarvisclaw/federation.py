"""Deprecated module path for the federation→network rename (2026-08).

The gateway renamed its public surface from "federation" to "network": what used
to be a federation of peers is presented as one AIP network of APIs. The client
moved to ``jarvisclaw.network``; this module keeps the old import path working.

    from jarvisclaw.federation import FederationClient  # still works
    from jarvisclaw.network import NetworkClient        # preferred

Wire paths are unchanged — the gateway still serves /v1/federation/*, so this is
a naming change only. Slated for removal in 4.0.
"""
from __future__ import annotations

from .network import NetworkClient

# Deprecated: use NetworkClient.
FederationClient = NetworkClient

__all__ = ["FederationClient", "NetworkClient"]
