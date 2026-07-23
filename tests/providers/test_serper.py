"""Serper provider adapter tests (mocked HTTP)."""

from __future__ import annotations

import pytest

from websift.client import WebSearchClient
from websift.models import SearchRequest
from websift.providers.errors import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderRateLimitError,
)
from websift.providers.registry import create_provider
from websift.providers.serper import SerperProvider, SerperProviderConfig, _map_serper_tbs
from websift.settings import AppSettings, ProviderSettings


class _FakeHttp:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[dict] = []
        self.base_url = "https://google.serper.dev"
        self._headers = {"X-API-KEY": "serper-secret"}

    def post_json(self, path="", *, json_body=None, extra_headers=None, provider=None):
        self.calls.append({"path": path, "json_body": dict(json_body or {}), "provider": provider})
        if self.error is not None:
            raise self.error
        if not self.responses:
            return {"organic": []}
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_serper_missing_api_key():
    with pytest.raises(ProviderConfigError) as ei:
        SerperProvider(SerperProviderConfig(api_key=""))
    assert ei.value.code == "missing_api_key"


def test_serper_create_provider_requires_config():
    with pytest.raises(ProviderConfigError) as ei:
        create_provider("serper", None)
    assert ei.value.code == "missing_config"


def test_serper_maps_organic_results_and_params():
    payload = {
        "organic": [
            {"title": "One", "link": "https://one.example", "snippet": "d1"},
            {"title": "Two", "link": "https://two.example", "snippet": "d2"},
        ]
    }
    http = _FakeHttp(responses=[payload])
    provider = SerperProvider(SerperProviderConfig(api_key="k"), http=http)
    results = provider.search(SearchRequest(query="rust", max_results=1, region="US", time_range="week"))
    assert len(results) == 1
    assert results[0].title == "One"
    assert results[0].url == "https://one.example"
    assert results[0].snippet == "d1"
    assert results[0].source == "serper"
    call = http.calls[0]
    assert call["path"] == "/search"
    assert call["json_body"]["q"] == "rust"
    assert call["json_body"]["num"] == 1
    assert call["json_body"]["gl"] == "us"
    assert call["json_body"]["tbs"] == "qdr:w"


def test_serper_auth_error():
    http = _FakeHttp(error=ProviderAuthError("Provider authentication failed.", provider="serper"))
    provider = SerperProvider(SerperProviderConfig(api_key="bad"), http=http)
    with pytest.raises(ProviderAuthError):
        provider.search(SearchRequest(query="q", max_results=5))


def test_serper_rate_limit():
    http = _FakeHttp(error=ProviderRateLimitError("Provider rate limited.", provider="serper", retry_after=2))
    provider = SerperProvider(SerperProviderConfig(api_key="k"), http=http)
    with pytest.raises(ProviderRateLimitError) as ei:
        provider.search(SearchRequest(query="q", max_results=5))
    assert ei.value.retry_after == 2


def test_serper_via_client_settings(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "organic": [
            {"title": "Serper Hit", "link": "https://s.example", "snippet": "ok"},
        ]
    }
    from websift.providers import serper as serper_mod

    real_init = serper_mod.SerperProvider.__init__

    def _init(self, config=None, *, http=None, fetch_context=None, pdf_semaphore=None):
        real_init(
            self,
            config,
            http=http or _FakeHttp(responses=[payload]),
            fetch_context=fetch_context,
            pdf_semaphore=pdf_semaphore,
        )

    monkeypatch.setattr(serper_mod.SerperProvider, "__init__", _init)

    settings = AppSettings(
        provider=ProviderSettings(
            name="serper",
            api_key="test-key-not-real",
            max_results=5,
        )
    )
    settings.validate()
    out = WebSearchClient(settings=settings).search("query")
    assert "Serper Hit" in out
    assert "https://s.example" in out


def test_settings_require_serper_api_key():
    s = AppSettings(provider=ProviderSettings(name="serper", api_key=None))
    with pytest.raises(Exception) as ei:
        s.validate()
    assert "SERPER_API_KEY" in str(ei.value) or getattr(ei.value, "code", "") == "missing_api_key"


def test_map_serper_tbs():
    assert _map_serper_tbs(None) is None
    assert _map_serper_tbs("any") is None
    assert _map_serper_tbs("day") == "qdr:d"
    assert _map_serper_tbs("w") == "qdr:w"
    assert _map_serper_tbs("month") == "qdr:m"
    assert _map_serper_tbs("year") == "qdr:y"
    assert _map_serper_tbs("unknown") is None


def test_serper_secret_not_in_public_headers():
    from websift.provider_http import ProviderHttpClient, ProviderHttpConfig

    client = ProviderHttpClient(
        ProviderHttpConfig(
            base_url="https://google.serper.dev",
            headers={"X-API-KEY": "super-secret-serper-token"},
        )
    )
    assert client.public_headers["X-API-KEY"] == "[REDACTED]"
    assert client.build_headers()["X-API-KEY"] == "super-secret-serper-token"
