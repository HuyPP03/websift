"""Model to_dict JSON payloads."""

from __future__ import annotations

from websift.models import FetchResult, SearchRequest, SearchResponse, SearchResult


def test_search_result_to_dict():
    r = SearchResult(title="T", url="https://x", snippet="S", rank=1, source="ddgs")
    d = r.to_dict()
    assert d == {
        "title": "T",
        "url": "https://x",
        "snippet": "S",
        "rank": 1,
        "source": "ddgs",
    }


def test_search_response_to_dict_ok():
    resp = SearchResponse(
        request=SearchRequest(query="q", max_results=3),
        results=(SearchResult(title="T", url="https://x", snippet="S"),),
    )
    d = resp.to_dict()
    assert d["ok"] is True
    assert d["query"] == "q"
    assert d["max_results"] == 3
    assert d["error"] is None
    assert d["results"][0]["title"] == "T"


def test_search_response_to_dict_error():
    resp = SearchResponse(
        request=SearchRequest(query="q", max_results=1),
        error_category="rate_limit",
        error_message="Search failed: limited",
    )
    d = resp.to_dict()
    assert d["ok"] is False
    assert d["results"] == []
    assert d["error"]["category"] == "rate_limit"
    assert "limited" in d["error"]["message"]


def test_fetch_result_to_dict_ok():
    r = FetchResult.success(
        "https://example.com",
        "hello",
        final_url="https://example.com/",
        content_type="text/html",
        status_code=200,
        bytes_read=5,
        redirect_count=1,
        truncated=True,
    )
    d = r.to_dict()
    assert d["ok"] is True
    assert d["url"] == "https://example.com"
    assert d["final_url"] == "https://example.com/"
    assert d["content"] == "hello"
    assert d["status_code"] == 200
    assert d["truncated"] is True
    assert d["error"] is None


def test_fetch_result_to_dict_error():
    r = FetchResult.failure("https://x", "No URL provided.", "empty_input")
    d = r.to_dict()
    assert d["ok"] is False
    assert d["content"] == ""
    assert d["error"]["category"] == "empty_input"
