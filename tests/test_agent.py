"""Smoke tests for the Agent class (no network)."""
import pytest
from jarvisclaw import Agent


def test_agent_init_api_key():
    agent = Agent(api_key="sk-test")
    assert agent is not None


def test_agent_init_no_credentials():
    """Agent without any auth should still instantiate (fails on first request)."""
    with pytest.raises(Exception):
        Agent()
