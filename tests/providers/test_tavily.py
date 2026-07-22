"""Tavily provider adapter tests (mocked HTTP)."""

from __future__ import annotations

import pytest

from web_search.client import WebSearchClient
from web_search.models import SearchRequest
from web_search.providers.errors import ProviderAuthError, ProviderConfigError, ProviderRateLimitError
from web_search.providers.registry import create_provider
from web_search.providers.tavily import TavilyProvider, TavilyProviderConfig
from web_search.settings import AppSettings, ProviderEndpoint, ProviderSettings


class _FakeHttp:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[dict] = []
        self.base_url = "https://api.tavily.com"
        self._headers = {"Authorization": "Bearer tavily-secret"}

    def post_json(self, path="", *, params=None, json_body=None, extra_headers=None, provider=None):
        self.calls.append({"path": path, "body": dict(json_body or {}), "provider": provider})
        if self.error is not None:
            raise self.error
        if not self.responses:
            return {"results": []}
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_tavily_missing_api_key():
    with pytest.raises(ProviderConfigError) as ei:
        TavilyProvider(TavilyProviderConfig(api_key=""))
    assert ei.value.code == "missing_api_key"


def test_tavily_create_provider_requires_config():
    with pytest.raises(ProviderConfigError) as ei:
        create_provider("tavily", None)
    assert ei.value.code == "missing_config"


def test_tavily_maps_results_and_params():
    payload = {
        "results": [
            {"title": "T1", "url": "https://t1.example", "content": "c1"},
            {"title": "T2", "url": "https://t2.example", "content": "c2"},
        ]
    }
    http = _FakeHttp(responses=[payload])
    provider = TavilyProvider(TavilyProviderConfig(api_key="k"), http=http)
    results = provider.search(
        SearchRequest(query="llm", max_results=1, safe_search="strict", region="US", time_range="week")
    )
    assert len(results) == 1
    assert results[0].title == "T1"
    assert results[0].url == "https://t1.example"
    assert results[0].snippet == "c1"
    assert results[0].source == "tavily"
    call = http.calls[0]
    assert call["path"] == "/search"
    assert call["body"]["query"] == "llm"
    assert call["body"]["max_results"] == 1
    assert call["body"]["safe_search"] is True
    assert call["body"]["country"] == "US"
    assert call["body"]["time_range"] == "week"


def test_tavily_auth_error():
    http = _FakeHttp(error=ProviderAuthError("Provider authentication failed.", provider="tavily"))
    provider = TavilyProvider(TavilyProviderConfig(api_key="bad"), http=http)
    with pytest.raises(ProviderAuthError):
        provider.search(SearchRequest(query="q", max_results=5))


def test_tavily_rate_limit():
    http = _FakeHttp(error=ProviderRateLimitError("Provider rate limited.", provider="tavily", retry_after=1))
    provider = TavilyProvider(TavilyProviderConfig(api_key="k"), http=http)
    with pytest.raises(ProviderRateLimitError) as ei:
        provider.search(SearchRequest(query="q", max_results=5))
    assert ei.value.retry_after == 1


def test_tavily_via_client_settings(monkeypatch: pytest.MonkeyPatch):
    payload = {"results": [{"title": "Tavily Hit", "url": "https://tv.example", "content": "ok"}]}
    from web_search.providers import tavily as tavily_mod

    real_init = tavily_mod.TavilyProvider.__init__

    def _init(self, config=None, *, http=None, fetch_context=None, pdf_semaphore=None):
        real_init(
            self,
            config,
            http=http or _FakeHttp(responses=[payload]),
            fetch_context=fetch_context,
            pdf_semaphore=pdf_semaphore,
        )

    monkeypatch.setattr(tavily_mod.TavilyProvider, "__init__", _init)

    settings = AppSettings(
        provider=ProviderSettings(
            name="tavily",
            api_key="test-key-not-real",
            max_results=5,
            endpoints={"tavily": ProviderEndpoint(api_key="test-key-not-real")},
        )
    )
    settings.validate()
    out = WebSearchClient(settings=settings).search("query")
    assert "Tavily Hit" in out
    assert "https://tv.example" in out


def test_settings_require_tavily_api_key():
    s = AppSettings(provider=ProviderSettings(name="tavily", api_key=None))
    with pytest.raises(Exception) as ei:
        s.validate()
    assert "TAVILY_API_KEY" in str(ei.value) or getattr(ei.value, "code", "") == "missing_api_key"


def test_tavily_search_does_not_request_raw_content():
    http = _FakeHttp(responses=[{"results": []}])
    TavilyProvider(TavilyProviderConfig(api_key="k"), http=http).search(SearchRequest(query="q", max_results=3))
    assert http.calls[0]["body"]["include_raw_content"] is False


def test_tavily_fetch_extract_success():
    payload = {
        "results": [
            {"url": "https://example.com/a", "raw_content": "# Hello\n\nWorld"},
        ]
    }
    http = _FakeHttp(responses=[payload])
    provider = TavilyProvider(TavilyProviderConfig(api_key="k"), http=http)
    result = provider.fetch("https://example.com/a")
    assert result.ok
    assert "Hello" in result.content
    assert result.content_type == "text/markdown"
    assert result.status_code is None
    assert http.calls[0]["path"] == "/extract"
    assert http.calls[0]["body"]["urls"] == ["https://example.com/a"]


def test_tavily_fetch_failed_results_falls_back_generic(monkeypatch):
    http = _FakeHttp(responses=[{"results": [], "failed_results": [{"url": "https://example.com/a", "error": "x"}]}])
    provider = TavilyProvider(TavilyProviderConfig(api_key="k"), http=http)

    def fake_fetch(*a, **k):
        from web_search.models import FetchResult

        return FetchResult.success(a[0], "generic-body", content_type="text/plain")

    monkeypatch.setattr("web_search.providers.base.fetch_raw", fake_fetch)
    out = provider.fetch("https://example.com/a")
    assert out.ok
    assert out.content == "generic-body"
    assert http.calls[0]["path"] == "/extract"


def test_tavily_fetch_auth_error_surfaces():
    http = _FakeHttp(error=ProviderAuthError("Provider authentication failed.", provider="tavily"))
    provider = TavilyProvider(TavilyProviderConfig(api_key="bad"), http=http)
    result = provider.fetch("https://example.com/a")
    assert not result.ok
    assert result.error_category == "auth"
    assert result.error_message.startswith("Fetch failed:")


def test_tavily_fetch_native_disabled_uses_generic(monkeypatch):
    from web_search.providers.base import FetchContext

    http = _FakeHttp(responses=[{"results": [{"url": "https://example.com/a", "raw_content": "paid"}]}])
    provider = TavilyProvider(
        TavilyProviderConfig(api_key="k"),
        http=http,
        fetch_context=FetchContext(native_fetch=False),
    )

    def fake_fetch(*a, **k):
        from web_search.models import FetchResult

        return FetchResult.success(a[0], "generic-only", content_type="text/plain")

    monkeypatch.setattr("web_search.providers.base.fetch_raw", fake_fetch)
    out = provider.fetch("https://example.com/a")
    assert out.content == "generic-only"
    assert http.calls == []
