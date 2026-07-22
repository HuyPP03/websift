"""MCP server factory — import side-effect free + bounded concurrency."""

from __future__ import annotations

import asyncio
import threading
import time
import warnings

import pytest

import web_search.server as server_mod
from web_search.client import WebSearchClient
from web_search.concurrency import WorkLimits
from web_search.http import extract_pdf_text
from web_search.server import ServerApp, create_server, is_loopback_bind, main, warn_if_public_bind
from web_search.settings import AppSettings, ConcurrencySettings, ProviderSettings, ServerSettings


def test_import_has_no_runtime_globals():
    """Importing web_search.server must not create mcp/client or parse env."""
    assert not hasattr(server_mod, "_client")
    assert not hasattr(server_mod, "HOST")
    assert not hasattr(server_mod, "PORT")
    assert not hasattr(server_mod, "TRANSPORT")
    assert callable(server_mod.create_server)
    assert callable(server_mod.main)
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
    assert app.limits.search_max == 8
    assert app.limits.fetch_max == 16
    assert app.limits.pdf_max == 2
    assert callable(app.web_search)
    assert callable(app.web_fetch)


def test_create_server_from_settings():
    settings = AppSettings(
        server=ServerSettings(host="0.0.0.0", port=9999, transport="stdio"),
        provider=ProviderSettings(name="ddgs", max_results=3, timeout_seconds=11),
        concurrency=ConcurrencySettings(search_max=2, fetch_max=3, pdf_max=1),
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        app = create_server(settings)
    assert any(issubclass(x.category, UserWarning) for x in w)
    assert app.host == "0.0.0.0"
    assert app.port == 9999
    assert app.transport == "stdio"
    assert app.client.max_results == 3
    assert app.client.timeout == 11
    assert app.limits.search_max == 2
    assert app.limits.fetch_max == 3
    assert app.limits.pdf_max == 1
    assert app.client._pdf_semaphore is app.limits.pdf_semaphore


def test_create_server_injects_client():
    client = WebSearchClient(max_results=1, timeout=2)
    app = create_server(AppSettings(), client=client)
    assert app.client is client
    assert client._pdf_semaphore is app.limits.pdf_semaphore


def test_loopback_bind_helpers():
    assert is_loopback_bind("127.0.0.1")
    assert is_loopback_bind("localhost")
    assert is_loopback_bind("::1")
    assert not is_loopback_bind("0.0.0.0")
    assert not is_loopback_bind("192.168.1.1")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        warn_if_public_bind("127.0.0.1")
        assert w == []
        warn_if_public_bind("0.0.0.0")
        assert len(w) == 1


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


@pytest.mark.asyncio
async def test_search_concurrency_bounded(monkeypatch):
    settings = AppSettings(concurrency=ConcurrencySettings(search_max=2, fetch_max=8, pdf_max=1))
    app = create_server(settings, warn_public_bind=False)

    active = 0
    peak = 0
    lock = threading.Lock()
    release = threading.Event()

    def blocking_search(q: str) -> str:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        assert release.wait(timeout=3), "search workers stuck"
        with lock:
            active -= 1
        return f"ok:{q}"

    monkeypatch.setattr(app.client, "search", blocking_search)

    tasks = [asyncio.create_task(app.web_search(f"q{i}")) for i in range(5)]
    # Allow workers to start and hit the semaphore
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with lock:
            if peak >= 2 and active == 2:
                break
        await asyncio.sleep(0.01)
    with lock:
        assert peak <= 2
        assert active == 2
    release.set()
    results = await asyncio.gather(*tasks)
    assert len(results) == 5
    assert peak == 2


@pytest.mark.asyncio
async def test_fetch_concurrency_bounded(monkeypatch):
    settings = AppSettings(concurrency=ConcurrencySettings(search_max=8, fetch_max=2, pdf_max=1))
    app = create_server(settings, warn_public_bind=False)

    active = 0
    peak = 0
    lock = threading.Lock()
    release = threading.Event()

    def blocking_fetch(u: str) -> str:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        assert release.wait(timeout=3), "fetch workers stuck"
        with lock:
            active -= 1
        return f"page:{u}"

    monkeypatch.setattr(app.client, "fetch", blocking_fetch)

    tasks = [asyncio.create_task(app.web_fetch(f"https://example.com/{i}")) for i in range(5)]
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with lock:
            if peak >= 2 and active == 2:
                break
        await asyncio.sleep(0.01)
    with lock:
        assert peak <= 2
        assert active == 2
    release.set()
    await asyncio.gather(*tasks)
    assert peak == 2


def test_pdf_semaphore_bounds_extract():
    limits = WorkLimits.from_settings(ConcurrencySettings(pdf_max=1))
    active = 0
    peak = 0
    lock = threading.Lock()
    release = threading.Event()

    import web_search.http as http_mod

    def slow_extract(raw, *, max_pages=50, max_chars=32000):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        assert release.wait(timeout=3)
        with lock:
            active -= 1
        return "pdf-text"

    original = http_mod._extract_pdf_text_unlocked
    http_mod._extract_pdf_text_unlocked = slow_extract  # type: ignore[assignment]
    try:

        def worker():
            return extract_pdf_text(b"%PDF", pdf_semaphore=limits.pdf_semaphore)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        time.sleep(0.15)
        with lock:
            assert active == 1
            assert peak == 1
        release.set()
        t1.join(timeout=3)
        t2.join(timeout=3)
        assert peak == 1
    finally:
        http_mod._extract_pdf_text_unlocked = original  # type: ignore[assignment]


def test_main_loads_env_and_runs(monkeypatch):
    monkeypatch.setenv("MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_PORT", "8787")
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("SEARCH_MAX_RESULTS", "3")
    monkeypatch.setenv("SEARCH_TIMEOUT", "11")
    monkeypatch.setenv("SEARCH_MAX_CONCURRENCY", "2")
    monkeypatch.setenv("FETCH_MAX_CONCURRENCY", "4")

    called: dict = {}

    def fake_run(self, transport=None):
        called["transport"] = transport or self.transport
        called["host"] = self.settings.server.host
        called["max_results"] = self.client.max_results
        called["timeout"] = self.client.timeout
        called["search_max"] = self.limits.search_max
        called["fetch_max"] = self.limits.fetch_max

    monkeypatch.setattr(ServerApp, "run", fake_run)
    main()
    assert called["transport"] == "stdio"
    assert called["host"] == "127.0.0.1"
    assert called["max_results"] == 3
    assert called["timeout"] == 11
    assert called["search_max"] == 2
    assert called["fetch_max"] == 4


def test_run_passes_transport(monkeypatch):
    app = create_server(
        AppSettings(server=ServerSettings(transport="stdio")),
        warn_public_bind=False,
    )
    seen: dict = {}

    def fake_mcp_run(transport=None):
        seen["transport"] = transport

    monkeypatch.setattr(app.mcp, "run", fake_mcp_run)
    app.run()
    assert seen["transport"] == "stdio"


def test_tool_docstrings_have_no_secret_params():
    """Tool schemas/docs must not mention provider credentials."""
    app = create_server(warn_public_bind=False)
    for name in ("web_search", "web_fetch"):
        fn = getattr(app, name)
        doc = (fn.__doc__ or "").lower()
        assert "api key" not in doc
        assert "authorization" not in doc
        assert "provider" not in doc or name == "web_search"  # search may say duckduckgo
