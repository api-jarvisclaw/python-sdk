"""Smoke tests for the Agent class (no network)."""
import os

import pytest

from jarvisclaw import Agent

_CRED_VARS = ("JARVISCLAW_API_KEY", "JARVISCLAW_WALLET_KEY")


@pytest.fixture
def no_ambient_credentials(monkeypatch):
    """Clear credential env vars for the duration of a test.

    Without this, running the suite on a machine that has a real key exported
    makes the no-credentials assertion fail: Agent() picks the key up from the
    environment and constructs successfully. The test is about the argument-less
    path, not about what happens to be in the shell.
    """
    for var in _CRED_VARS:
        monkeypatch.delenv(var, raising=False)


def test_agent_init_api_key():
    agent = Agent(api_key="sk-test")
    assert agent is not None


def test_agent_init_no_credentials(no_ambient_credentials):
    """Agent with no auth anywhere must fail loudly at construction."""
    with pytest.raises(ValueError, match="api_key or private_key"):
        Agent()


def test_agent_reads_env_credentials(monkeypatch):
    """The env-var fallback is a documented feature, so pin it."""
    for var in _CRED_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("JARVISCLAW_API_KEY", "sk-from-env")
    agent = Agent()
    assert agent is not None
    assert agent.address is None, "API key mode has no wallet address"


def test_agent_explicit_key_beats_env(monkeypatch):
    """An explicit api_key must win over the environment."""
    monkeypatch.setenv("JARVISCLAW_API_KEY", "sk-from-env")
    agent = Agent(api_key="sk-explicit")
    assert agent is not None
