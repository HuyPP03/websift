"""Brave provider adapter tests (mocked HTTP)."""

from __future__ import annotations

import pytest

from websift.client import WebSearchClient
from websift.models import SearchRequest
from websift.providers.brave import BraveProvider, BraveProviderConfig
from websift.providers.errors import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderRateLimitError,
)
from websift.providers.registry import create_provider
from websift.settings import AppSettings, ProviderSettings


class _FakeHttp:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[dict] = []
        self.base_url = "https://api.search.brave.com"
        self._headers = {"X-Subscription-Token": "brave-secret"}

    def get_json(self, path="", *, params=None, extra_headers=None, provider=None):
        self.calls.append({"path": path, "params": dict(params or {}), "provider": provider})
        if self.error is not None:
            raise self.error
        if not self.responses:
            return {"web": {"results": []}}
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_brave_missing_api_key():
    with pytest.raises(ProviderConfigError) as ei:
        BraveProvider(BraveProviderConfig(api_key=""))
    assert ei.value.code == "missing_api_key"


def test_brave_create_provider_requires_config():
    with pytest.raises(ProviderConfigError) as ei:
        create_provider("brave", None)
    assert ei.value.code == "missing_config"


def test_brave_maps_web_results_and_params():
    payload = {
        "web": {
            "results": [
                {"title": "One", "url": "https://one.example", "description": "d1"},
                {"title": "Two", "url": "https://two.example", "description": "d2"},
            ]
        }
    }
    http = _FakeHttp(responses=[payload])
    provider = BraveProvider(BraveProviderConfig(api_key="k"), http=http)
    results = provider.search(
        SearchRequest(query="rust", max_results=1, safe_search="off", region="US", time_range="week")
    )
    assert len(results) == 1
    assert results[0].title == "One"
    assert results[0].url == "https://one.example"
    assert results[0].snippet == "d1"
    assert results[0].source == "brave"
    call = http.calls[0]
    assert call["path"] == "/res/v1/web/search"
    assert call["params"]["q"] == "rust"
    assert call["params"]["count"] == 1
    assert call["params"]["safesearch"] == "off"
    assert call["params"]["country"] == "US"
    assert call["params"]["freshness"] == "pw"


def test_brave_auth_error():
    http = _FakeHttp(error=ProviderAuthError("Provider authentication failed.", provider="brave"))
    provider = BraveProvider(BraveProviderConfig(api_key="bad"), http=http)
    with pytest.raises(ProviderAuthError):
        provider.search(SearchRequest(query="q", max_results=5))


def test_brave_rate_limit():
    http = _FakeHttp(error=ProviderRateLimitError("Provider rate limited.", provider="brave", retry_after=2))
    provider = BraveProvider(BraveProviderConfig(api_key="k"), http=http)
    with pytest.raises(ProviderRateLimitError) as ei:
        provider.search(SearchRequest(query="q", max_results=5))
    assert ei.value.retry_after == 2


def test_brave_via_client_settings(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "web": {
            "results": [
                {"title": "Brave Hit", "url": "https://b.example", "description": "ok"},
            ]
        }
    }
    from websift.providers import brave as brave_mod

    real_init = brave_mod.BraveProvider.__init__

    def _init(self, config=None, *, http=None, fetch_context=None, pdf_semaphore=None):
        real_init(
            self,
            config,
            http=http or _FakeHttp(responses=[payload]),
            fetch_context=fetch_context,
            pdf_semaphore=pdf_semaphore,
        )

    monkeypatch.setattr(brave_mod.BraveProvider, "__init__", _init)

    settings = AppSettings(
        provider=ProviderSettings(
            name="brave",
            api_key="test-key-not-real",
            max_results=5,
        )
    )
    settings.validate()
    out = WebSearchClient(settings=settings).search("query")
    assert "Brave Hit" in out
    assert "https://b.example" in out


def test_settings_require_brave_api_key():
    s = AppSettings(provider=ProviderSettings(name="brave", api_key=None))
    with pytest.raises(Exception) as ei:
        s.validate()
    assert "BRAVE_API_KEY" in str(ei.value) or getattr(ei.value, "code", "") == "missing_api_key"


def test_brave_secret_not_in_public_headers():
    from websift.provider_http import ProviderHttpClient, ProviderHttpConfig

    client = ProviderHttpClient(
        ProviderHttpConfig(
            base_url="https://api.search.brave.com",
            headers={"X-Subscription-Token": "super-secret-brave-token"},
        )
    )
    assert client.public_headers["X-Subscription-Token"] == "[REDACTED]"
    assert client.build_headers()["X-Subscription-Token"] == "super-secret-brave-token"
