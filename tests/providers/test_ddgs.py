"""DDGS provider adapter + WebSearchClient integration (mocked)."""

from __future__ import annotations

import sys
import types

import pytest

from web_search.client import WebSearchClient
from web_search.models import ErrorCategory, SearchRequest
from web_search.providers.ddgs import DdgsProvider, DdgsProviderConfig
from web_search.providers.errors import (
    ProviderImportError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


@pytest.fixture
def mock_ddgs(monkeypatch: pytest.MonkeyPatch):
    created = {}

    class FakeDDGS:
        def __init__(self, timeout=None):
            created["timeout"] = timeout

        def text(self, query, max_results=5):
            created["query"] = query
            created["max_results"] = max_results
            return [
                {
                    "title": "Python Docs",
                    "href": "https://docs.python.org/3/",
                    "body": "Official documentation",
                }
            ]

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)
    return created


def test_ddgs_receives_timeout_and_max_results(mock_ddgs):
    client = WebSearchClient(max_results=4, timeout=9)
    out = client.search("  python typing  ")
    assert mock_ddgs["timeout"] == 9
    assert mock_ddgs["max_results"] == 4
    assert mock_ddgs["query"] == "python typing"
    assert "Python Docs" in out
    assert "https://docs.python.org/3/" in out
    assert "Official documentation" in out


def test_ddgs_field_mapping_title_href_body(mock_ddgs):
    out = WebSearchClient().search("x")
    assert "Title: Python Docs" in out
    assert "URL: https://docs.python.org/3/" in out
    assert "Snippet: Official documentation" in out


def test_ddgs_provider_direct_mapping(mock_ddgs):
    provider = DdgsProvider(DdgsProviderConfig(timeout=11))
    results = provider.search(SearchRequest(query="q", max_results=3))
    assert mock_ddgs["timeout"] == 11
    assert mock_ddgs["max_results"] == 3
    assert len(results) == 1
    assert results[0].title == "Python Docs"
    assert results[0].url == "https://docs.python.org/3/"
    assert results[0].snippet == "Official documentation"
    assert results[0].rank == 1
    assert results[0].source == "ddgs"


def test_ddgs_provider_import_error(monkeypatch: pytest.MonkeyPatch):
    import builtins

    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "ddgs" or (isinstance(name, str) and name.startswith("ddgs.")):
            raise ImportError("no ddgs")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    # Ensure cached module does not short-circuit
    monkeypatch.delitem(sys.modules, "ddgs", raising=False)

    provider = DdgsProvider()
    with pytest.raises(ProviderImportError) as ei:
        provider.search(SearchRequest(query="q", max_results=5))
    assert "ddgs not installed" in ei.value.message

    out = WebSearchClient().search("python")
    assert "ddgs not installed" in out


def test_ddgs_provider_timeout_mapping(monkeypatch: pytest.MonkeyPatch):
    class FakeDDGS:
        def __init__(self, timeout=None):
            pass

        def text(self, query, max_results=5):
            raise TimeoutError("request timed out")

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)

    with pytest.raises(ProviderTimeoutError):
        DdgsProvider().search(SearchRequest(query="q", max_results=1))

    resp = WebSearchClient().search_structured("q")
    assert resp.error_category == ErrorCategory.TIMEOUT
    assert "Search failed:" in (resp.error_message or "")


def test_ddgs_provider_rate_limit_mapping(monkeypatch: pytest.MonkeyPatch):
    class FakeDDGS:
        def __init__(self, timeout=None):
            pass

        def text(self, query, max_results=5):
            raise RuntimeError("rate limit 429")

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)

    with pytest.raises(ProviderRateLimitError):
        DdgsProvider().search(SearchRequest(query="q", max_results=1))

    resp = WebSearchClient().search_structured("q")
    assert resp.error_category == ErrorCategory.RATE_LIMIT
    out = WebSearchClient().search("q")
    assert out.startswith("Search failed:")
    assert "rate" in out.lower() or "429" in out


def test_ddgs_provider_connection_mapping(monkeypatch: pytest.MonkeyPatch):
    class FakeDDGS:
        def __init__(self, timeout=None):
            pass

        def text(self, query, max_results=5):
            raise ConnectionError("connection refused")

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)

    with pytest.raises(ProviderUnavailableError):
        DdgsProvider().search(SearchRequest(query="q", max_results=1))

    resp = WebSearchClient().search_structured("q")
    assert resp.error_category == ErrorCategory.UNAVAILABLE


def test_ddgs_provider_empty_results(monkeypatch: pytest.MonkeyPatch):
    class FakeDDGS:
        def __init__(self, timeout=None):
            pass

        def text(self, query, max_results=5):
            return []

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)
    assert DdgsProvider().search(SearchRequest(query="q", max_results=5)) == []
    assert WebSearchClient().search("nothing") == "No results found."


def test_ddgs_provider_unsupported_filter_rejected():
    from web_search.providers.errors import ProviderConfigError

    provider = DdgsProvider()
    with pytest.raises(ProviderConfigError) as ei:
        provider.search(SearchRequest(query="q", max_results=5, region="us-en"))
    assert ei.value.code == "unsupported_filter"

    # Client maps ProviderConfigError to structured PROVIDER error
    class RegionProvider:
        name = "region-fake"
        capabilities = DdgsProvider.capabilities

        def search(self, request):
            return provider.search(
                SearchRequest(
                    query=request.query,
                    max_results=request.max_results,
                    region="us-en",
                )
            )

    resp = WebSearchClient(provider=RegionProvider()).search_structured("q")
    assert not resp.ok
    assert resp.error_category == ErrorCategory.PROVIDER
    assert "safe_search" not in (resp.error_message or "")
    assert "region" in (resp.error_message or "")


def test_injected_provider_used():
    class FakeProvider:
        name = "fake"
        capabilities = DdgsProvider.capabilities

        def search(self, request):
            from web_search.models import SearchResult

            return [
                SearchResult(
                    title="Injected",
                    url="https://injected.example/",
                    snippet="via injection",
                    rank=1,
                    source="fake",
                )
            ]

    out = WebSearchClient(provider=FakeProvider()).search("anything")
    assert "Injected" in out
    assert "https://injected.example/" in out


@pytest.mark.live
def test_live_ddgs_smoke():
    """Optional live smoke; excluded from default suite."""
    out = WebSearchClient(max_results=1, timeout=20).search("python")
    assert isinstance(out, str)
    assert out
    assert "No query" not in out
