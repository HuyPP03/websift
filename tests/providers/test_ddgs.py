"""DDGS provider characterization via WebSearchClient (pre-provider-architecture)."""

from __future__ import annotations

import sys
import types

import pytest

from web_search.client import WebSearchClient


@pytest.fixture
def mock_ddgs(monkeypatch: pytest.MonkeyPatch):
    created = {}

    class FakeDDGS:
        def __init__(self, timeout=None):
            created["timeout"] = timeout

        def text(self, query, max_results=5):
            created["query"] = query
            created["max_results"] = max_results
            return [
                {
                    "title": "Python Docs",
                    "href": "https://docs.python.org/3/",
                    "body": "Official documentation",
                }
            ]

    mod = types.ModuleType("ddgs")
    mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", mod)
    return created


def test_ddgs_receives_timeout_and_max_results(mock_ddgs):
    client = WebSearchClient(max_results=4, timeout=9)
    out = client.search("  python typing  ")
    assert mock_ddgs["timeout"] == 9
    assert mock_ddgs["max_results"] == 4
    assert mock_ddgs["query"] == "python typing"
    assert "Python Docs" in out
    assert "https://docs.python.org/3/" in out
    assert "Official documentation" in out


def test_ddgs_field_mapping_title_href_body(mock_ddgs):
    out = WebSearchClient().search("x")
    assert "Title: Python Docs" in out
    assert "URL: https://docs.python.org/3/" in out
    assert "Snippet: Official documentation" in out


@pytest.mark.live
def test_live_ddgs_smoke():
    """Optional live smoke; excluded from default suite."""
    out = WebSearchClient(max_results=1, timeout=20).search("python")
    assert isinstance(out, str)
    assert out
    assert "No query" not in out
