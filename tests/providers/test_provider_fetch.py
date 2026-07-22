"""Coverage for BaseProvider fetch ownership and native extract policy."""

from __future__ import annotations

import pytest

from web_search.client import WebSearchClient
from web_search.models import ErrorCategory, FetchResult, SearchRequest, SearchResult
from web_search.providers.base import BaseProvider, FetchContext
from web_search.providers.ddgs import DdgsProvider
from web_search.providers.errors import (
    ProviderAuthError,
    ProviderBillingError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from web_search.providers.exa import ExaProvider, ExaProviderConfig
from web_search.providers.fallback import FallbackSearchProvider
from web_search.providers.tavily import TavilyProvider, TavilyProviderConfig
from web_search.settings import AppSettings, FetchSettings, ProviderSettings


class _StubSearch(BaseProvider):
    name = "stub"

    def search(self, request: SearchRequest) -> list[SearchResult]:
        return [SearchResult(title="t", url="https://e/", snippet="s", rank=1, source="stub")]


class _FakeHttp:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[dict] = []

    def post_json(self, path="", *, params=None, json_body=None, extra_headers=None, provider=None):
        self.calls.append({"path": path, "body": dict(json_body or {})})
        if self.error is not None:
            raise self.error
        if not self.responses:
            return {"results": []}
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_base_provider_fetch_blocks_empty():
    assert BaseProvider().fetch("").error_category == ErrorCategory.EMPTY_INPUT


def test_client_delegates_fetch_to_primary(monkeypatch):
    seen = []

    class P(_StubSearch):
        def fetch(self, url: str) -> FetchResult:
            seen.append(url)
            return FetchResult.success(url, "from-primary")

    out = WebSearchClient(provider=P()).fetch("https://example.com/")
    assert out == "from-primary"
    assert seen == ["https://example.com/"]


def test_client_maps_provider_fetch_exception():
    class P(_StubSearch):
        def fetch(self, url: str) -> FetchResult:
            raise ProviderAuthError("nope", provider="stub")

    out = WebSearchClient(provider=P()).fetch_structured("https://example.com/")
    assert out.error_category == ErrorCategory.AUTH
    assert out.error_message.startswith("Fetch failed:")


def test_client_maps_unexpected_fetch_exception():
    class P(_StubSearch):
        def fetch(self, url: str) -> FetchResult:
            raise RuntimeError("boom token=secret123")

    out = WebSearchClient(provider=P()).fetch_structured("https://example.com/")
    assert out.error_category == ErrorCategory.UNKNOWN
    assert "Fetch failed:" in (out.error_message or "")


def test_fallback_fetch_uses_primary_only(monkeypatch):
    class Primary(_StubSearch):
        name = "primary"

        def fetch(self, url: str) -> FetchResult:
            return FetchResult.success(url, "primary-fetch")

    class Secondary(_StubSearch):
        name = "secondary"

        def fetch(self, url: str) -> FetchResult:
            raise AssertionError("secondary fetch must not run")

    chain = FallbackSearchProvider([Primary(), Secondary()])
    assert chain.fetch("https://example.com/").content == "primary-fetch"


def test_tavily_billing_and_rate_limit_surface():
    p = TavilyProvider(
        TavilyProviderConfig(api_key="k"),
        http=_FakeHttp(error=ProviderBillingError("plan limit", provider="tavily")),
    )
    r = p.fetch("https://example.com/")
    assert not r.ok
    assert r.error_category == ErrorCategory.PROVIDER
    assert "Fetch failed:" in (r.error_message or "")

    p2 = TavilyProvider(
        TavilyProviderConfig(api_key="k"),
        http=_FakeHttp(error=ProviderRateLimitError("slow", provider="tavily")),
    )
    r2 = p2.fetch("https://example.com/")
    assert r2.error_category == ErrorCategory.RATE_LIMIT


def test_tavily_transient_falls_back(monkeypatch):
    p = TavilyProvider(
        TavilyProviderConfig(api_key="k"),
        http=_FakeHttp(error=ProviderUnavailableError("down", provider="tavily")),
    )

    def fake_fetch(*a, **k):
        return FetchResult.success(a[0], "generic-after-5xx", content_type="text/plain")

    monkeypatch.setattr("web_search.providers.base.fetch_raw", fake_fetch)
    assert p.fetch("https://example.com/").content == "generic-after-5xx"


def test_tavily_malformed_and_empty_content_paths(monkeypatch):
    # empty raw_content in results → URL-level fail → generic
    p = TavilyProvider(
        TavilyProviderConfig(api_key="k"),
        http=_FakeHttp(responses=[{"results": [{"url": "https://example.com/", "raw_content": "  "}]}]),
    )

    def fake_fetch(*a, **k):
        return FetchResult.success(a[0], "generic-empty", content_type="text/plain")

    monkeypatch.setattr("web_search.providers.base.fetch_raw", fake_fetch)
    assert p.fetch("https://example.com/").content == "generic-empty"

    # completely missing results fields → ProviderResponseError → generic
    p2 = TavilyProvider(
        TavilyProviderConfig(api_key="k"),
        http=_FakeHttp(responses=[{}]),
    )
    monkeypatch.setattr("web_search.providers.base.fetch_raw", fake_fetch)
    assert p2.fetch("https://example.com/").content == "generic-empty"


def test_exa_timeout_falls_back(monkeypatch):
    p = ExaProvider(
        ExaProviderConfig(api_key="k"),
        http=_FakeHttp(error=ProviderTimeoutError("slow", provider="exa")),
    )

    def fake_fetch(*a, **k):
        return FetchResult.success(a[0], "exa-generic", content_type="text/plain")

    monkeypatch.setattr("web_search.providers.base.fetch_raw", fake_fetch)
    assert p.fetch("https://example.com/").content == "exa-generic"


def test_exa_native_disabled(monkeypatch):
    p = ExaProvider(
        ExaProviderConfig(api_key="k"),
        http=_FakeHttp(responses=[{"results": [{"url": "https://example.com/", "text": "paid"}]}]),
        fetch_context=FetchContext(native_fetch=False),
    )

    def fake_fetch(*a, **k):
        return FetchResult.success(a[0], "forced-generic", content_type="text/plain")

    monkeypatch.setattr("web_search.providers.base.fetch_raw", fake_fetch)
    assert p.fetch("https://example.com/").content == "forced-generic"
    assert p._http.calls == [] if hasattr(p._http, "calls") else True


def test_validate_url_for_provider_blocks_userinfo():
    p = DdgsProvider()
    blocked = p.validate_url_for_provider("https://user:pass@example.com/")
    assert blocked is not None
    assert blocked.error_category == ErrorCategory.BLOCKED


def test_provider_http_billing_status():
    from web_search.provider_http import ProviderHttpClient, ProviderHttpConfig, ProviderHttpResponse

    client = ProviderHttpClient(ProviderHttpConfig(base_url="https://api.example"))
    with pytest.raises(ProviderBillingError):
        client._parse_json_response(
            ProviderHttpResponse(status=402, headers={}, body=b"{}", url="https://api.example/x"),
            provider="tavily",
        )
    with pytest.raises(ProviderBillingError):
        client._parse_json_response(
            ProviderHttpResponse(status=432, headers={}, body=b"{}", url="https://api.example/x"),
            provider="tavily",
        )


def test_settings_native_fetch_env():
    s = AppSettings.from_env({"PROVIDER_NATIVE_FETCH": "false"})
    assert s.fetch.native_fetch is False
    c = WebSearchClient(settings=s)
    assert c._fetch_context.native_fetch is False


def test_client_injected_provider_gets_fetch_context():
    settings = AppSettings(
        provider=ProviderSettings(name="ddgs"),
        fetch=FetchSettings(native_fetch=False, max_redirects=1),
    )
    p = _StubSearch()
    c = WebSearchClient(settings=settings, provider=p)
    assert p._fetch_context.native_fetch is False
    assert p._fetch_context.max_redirects == 1
    assert c._primary_provider is p


def test_truncate_native_content():
    p = BaseProvider(fetch_context=FetchContext(max_page_chars=10))
    ok = p.truncate_native_content("https://e/", "abcdefghijklmnop", content_type="text/markdown")
    assert ok.ok
    assert ok.truncated is True
    empty = p.truncate_native_content("https://e/", "   ")
    assert empty.error_category == ErrorCategory.EMPTY_CONTENT


def test_tavily_response_error_type_on_search():
    p = TavilyProvider(TavilyProviderConfig(api_key="k"), http=_FakeHttp(responses=["not-a-dict"]))
    with pytest.raises(ProviderResponseError):
        p.search(SearchRequest(query="q", max_results=1))
