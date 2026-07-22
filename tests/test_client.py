"""WebSearchClient public API characterization (mocked network)."""

from __future__ import annotations

import pytest

from web_search.client import WebSearchClient


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
        import types
        import sys

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
        import types
        import sys

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
        assert "rate limited" in out


class TestFetch:
    def test_empty_url(self):
        assert WebSearchClient().fetch("") == "No URL provided."
        assert WebSearchClient().fetch("  ") == "No URL provided."

    def test_fetch_error_passthrough(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.client.fetch_raw",
            lambda *a, **k: ("Blocked: private", "", ""),
        )
        assert WebSearchClient().fetch("http://x/") == "Blocked: private"

    def test_fetch_plain_text(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.client.fetch_raw",
            lambda *a, **k: (None, "plain body", "text/plain"),
        )
        out = WebSearchClient().fetch("https://example.com/a.txt")
        assert out == "plain body"

    def test_fetch_html_converted(self, monkeypatch: pytest.MonkeyPatch):
        # Headings are emitted; <p> text is a known v0.1.0 converter gap.
        html = "<html><body><h1>Hi</h1><p>There</p></body></html>"
        monkeypatch.setattr(
            "web_search.client.fetch_raw",
            lambda *a, **k: (None, html, "text/html"),
        )
        out = WebSearchClient().fetch("https://example.com/")
        assert "Hi" in out

    def test_github_readme_shortcut(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[tuple] = []

        def fake_fetch(url, timeout, max_b, max_pdf, extra_headers=None):
            calls.append((url, extra_headers))
            if "api.github.com" in url:
                return None, "# Repo\n\nHello", "text/plain"
            return "should not hit", "", ""

        monkeypatch.setattr("web_search.client.fetch_raw", fake_fetch)
        out = WebSearchClient().fetch("https://github.com/python/cpython")
        assert "README of https://github.com/python/cpython" in out
        assert "Hello" in out
        assert calls
        assert "api.github.com/repos/python/cpython/readme" in calls[0][0]
        assert calls[0][1]["Accept"] == "application/vnd.github.raw+json"

    def test_github_non_repo_paths_skip_shortcut(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.client.fetch_raw",
            lambda *a, **k: (None, "page", "text/plain"),
        )
        client = WebSearchClient()
        assert client._github_readme_api_url("https://github.com/features") is None
        assert client._github_readme_api_url("https://gitlab.com/a/b") is None
        assert client._github_readme_api_url("https://github.com/a/b/c") is None
        assert client._github_readme_api_url("https://github.com/topics/x") is None

    def test_github_strips_git_suffix(self):
        url = WebSearchClient()._github_readme_api_url("https://github.com/foo/bar.git")
        assert url == "https://api.github.com/repos/foo/bar/readme"

    def test_truncation_applied(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.client.fetch_raw",
            lambda *a, **k: (None, "x" * 1000, "text/plain"),
        )
        out = WebSearchClient(max_page_chars=50).fetch("https://example.com/")
        assert "truncated" in out

    def test_github_readme_fallback_to_page_when_api_empty(self, monkeypatch: pytest.MonkeyPatch):
        def fake_fetch(url, timeout, max_b, max_pdf, extra_headers=None):
            if "api.github.com" in url:
                return None, "   ", "text/plain"
            return None, "html-page", "text/plain"

        monkeypatch.setattr("web_search.client.fetch_raw", fake_fetch)
        out = WebSearchClient().fetch("https://github.com/foo/bar")
        assert out == "html-page"

    def test_github_invalid_owner_chars(self):
        assert WebSearchClient()._github_readme_api_url("https://github.com/foo bar/baz") is None
