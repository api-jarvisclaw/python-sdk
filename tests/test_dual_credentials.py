"""Every client must accept either credential, on either rail.

The two supported modes are an API key (managed billing) and a wallet private key (x402
on-chain settlement), and a wallet key may be EVM (hex, Base) or Solana (base58). This
holds structurally because every client subclasses BaseClient, which owns the auth
strategy — the test exists so that a client which stops doing that, and therefore
silently supports only one credential, fails here rather than in someone's agent.

Pinned on the Python side too because the Go SDK accepted only EVM keys until recently:
the two SDKs disagreed about what "wallet mode" meant, and nothing in either test suite
would have caught the divergence.
"""
from __future__ import annotations

import base58
import pytest

import jarvisclaw

# Deterministic throwaway keys. Neither holds anything; the tests only need keys that
# parse and produce an address.
EVM_KEY = "0x4c0883a69102937d6231471b5dbb6204fe512961708279f2e3f1a1a1f1f1f1f1"
SOLANA_KEY = base58.b58encode(bytes(range(1, 33))).decode()

# Constructed with the same keyword arguments, so they can be exercised uniformly.
CLIENT_NAMES = [
    "JarvisClaw",
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
    "FederationClient",
    "PromptCoachClient",
]


def _address(client):
    """Read the wallet address, which JarvisClaw exposes under a second name."""
    addr = getattr(client, "address", None)
    return addr


@pytest.mark.parametrize("name", CLIENT_NAMES)
def test_client_accepts_an_api_key(name):
    client = getattr(jarvisclaw, name)(api_key="sk-test")
    assert _address(client) is None, "API-key mode has no wallet address"


@pytest.mark.parametrize("name", CLIENT_NAMES)
def test_client_accepts_an_evm_wallet_key(name):
    client = getattr(jarvisclaw, name)(private_key=EVM_KEY)
    addr = _address(client)
    assert addr and addr.startswith("0x"), f"{name} did not derive an EVM address: {addr!r}"


@pytest.mark.parametrize("name", CLIENT_NAMES)
def test_client_accepts_a_solana_wallet_key(name):
    client = getattr(jarvisclaw, name)(private_key=SOLANA_KEY)
    addr = _address(client)
    assert addr, f"{name} did not derive a Solana address"
    assert not addr.startswith("0x"), f"a Solana address must not be hex: {addr!r}"
    # base58, 32-byte pubkey.
    assert len(base58.b58decode(addr)) == 32


@pytest.mark.parametrize("name", CLIENT_NAMES)
def test_client_requires_some_credential(name):
    # Neither key and no env var: fail at construction with a message naming both
    # options, rather than at the first request with a 401.
    with pytest.raises(ValueError, match="api_key|private_key"):
        getattr(jarvisclaw, name)()


def test_every_exported_client_is_covered():
    """A new client must be added to CLIENT_NAMES, or this test is a lie."""
    exported = {
        n for n in jarvisclaw.__all__
        if n.endswith("Client") or n in ("JarvisClaw",)
    }
    # Agent is excluded on purpose: it composes clients rather than subclassing
    # BaseClient, and takes its own constructor arguments.
    missing = exported - set(CLIENT_NAMES)
    assert not missing, f"exported clients not covered by the dual-credential test: {sorted(missing)}"


def test_wallet_address_alias_agrees_with_address():
    """JarvisClaw exposes the same value under wallet_address; a divergence would mean
    one of them re-derived the key."""
    jc = jarvisclaw.JarvisClaw(private_key=SOLANA_KEY)
    assert jc.wallet_address == jc.address


def test_env_credentials_are_detected(monkeypatch):
    # The env path must get the same detection as an explicit argument, since that is how
    # an agent in a container is configured.
    monkeypatch.delenv("JARVISCLAW_API_KEY", raising=False)
    monkeypatch.setenv("JARVISCLAW_WALLET_KEY", SOLANA_KEY)
    client = jarvisclaw.ChatClient()
    assert client.address and not client.address.startswith("0x")

    monkeypatch.delenv("JARVISCLAW_WALLET_KEY", raising=False)
    monkeypatch.setenv("JARVISCLAW_API_KEY", "sk-env")
    assert jarvisclaw.ChatClient().address is None
