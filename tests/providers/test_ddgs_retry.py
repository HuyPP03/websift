"""DDGS retry / friendlier error mapping (mocked)."""

from __future__ import annotations

import sys
import types

import pytest

from websift.models import SearchRequest
from websift.providers.ddgs import DdgsProvider, DdgsProviderConfig
from websift.providers.errors import ProviderRateLimitError, ProviderTimeoutError, ProviderUnavailableError


def test_ddgs_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps: list[float] = []

    class FakeDDGS:
        def __init__(self, timeout=None):
            pass

        def text(self, query, max_results=5):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("rate limit 429")
            return [
                {
                    "title": "OK",
                    "href": "https://example.com/",
                    "body": "done",
                }
            ]

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)
    monkeypatch.setattr("websift.providers.ddgs.time.sleep", lambda s: sleeps.append(s))

    provider = DdgsProvider(DdgsProviderConfig(timeout=5, retry_max=2, retry_backoff_seconds=0.1))
    results = provider.search(SearchRequest(query="q", max_results=1))
    assert calls["n"] == 2
    assert sleeps  # backoff applied before success
    assert results[0].title == "OK"


def test_ddgs_retry_exhausted_raises_rate_limit(monkeypatch):
    class FakeDDGS:
        def __init__(self, timeout=None):
            pass

        def text(self, query, max_results=5):
            raise RuntimeError("rate limit 429")

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)
    monkeypatch.setattr("websift.providers.ddgs.time.sleep", lambda s: None)

    provider = DdgsProvider(DdgsProviderConfig(retry_max=1, retry_backoff_seconds=0.01))
    with pytest.raises(ProviderRateLimitError) as ei:
        provider.search(SearchRequest(query="q", max_results=1))
    assert "rate-limited" in ei.value.message.lower() or "blocked" in ei.value.message.lower()


def test_ddgs_timeout_message_is_friendly(monkeypatch):
    class FakeDDGS:
        def __init__(self, timeout=None):
            pass

        def text(self, query, max_results=5):
            raise TimeoutError("request timed out")

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)
    monkeypatch.setattr("websift.providers.ddgs.time.sleep", lambda s: None)

    with pytest.raises(ProviderTimeoutError) as ei:
        DdgsProvider(DdgsProviderConfig(retry_max=0)).search(SearchRequest(query="q", max_results=1))
    assert "timed out" in ei.value.message.lower()


def test_ddgs_connection_message_is_friendly(monkeypatch):
    class FakeDDGS:
        def __init__(self, timeout=None):
            pass

        def text(self, query, max_results=5):
            raise ConnectionError("connection refused")

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)
    monkeypatch.setattr("websift.providers.ddgs.time.sleep", lambda s: None)

    with pytest.raises(ProviderUnavailableError) as ei:
        DdgsProvider(DdgsProviderConfig(retry_max=0)).search(SearchRequest(query="q", max_results=1))
    assert "could not reach" in ei.value.message.lower() or "duckduckgo" in ei.value.message.lower()


def test_settings_wire_ddgs_retry_into_client(monkeypatch):
    from websift.client import WebSearchClient
    from websift.settings import AppSettings, ProviderSettings

    seen = {}

    class CaptureProvider:
        name = "ddgs"

        def __init__(self, config=None, **kwargs):
            seen["config"] = config

        def search(self, request):
            return []

        def fetch(self, url):
            from websift.models import FetchResult

            return FetchResult.success(url, "x", final_url=url)

    monkeypatch.setattr("websift.providers.registry.DdgsProvider", CaptureProvider)
    # Also patch where create_provider factory closes over — use create_provider path via settings
    monkeypatch.setattr("websift.client.create_provider", lambda name, config=None, **kw: CaptureProvider(config))

    settings = AppSettings(
        provider=ProviderSettings(name="ddgs", retry_max=3, retry_backoff_seconds=1.25, timeout_seconds=9)
    )
    client = WebSearchClient(settings=settings, provider="ddgs")
    assert seen["config"].retry_max == 3
    assert seen["config"].retry_backoff_seconds == 1.25
    assert seen["config"].timeout == 9
    assert client.max_results == 5
