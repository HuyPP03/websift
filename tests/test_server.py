"""MCP server factory — import side-effect free."""

from __future__ import annotations

import pytest

import web_search.server as server_mod
from web_search.client import WebSearchClient
from web_search.server import ServerApp, create_server, main
from web_search.settings import AppSettings, ProviderSettings, ServerSettings


def test_import_has_no_runtime_globals():
    """Importing web_search.server must not create mcp/client or parse env."""
    assert not hasattr(server_mod, "_client")
    assert not hasattr(server_mod, "HOST")
    assert not hasattr(server_mod, "PORT")
    assert not hasattr(server_mod, "TRANSPORT")
    assert callable(server_mod.create_server)
    assert callable(server_mod.main)
    # No module-level FastMCP instance
    assert getattr(server_mod, "mcp", None) is None


def test_create_server_defaults_no_env(monkeypatch):
    monkeypatch.delenv("MCP_HOST", raising=False)
    monkeypatch.delenv("SEARCH_MAX_RESULTS", raising=False)
    app = create_server()
    assert isinstance(app, ServerApp)
    assert app.host == "127.0.0.1"
    assert app.port == 8787
    assert app.transport == "streamable-http"
    assert app.client.max_results == 5
    assert app.client.timeout == 30
    assert callable(app.web_search)
    assert callable(app.web_fetch)


def test_create_server_from_settings():
    settings = AppSettings(
        server=ServerSettings(host="0.0.0.0", port=9999, transport="stdio"),
        provider=ProviderSettings(name="ddgs", max_results=3, timeout_seconds=11),
    )
    app = create_server(settings)
    assert app.host == "0.0.0.0"
    assert app.port == 9999
    assert app.transport == "stdio"
    assert app.client.max_results == 3
    assert app.client.timeout == 11


def test_create_server_injects_client():
    client = WebSearchClient(max_results=1, timeout=2)
    app = create_server(AppSettings(), client=client)
    assert app.client is client


@pytest.mark.asyncio
async def test_web_search_tool_delegates(monkeypatch):
    app = create_server()
    monkeypatch.setattr(app.client, "search", lambda q: f"RESULTS:{q}")
    out = await app.web_search("hello")
    assert out == "RESULTS:hello"


@pytest.mark.asyncio
async def test_web_fetch_tool_delegates(monkeypatch):
    app = create_server()
    monkeypatch.setattr(app.client, "fetch", lambda u: f"PAGE:{u}")
    out = await app.web_fetch("https://example.com/")
    assert out == "PAGE:https://example.com/"


def test_main_loads_env_and_runs(monkeypatch):
    monkeypatch.setenv("MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_PORT", "8787")
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("SEARCH_MAX_RESULTS", "3")
    monkeypatch.setenv("SEARCH_TIMEOUT", "11")

    called: dict = {}

    def fake_run(self, transport=None):
        called["transport"] = transport or self.transport
        called["host"] = self.settings.server.host
        called["max_results"] = self.client.max_results
        called["timeout"] = self.client.timeout

    monkeypatch.setattr(ServerApp, "run", fake_run)
    main()
    assert called["transport"] == "stdio"
    assert called["host"] == "127.0.0.1"
    assert called["max_results"] == 3
    assert called["timeout"] == 11


def test_run_passes_transport(monkeypatch):
    app = create_server(
        AppSettings(server=ServerSettings(transport="stdio")),
    )
    seen: dict = {}

    def fake_mcp_run(transport=None):
        seen["transport"] = transport

    monkeypatch.setattr(app.mcp, "run", fake_mcp_run)
    app.run()
    assert seen["transport"] == "stdio"
