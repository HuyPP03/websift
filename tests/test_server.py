"""MCP server tool characterization (offline, mocked client)."""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def server_module(monkeypatch: pytest.MonkeyPatch):
    """Import server with controlled env; reload if needed."""
    monkeypatch.setenv("MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_PORT", "8787")
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("SEARCH_MAX_RESULTS", "3")
    monkeypatch.setenv("SEARCH_TIMEOUT", "11")

    for name in list(sys.modules):
        if name == "web_search.server" or name.startswith("web_search.server."):
            del sys.modules[name]

    import web_search.server as server

    server = importlib.reload(server)
    return server


def test_import_time_settings_from_env(server_module):
    """v0.1.0 characterization: settings are read at import time."""
    assert server_module.HOST == "127.0.0.1"
    assert server_module.PORT == 8787
    assert server_module.TRANSPORT == "stdio"
    assert server_module._client.max_results == 3
    assert server_module._client.timeout == 11


def test_tools_registered(server_module):
    assert callable(server_module.web_search)
    assert callable(server_module.web_fetch)
    assert callable(server_module.main)


@pytest.mark.asyncio
async def test_web_search_tool_delegates(server_module, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server_module._client, "search", lambda q: f"RESULTS:{q}")
    out = await server_module.web_search("hello")
    assert out == "RESULTS:hello"


@pytest.mark.asyncio
async def test_web_fetch_tool_delegates(server_module, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server_module._client, "fetch", lambda u: f"PAGE:{u}")
    out = await server_module.web_fetch("https://example.com/")
    assert out == "PAGE:https://example.com/"


@pytest.mark.asyncio
async def test_tools_use_to_thread(server_module, monkeypatch: pytest.MonkeyPatch):
    seen: list[str] = []

    def fake_search(q: str) -> str:
        seen.append(q)
        return "ok"

    monkeypatch.setattr(server_module._client, "search", fake_search)
    result = await server_module.web_search("q1")
    assert result == "ok"
    assert seen == ["q1"]


def test_main_invokes_mcp_run(server_module, monkeypatch: pytest.MonkeyPatch):
    called = {}

    def fake_run(transport=None):
        called["transport"] = transport

    monkeypatch.setattr(server_module.mcp, "run", fake_run)
    server_module.main()
    assert called["transport"] == server_module.TRANSPORT
