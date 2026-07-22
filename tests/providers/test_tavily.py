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

    def _init(self, config=None, *, http=None):
        real_init(self, config, http=http or _FakeHttp(responses=[payload]))

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
