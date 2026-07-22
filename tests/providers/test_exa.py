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

    def _init(self, config=None, *, http=None, fetch_context=None, pdf_semaphore=None):
        real_init(
            self,
            config,
            http=http or _FakeHttp(responses=[payload]),
            fetch_context=fetch_context,
            pdf_semaphore=pdf_semaphore,
        )

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


def test_exa_fetch_contents_success():
    payload = {
        "results": [
            {"url": "https://example.com/a", "text": "Exa full page text"},
        ]
    }
    http = _FakeHttp(responses=[payload])
    provider = ExaProvider(ExaProviderConfig(api_key="k"), http=http)
    result = provider.fetch("https://example.com/a")
    assert result.ok
    assert "Exa full page text" in result.content
    assert result.status_code is None
    assert http.calls[0]["path"] == "/contents"
    assert http.calls[0]["body"]["urls"] == ["https://example.com/a"]
    assert http.calls[0]["body"]["text"] is True


def test_exa_fetch_status_failure_falls_back(monkeypatch):
    payload = {
        "results": [],
        "statuses": [{"id": "https://example.com/a", "status": "error", "error": {"tag": "CRAWL_NOT_FOUND"}}],
    }
    http = _FakeHttp(responses=[payload])
    provider = ExaProvider(ExaProviderConfig(api_key="k"), http=http)

    def fake_fetch(*a, **k):
        from web_search.models import FetchResult

        return FetchResult.success(a[0], "generic-exa", content_type="text/plain")

    monkeypatch.setattr("web_search.providers.base.fetch_raw", fake_fetch)
    out = provider.fetch("https://example.com/a")
    assert out.content == "generic-exa"


def test_exa_fetch_auth_error_surfaces():
    http = _FakeHttp(error=ProviderAuthError("Provider authentication failed.", provider="exa"))
    provider = ExaProvider(ExaProviderConfig(api_key="bad"), http=http)
    result = provider.fetch("https://example.com/a")
    assert not result.ok
    assert result.error_category == "auth"
    assert "Fetch failed:" in (result.error_message or "")
