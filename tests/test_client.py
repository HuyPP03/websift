"""WebSearchClient public API characterization (mocked network)."""

from __future__ import annotations

import pytest

from websift.client import (
    WebSearchClient,
    format_fetch_result,
    format_search_response,
    process_fetched_body,
)
from websift.models import (
    ErrorCategory,
    FetchResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from websift.providers.base import github_readme_api_url


class TestSearch:
    def test_empty_query(self):
        assert WebSearchClient().search("") == "No query provided."
        assert WebSearchClient().search("   ") == "No query provided."

    def test_import_error_message(self, monkeypatch: pytest.MonkeyPatch):
        import builtins

        real_import = builtins.__import__

        def _import(name, *args, **kwargs):
            if name == "ddgs" or name.startswith("ddgs."):
                raise ImportError("no ddgs")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _import)
        out = WebSearchClient().search("python")
        assert "ddgs not installed" in out

    def test_success_format(self, monkeypatch: pytest.MonkeyPatch):
        import sys
        import types

        class FakeDDGS:
            def __init__(self, timeout=None):
                self.timeout = timeout

            def text(self, query, max_results=5):
                return [
                    {"title": "T1", "href": "https://a.example/", "body": "S1"},
                    {"title": "T2", "href": "https://b.example/", "body": "S2"},
                ]

        mod = types.ModuleType("ddgs")
        mod.DDGS = FakeDDGS
        monkeypatch.setitem(sys.modules, "ddgs", mod)

        out = WebSearchClient(max_results=2, timeout=7).search("asyncio")
        assert "Title: T1" in out
        assert "URL: https://a.example/" in out
        assert "Snippet: S1" in out
        assert "---" in out
        assert "Call fetch(url)" in out

    def test_no_results(self, monkeypatch: pytest.MonkeyPatch):
        import sys
        import types

        class FakeDDGS:
            def __init__(self, timeout=None):
                pass

            def text(self, query, max_results=5):
                return []

        mod = types.ModuleType("ddgs")
        mod.DDGS = FakeDDGS
        monkeypatch.setitem(sys.modules, "ddgs", mod)
        assert WebSearchClient().search("nothing") == "No results found."

    def test_search_exception(self, monkeypatch: pytest.MonkeyPatch):
        import sys
        import types

        class FakeDDGS:
            def __init__(self, timeout=None):
                pass

            def text(self, query, max_results=5):
                raise RuntimeError("rate limited")

        mod = types.ModuleType("ddgs")
        mod.DDGS = FakeDDGS
        monkeypatch.setitem(sys.modules, "ddgs", mod)
        out = WebSearchClient().search("x")
        assert out.startswith("Search failed:")
        assert "rate" in out.lower()


