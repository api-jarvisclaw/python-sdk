"""Import and surface checks.

The public API is what users pin against, so every name in __all__ must actually
import and every documented method must exist. The README once advertised six
methods on JarvisClaw that were never implemented; test_readme_methods_exist
below is what stops that recurring.
"""
import os

import pytest


def test_imports():
    import jarvisclaw

    for name in jarvisclaw.__all__:
        assert hasattr(jarvisclaw, name), f"{name} is in __all__ but not importable"


def test_base_client_init():
    from jarvisclaw import ChatClient

    os.environ["JARVISCLAW_API_KEY"] = "sk-test"
    try:
        client = ChatClient()
        assert client is not None
        assert client.address is None, "API key mode has no wallet address"
    finally:
        del os.environ["JARVISCLAW_API_KEY"]


def test_client_requires_credentials():
    from jarvisclaw import ChatClient

    saved = {k: os.environ.pop(k, None) for k in ("JARVISCLAW_API_KEY", "JARVISCLAW_WALLET_KEY")}
    try:
        with pytest.raises(ValueError, match="api_key or private_key"):
            ChatClient()
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_readme_methods_exist():
    """Every JarvisClaw method the README shows must be real."""
    from jarvisclaw import JarvisClaw

    documented = [
        "resolve", "execute", "execute_budget", "stream", "subscribe",
        "audit", "audit_log", "budget_status", "spend", "model_breakdown",
        "daily_trend", "discover", "discover_peers", "crawl_network",
        "search_federation", "federation_execute", "resolve_natural",
        "network_stats", "balance", "get_balance",
        # The discovery-to-invocation path on the unified client. search_federation
        # and federation_execute existed, with nothing between them: the first hands
        # back a resource_id and the second wants a hand-built body naming it.
        "list_apis", "call_resource", "invoke_resource",
    ]
    missing = [n for n in documented if not hasattr(JarvisClaw, n)]
    assert not missing, f"documented but missing: {missing}"


def test_no_dead_endpoint_methods():
    """Methods that pointed at deleted routes must stay deleted."""
    import inspect

    from jarvisclaw import IntentClient, PromptCoachClient

    # /v1/aip/analytics/* was consolidated into /api/analytics/aggregate.
    for name in ("cost_summary", "cost_trend", "roi"):
        assert not hasattr(IntentClient, name), f"IntentClient.{name} hits a removed route"

    # /v1/prompt-coach/score never existed; score() now derives from optimize().
    # Check for a request to it, not a mention: the docstring names the path to
    # explain why it is absent.
    src = inspect.getsource(PromptCoachClient)
    assert '"/v1/prompt-coach/score"' not in src
    assert "'/v1/prompt-coach/score'" not in src


def test_async_clients_import():
    pytest.importorskip("httpx")
    from jarvisclaw import aio

    for name in aio.__all__:
        assert hasattr(aio, name), f"{name} is in aio.__all__ but not importable"


def test_version_matches_pyproject():
    """pyproject.toml and __version__ must agree.

    They drifted once: 3.1.0 was set in __init__.py but not pyproject.toml, so
    the release workflow built a 3.0.1 wheel and PyPI rejected it as a duplicate
    version. The tag was already pushed by then, which is the expensive part —
    nothing before the upload attempt noticed.
    """
    import re
    import sys
    from pathlib import Path

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import pytest

        tomllib = pytest.importorskip("tomli", reason="needs tomllib or tomli")

    root = Path(__file__).resolve().parent.parent
    pyproject_version = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]

    init_src = (root / "jarvisclaw" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init_src)
    assert match, "__version__ not found in jarvisclaw/__init__.py"

    assert match.group(1) == pyproject_version, (
        f"__version__ is {match.group(1)} but pyproject.toml says "
        f"{pyproject_version}; the built wheel would carry the pyproject value"
    )

    import jarvisclaw

    assert jarvisclaw.__version__ == pyproject_version
