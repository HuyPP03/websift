"""Fallback chain and POST JSON transport tests."""

from __future__ import annotations

import io
import json
from email.message import Message

import pytest

from web_search.client import WebSearchClient
from web_search.models import SearchRequest, SearchResult
from web_search.provider_http import ProviderHttpClient, ProviderHttpConfig
from web_search.providers.errors import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from web_search.providers.fallback import FallbackSearchProvider
from web_search.settings import AppSettings, ProviderEndpoint, ProviderSettings


class _StubProvider:
    def __init__(self, name: str, *, results=None, error=None):
        self.name = name
        self.capabilities = type("C", (), {"safe_search": False, "region": False, "time_range": False})()
        self._results = results
        self._error = error
        self.calls = 0

    def search(self, request: SearchRequest):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return list(self._results or [])


def test_fallback_uses_second_on_unavailable():
    p1 = _StubProvider("a", error=ProviderUnavailableError("down", provider="a"))
    p2 = _StubProvider(
        "b",
        results=[SearchResult(title="ok", url="https://ok.example", snippet="s", rank=1, source="b")],
    )
    chain = FallbackSearchProvider([p1, p2])
    out = chain.search(SearchRequest(query="q", max_results=3))
    assert p1.calls == 1
    assert p2.calls == 1
    assert out[0].title == "ok"
    assert chain.name == "a"


def test_fallback_no_auth_error():
    p1 = _StubProvider("a", error=ProviderAuthError("bad key", provider="a"))
    p2 = _StubProvider("b", results=[])
    chain = FallbackSearchProvider([p1, p2])
    with pytest.raises(ProviderAuthError):
        chain.search(SearchRequest(query="q", max_results=1))
    assert p2.calls == 0


def test_fallback_no_config_error():
    p1 = _StubProvider("a", error=ProviderConfigError("bad", code="unsupported_filter", provider="a"))
    p2 = _StubProvider("b", results=[])
    chain = FallbackSearchProvider([p1, p2])
    with pytest.raises(ProviderConfigError):
        chain.search(SearchRequest(query="q", max_results=1))
    assert p2.calls == 0


def test_fallback_rate_limit_then_success():
    p1 = _StubProvider("a", error=ProviderRateLimitError("rl", provider="a"))
    p2 = _StubProvider(
        "b",
        results=[SearchResult(title="fb", url="https://fb.example", snippet="x", rank=1, source="b")],
    )
    out = FallbackSearchProvider([p1, p2]).search(SearchRequest(query="q", max_results=1))
    assert out[0].source == "b"


def test_fallback_empty_chain():
    with pytest.raises(ProviderConfigError) as ei:
        FallbackSearchProvider([])
    assert ei.value.code == "empty_fallback_chain"


def test_fallback_all_fail_raises_last():
    p1 = _StubProvider("a", error=ProviderUnavailableError("a", provider="a"))
    p2 = _StubProvider("b", error=ProviderUnavailableError("b last", provider="b"))
    with pytest.raises(ProviderUnavailableError) as ei:
        FallbackSearchProvider([p1, p2]).search(SearchRequest(query="q", max_results=1))
    assert "b last" in ei.value.message


def test_settings_unknown_fallback():
    s = AppSettings(provider=ProviderSettings(name="ddgs", fallback_providers=("notreal",)))
    with pytest.raises(Exception) as ei:
        s.validate()
    assert "FALLBACK" in str(ei.value).upper() or getattr(ei.value, "code", "") == "unknown_provider"


def test_settings_fallback_requires_brave_key():
    s = AppSettings(
        provider=ProviderSettings(
            name="ddgs",
            fallback_providers=("brave",),
            endpoints={},
        )
    )
    with pytest.raises(Exception) as ei:
        s.validate()
    assert "BRAVE_API_KEY" in str(ei.value)


class _FakeHTTPResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        super().__init__(body)
        self.status = status
        self._headers = Message()
        for k, v in (headers or {}).items():
            self._headers[k] = v

    def getcode(self):
        return self.status

    @property
    def headers(self):
        return self._headers


def test_post_json_success(monkeypatch: pytest.MonkeyPatch):
    body = json.dumps({"ok": True}).encode()

    def fake_urlopen(req, timeout=None):
        assert req.get_method() == "POST"
        assert "https://api.example.com/search" in req.full_url
        assert req.data is not None
        assert b"query" in req.data
        return _FakeHTTPResponse(body, 200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c = ProviderHttpClient(
        ProviderHttpConfig(
            base_url="https://api.example.com",
            headers={"Authorization": "Bearer sec"},
            retry_max=0,
        )
    )
    data = c.post_json("/search", json_body={"query": "x"}, provider="tavily")
    assert data == {"ok": True}


def test_client_fallback_chain(monkeypatch: pytest.MonkeyPatch):
    from web_search.providers import brave as brave_mod
    from web_search.providers import ddgs as ddgs_mod

    class _BraveHttp:
        def get_json(self, path="", *, params=None, extra_headers=None, provider=None):
            raise ProviderUnavailableError("brave down", provider="brave")

    real_brave = brave_mod.BraveProvider.__init__

    def _brave_init(self, config=None, *, http=None):
        real_brave(self, config, http=http or _BraveHttp())

    monkeypatch.setattr(brave_mod.BraveProvider, "__init__", _brave_init)

    def _ddgs_search(self, request):
        return [SearchResult(title="DDGS", url="https://d.example", snippet="s", rank=1, source="ddgs")]

    monkeypatch.setattr(ddgs_mod.DdgsProvider, "search", _ddgs_search)

    settings = AppSettings(
        provider=ProviderSettings(
            name="brave",
            api_key="k",
            fallback_providers=("ddgs",),
            endpoints={"brave": ProviderEndpoint(api_key="k")},
        )
    )
    settings.validate()
    out = WebSearchClient(settings=settings).search("q")
    assert "DDGS" in out
    assert "https://d.example" in out
