"""Exa provider adapter tests (mocked HTTP)."""

from __future__ import annotations

import pytest

from web_search.client import WebSearchClient
from web_search.models import SearchRequest
from web_search.providers.errors import ProviderAuthError, ProviderConfigError
from web_search.providers.exa import ExaProvider, ExaProviderConfig
from web_search.providers.registry import create_provider
from web_search.settings import AppSettings, ProviderEndpoint, ProviderSettings


class _FakeHttp:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[dict] = []
        self.base_url = "https://api.exa.ai"
        self._headers = {"x-api-key": "exa-secret"}

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


def test_exa_missing_api_key():
    with pytest.raises(ProviderConfigError) as ei:
        ExaProvider(ExaProviderConfig(api_key=""))
    assert ei.value.code == "missing_api_key"


def test_exa_create_provider_requires_config():
    with pytest.raises(ProviderConfigError) as ei:
        create_provider("exa", None)
    assert ei.value.code == "missing_config"


def test_exa_maps_results_and_params():
    payload = {
        "results": [
            {"title": "E1", "url": "https://e1.example", "text": "snippet one"},
            {"title": "E2", "url": "https://e2.example", "text": "snippet two"},
        ]
    }
    http = _FakeHttp(responses=[payload])
    provider = ExaProvider(ExaProviderConfig(api_key="k"), http=http)
    results = provider.search(SearchRequest(query="agents", max_results=1))
    assert len(results) == 1
    assert results[0].title == "E1"
    assert results[0].url == "https://e1.example"
    assert results[0].snippet == "snippet one"
    assert results[0].source == "exa"
    call = http.calls[0]
    assert call["path"] == "/search"
    assert call["body"]["query"] == "agents"
    assert call["body"]["numResults"] == 1
    assert "contents" in call["body"]


def test_exa_auth_error():
    http = _FakeHttp(error=ProviderAuthError("Provider authentication failed.", provider="exa"))
    provider = ExaProvider(ExaProviderConfig(api_key="bad"), http=http)
    with pytest.raises(ProviderAuthError):
        provider.search(SearchRequest(query="q", max_results=5))


def test_exa_via_client_settings(monkeypatch: pytest.MonkeyPatch):
    payload = {"results": [{"title": "Exa Hit", "url": "https://ex.example", "text": "ok"}]}
    from web_search.providers import exa as exa_mod

    real_init = exa_mod.ExaProvider.__init__

    def _init(self, config=None, *, http=None):
        real_init(self, config, http=http or _FakeHttp(responses=[payload]))

    monkeypatch.setattr(exa_mod.ExaProvider, "__init__", _init)

    settings = AppSettings(
        provider=ProviderSettings(
            name="exa",
            api_key="test-key-not-real",
            max_results=5,
            endpoints={"exa": ProviderEndpoint(api_key="test-key-not-real")},
        )
    )
    settings.validate()
    out = WebSearchClient(settings=settings).search("query")
    assert "Exa Hit" in out
    assert "https://ex.example" in out


def test_settings_require_exa_api_key():
    s = AppSettings(provider=ProviderSettings(name="exa", api_key=None))
    with pytest.raises(Exception) as ei:
        s.validate()
    assert "EXA_API_KEY" in str(ei.value) or getattr(ei.value, "code", "") == "missing_api_key"