class TestFetch:
    def test_empty_url(self):
        assert WebSearchClient().fetch("") == "No URL provided."
        assert WebSearchClient().fetch("  ") == "No URL provided."

    def test_fetch_error_passthrough(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.failure("http://x/", "Blocked: private", ErrorCategory.BLOCKED),
        )
        assert WebSearchClient().fetch("http://x/") == "Blocked: private"

    def test_fetch_plain_text(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.success("https://example.com/a.txt", "plain body", content_type="text/plain"),
        )
        out = WebSearchClient().fetch("https://example.com/a.txt")
        assert out == "plain body"

    def test_fetch_html_converted(self, monkeypatch: pytest.MonkeyPatch):
        html = "<html><body><h1>Hi</h1><p>There</p></body></html>"
        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.success("https://example.com/", html, content_type="text/html"),
        )
        out = WebSearchClient().fetch("https://example.com/")
        assert "Hi" in out
        assert "There" in out

    def test_github_readme_shortcut(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[tuple] = []

        def fake_fetch(url, timeout, max_b, max_pdf, extra_headers=None, **kwargs):
            calls.append((url, extra_headers))
            if "api.github.com" in url:
                return FetchResult.success(url, "# Repo\n\nHello", content_type="text/plain", status_code=200)
            return FetchResult.failure(url, "should not hit", ErrorCategory.UNKNOWN)

        monkeypatch.setattr("websift.providers.base.fetch_raw", fake_fetch)
        out = WebSearchClient().fetch("https://github.com/python/cpython")
        assert "README of https://github.com/python/cpython" in out
        assert "Hello" in out
        assert calls
        assert "api.github.com/repos/python/cpython/readme" in calls[0][0]
        assert calls[0][1]["Accept"] == "application/vnd.github.raw+json"
        # Non-credential headers only
        assert "Authorization" not in (calls[0][1] or {})

    def test_github_non_repo_paths_skip_shortcut(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.success(a[0], "page", content_type="text/plain"),
        )
        assert github_readme_api_url("https://github.com/features") is None
        assert github_readme_api_url("https://gitlab.com/a/b") is None
        assert github_readme_api_url("https://github.com/a/b/c") is None
        assert github_readme_api_url("https://github.com/topics/x") is None

    def test_github_strips_git_suffix(self):
        url = github_readme_api_url("https://github.com/foo/bar.git")
        assert url == "https://api.github.com/repos/foo/bar/readme"

    def test_truncation_applied(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.success("https://example.com/", "x" * 1000, content_type="text/plain"),
        )
        out = WebSearchClient(max_page_chars=50).fetch("https://example.com/")
        assert "truncated" in out

    def test_github_readme_fallback_to_page_when_api_empty(self, monkeypatch: pytest.MonkeyPatch):
        def fake_fetch(url, timeout, max_b, max_pdf, extra_headers=None, **kwargs):
            if "api.github.com" in url:
                return FetchResult.success(url, "   ", content_type="text/plain")
            return FetchResult.success(url, "html-page", content_type="text/plain")

        monkeypatch.setattr("websift.providers.base.fetch_raw", fake_fetch)
        out = WebSearchClient().fetch("https://github.com/foo/bar")
        assert out == "html-page"

    def test_github_invalid_owner_chars(self):
        assert github_readme_api_url("https://github.com/foo bar/baz") is None


class TestFormatters:
    def test_format_search_success(self):
        resp = SearchResponse(
            request=SearchRequest(query="q", max_results=2),
            results=(SearchResult(title="T", url="https://e/", snippet="S", rank=1, source="ddgs"),),
        )
        out = format_search_response(resp)
        assert "Title: T" in out
        assert "Call fetch(url)" in out

    def test_format_search_errors(self):
        req = SearchRequest(query="", max_results=5)
        assert (
            format_search_response(SearchResponse(request=req, error_category=ErrorCategory.EMPTY_INPUT))
            == "No query provided."
        )
        assert "ddgs not installed" in format_search_response(
            SearchResponse(
                request=req,
                error_category=ErrorCategory.PROVIDER_IMPORT,
                error_message="Error: ddgs not installed. Run: pip install ddgs",
            )
        )
        assert format_search_response(SearchResponse(request=req, results=())) == "No results found."

    def test_format_fetch_error_and_success(self):
        assert format_fetch_result(FetchResult.failure("u", "Blocked: x", ErrorCategory.BLOCKED)) == "Blocked: x"
        assert format_fetch_result(FetchResult.success("u", "body")) == "body"

    def test_process_fetched_body_html_and_text(self):
        text, truncated = process_fetched_body(
            "<html><body><h1>X</h1><p>Y</p></body></html>",
            "text/html",
            max_page_chars=10_000,
        )
        assert "X" in text and "Y" in text
        assert truncated is False
        plain, truncated2 = process_fetched_body("hello", "text/plain", max_page_chars=10)
        assert plain == "hello"
        assert truncated2 is False


class TestStructuredInternals:
    def test_search_structured_categories(self, monkeypatch: pytest.MonkeyPatch):
        empty = WebSearchClient().search_structured("")
        assert empty.error_category == ErrorCategory.EMPTY_INPUT
        assert not empty.ok

        import sys
        import types

        class FakeDDGS:
            def __init__(self, timeout=None):
                pass

            def text(self, query, max_results=5):
                return [{"title": "A", "href": "https://a/", "body": "b"}]

        mod = types.ModuleType("ddgs")
        mod.DDGS = FakeDDGS
        monkeypatch.setitem(sys.modules, "ddgs", mod)
        ok = WebSearchClient().search_structured("q")
        assert ok.ok
        assert ok.results[0].source == "ddgs"
        assert ok.results[0].rank == 1

    def test_fetch_structured_categories(self, monkeypatch: pytest.MonkeyPatch):
        empty = WebSearchClient().fetch_structured("")
        assert empty.error_category == ErrorCategory.EMPTY_INPUT

        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.failure(
                a[0],
                "(content exceeds download limit of 1 bytes)",
                ErrorCategory.OVERFLOW,
                overflow=True,
            ),
        )
        overflow = WebSearchClient().fetch_structured("https://example.com/")
        assert overflow.error_category == ErrorCategory.OVERFLOW
        assert overflow.overflow is True
        assert not overflow.ok

        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.failure(a[0], "Failed to fetch URL: timeout (x)", ErrorCategory.TIMEOUT),
        )
        timeout = WebSearchClient().fetch_structured("https://example.com/")
        assert timeout.error_category == ErrorCategory.TIMEOUT

        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.failure(
                a[0], "Failed to fetch URL: HTTP 401", ErrorCategory.AUTH, status_code=401
            ),
        )
        auth = WebSearchClient().fetch_structured("https://example.com/")
        assert auth.error_category == ErrorCategory.AUTH

        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.failure(
                a[0], "(non-text content: image/png)", ErrorCategory.UNSUPPORTED, content_type="image/png"
            ),
        )
        unsup = WebSearchClient().fetch_structured("https://example.com/")
        assert unsup.error_category == ErrorCategory.UNSUPPORTED

        monkeypatch.setattr(
            "websift.providers.base.fetch_raw",
            lambda *a, **k: FetchResult.success(
                a[0], "ok-body", content_type="text/plain", status_code=200, bytes_read=7
            ),
        )
        ok = WebSearchClient().fetch_structured("https://example.com/")
        assert ok.ok
        assert ok.content == "ok-body"
        assert ok.bytes_read == 7
        assert ok.truncated is False
