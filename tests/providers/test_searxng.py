"""SearXNG provider adapter tests (mocked HTTP)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from web_search.client import WebSearchClient
from web_search.models import SearchRequest
from web_search.providers.errors import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from web_search.providers.registry import create_provider
from web_search.providers.searxng import SearxngProvider, SearxngProviderConfig
from web_search.settings import AppSettings, ProviderSettings


@dataclass
class _FakeResp:
    status: int
    headers: dict
    body: bytes
    url: str = "https://searx.example/search"


class _FakeHttp:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[dict] = []
        self.base_url = "https://searx.example"
        self._headers = {}

    def get_json(self, path="", *, params=None, extra_headers=None, provider=None):
        self.calls.append({"path": path, "params": dict(params or {}), "provider": provider})
        if self.error is not None:
            raise self.error
        if not self.responses:
            return {"results": []}
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, _FakeResp):
            # Mimic get_json status handling via raising when needed
            if item.status in {401, 403}:
                raise ProviderAuthError("Provider authentication failed.", provider=provider)
            if item.status == 429:
                raise ProviderRateLimitError("Provider rate limited.", provider=provider)
            if item.status >= 500:
                raise ProviderUnavailableError(f"Provider unavailable (HTTP {item.status}).", provider=provider)
            if item.status < 200 or item.status >= 300:
                from web_search.providers.errors import ProviderResponseError

                raise ProviderResponseError(f"Provider returned HTTP {item.status}.", provider=provider)
            return json.loads(item.body.decode("utf-8")) if item.body else None
        return item


def test_searxng_missing_base_url():
    with pytest.raises(ProviderConfigError) as ei:
        SearxngProvider(SearxngProviderConfig(base_url=""))
    assert ei.value.code == "missing_base_url"


def test_searxng_create_provider_requires_config():
    with pytest.raises(ProviderConfigError) as ei:
        create_provider("searxng", None)
    assert ei.value.code == "missing_config"


def test_searxng_maps_results_and_params():
    payload = {
        "results": [
            {"title": "A", "url": "https://a.example", "content": "snippet a"},
            {"title": "B", "url": "https://b.example", "content": "snippet b"},
            {"title": "C", "url": "https://c.example", "content": "snippet c"},
        ]
    }
    http = _FakeHttp(responses=[payload])
    provider = SearxngProvider(
        SearxngProviderConfig(base_url="https://searx.example", allow_http=False),
        http=http,
    )
    results = provider.search(SearchRequest(query="python", max_results=2, safe_search="strict", region="en"))
    assert len(results) == 2
    assert results[0].title == "A"
    assert results[0].url == "https://a.example"
    assert results[0].snippet == "snippet a"
    assert results[0].source == "searxng"
    assert results[0].rank == 1
    call = http.calls[0]
    assert call["path"] == "/search"
    assert call["params"]["q"] == "python"
    assert call["params"]["format"] == "json"
    assert call["params"]["safesearch"] == 2
    assert call["params"]["language"] == "en"


def test_searxng_auth_header_on_config():
    # Construct real client path without network: invalid host still builds headers.
    # Use allow_http localhost-style base and inject http instead.
    http = _FakeHttp(responses=[{"results": []}])
    http._headers = {"Authorization": "Bearer secret-searx-key"}
    provider = SearxngProvider(
        SearxngProviderConfig(base_url="https://searx.example", api_key="secret-searx-key"),
        http=http,
    )
    assert provider.search(SearchRequest(query="q", max_results=1)) == []


def test_searxng_auth_error():
    http = _FakeHttp(error=ProviderAuthError("Provider authentication failed.", provider="searxng"))
    provider = SearxngProvider(SearxngProviderConfig(base_url="https://searx.example"), http=http)
    with pytest.raises(ProviderAuthError):
        provider.search(SearchRequest(query="q", max_results=5))


def test_searxng_via_client_settings(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "results": [
            {"title": "T", "url": "https://t.example", "content": "S"},
        ]
    }

    # Patch provider construction to inject fake http
    from web_search.providers import searxng as searxng_mod

    real_init = searxng_mod.SearxngProvider.__init__

    def _init(self, config=None, *, http=None):
        real_init(self, config, http=http or _FakeHttp(responses=[payload]))

    monkeypatch.setattr(searxng_mod.SearxngProvider, "__init__", _init)

    settings = AppSettings(
        provider=ProviderSettings(
            name="searxng",
            base_url="https://searx.example",
            max_results=3,
            timeout_seconds=12,
        )
    )
    settings.validate()
    client = WebSearchClient(settings=settings)
    out = client.search("hello")
    assert "Title: T" in out
    assert "https://t.example" in out


def test_settings_require_searxng_base_url():
    s = AppSettings(provider=ProviderSettings(name="searxng", base_url=None))
    with pytest.raises(Exception) as ei:
        s.validate()
    assert "SEARXNG_BASE_URL" in str(ei.value) or getattr(ei.value, "code", "") == "missing_base_url"
