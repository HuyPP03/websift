"""Credential isolation: provider secrets never ride page-fetch / GitHub path."""

from __future__ import annotations

from web_search.client import WebSearchClient, _GITHUB_README_HEADERS
from web_search.models import ErrorCategory, FetchResult
from web_search.provider_http import ProviderHttpClient, ProviderHttpConfig, is_secret_header_name


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

    monkeypatch.setattr("web_search.client.fetch_raw", fake_fetch)
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
