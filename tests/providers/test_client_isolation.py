"""Credential isolation: provider secrets never ride page-fetch / GitHub path."""

from __future__ import annotations

from websift.client import _GITHUB_README_HEADERS, WebSearchClient
from websift.models import ErrorCategory, FetchResult
from websift.provider_http import ProviderHttpClient, ProviderHttpConfig, is_secret_header_name


def test_github_readme_headers_are_non_secret():
    for name in _GITHUB_README_HEADERS:
        assert not is_secret_header_name(name)


def test_github_shortcut_does_not_attach_provider_secrets(monkeypatch):
    """GitHub fetch only gets Accept / API-version — never Authorization."""
    calls: list[dict | None] = []

    def fake_fetch(url, timeout, max_b, max_pdf, extra_headers=None, **kwargs):
        calls.append(extra_headers)
        if "api.github.com" in url:
            return FetchResult.success(url, "# Hello\n", content_type="text/plain", status_code=200)
        return FetchResult.failure(url, "skip", ErrorCategory.UNKNOWN)

    monkeypatch.setattr("websift.providers.base.fetch_raw", fake_fetch)
    out = WebSearchClient().fetch("https://github.com/python/cpython")
    assert "Hello" in out
    assert calls
    headers = calls[0] or {}
    assert "Authorization" not in headers
    assert "X-API-Key" not in headers
    assert headers.get("Accept") == "application/vnd.github.raw+json"
    # Prove provider secret client would refuse these if mixed
    provider_client = ProviderHttpClient(
        ProviderHttpConfig(
            base_url="https://api.brave.example",
            headers={"X-Subscription-Token": "brave-secret-token"},
        )
    )
    # GitHub headers alone are fine
    provider_client.assert_no_page_fetch_leak(headers)
    # Mixing in secret would fail
    mixed = dict(headers)
    mixed["X-Subscription-Token"] = "brave-secret-token"
    try:
        provider_client.assert_no_page_fetch_leak(mixed)
        raised = False
    except Exception:
        raised = True
    assert raised


def test_tavily_extract_keeps_secrets_on_provider_http(monkeypatch):
    """Native extract posts to Tavily only; generic fallback has no provider headers."""
    from websift.models import FetchResult
    from websift.providers.tavily import TavilyProvider, TavilyProviderConfig

    class FakeHttp:
        def __init__(self):
            self.calls = []
            self.base_url = "https://api.tavily.com"
            self._headers = {"Authorization": "Bearer tavily-secret"}

        def post_json(self, path="", *, params=None, json_body=None, extra_headers=None, provider=None):
            self.calls.append({"path": path, "body": dict(json_body or {})})
            return {"failed_results": [{"url": json_body["urls"][0], "error": "nope"}]}

    generic_headers = []

    def fake_fetch(url, timeout, max_b, max_pdf, extra_headers=None, **kwargs):
        generic_headers.append(extra_headers)
        return FetchResult.success(url, "generic", content_type="text/plain")

    monkeypatch.setattr("websift.providers.base.fetch_raw", fake_fetch)
    http = FakeHttp()
    provider = TavilyProvider(TavilyProviderConfig(api_key="tavily-secret"), http=http)
    out = provider.fetch("https://example.com/page")
    assert out.content == "generic"
    assert http.calls[0]["path"] == "/extract"
    assert http.calls[0]["body"]["urls"] == ["https://example.com/page"]
    # generic path must not receive Authorization
    assert not generic_headers[0] or "Authorization" not in (generic_headers[0] or {})
