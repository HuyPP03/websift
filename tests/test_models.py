"""Unit tests for structured models and error classification."""

from __future__ import annotations

from web_search.models import (
    ErrorCategory,
    FetchResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
    classify_error_message,
    classify_http_status,
)


def test_fetch_result_ok_and_factories():
    ok = FetchResult.success("https://a/", "body", content_type="text/plain", status_code=200, bytes_read=4)
    assert ok.ok
    assert ok.error_category is None
    assert ok.content == "body"

    bad = FetchResult.failure("https://a/", "Blocked: x", ErrorCategory.BLOCKED)
    assert not bad.ok
    assert bad.error_category == ErrorCategory.BLOCKED
    assert bad.final_url == "https://a/"


def test_search_response_ok():
    req = SearchRequest(query="q", max_results=3)
    resp = SearchResponse(request=req, results=(SearchResult("t", "u", "s", rank=1),))
    assert resp.ok
    assert not SearchResponse(request=req, error_category=ErrorCategory.PROVIDER).ok


def test_classify_http_status():
    assert classify_http_status(401) == ErrorCategory.AUTH
    assert classify_http_status(403) == ErrorCategory.AUTH
    assert classify_http_status(429) == ErrorCategory.RATE_LIMIT
    assert classify_http_status(503) == ErrorCategory.UNAVAILABLE
    assert classify_http_status(404) == ErrorCategory.HTTP_ERROR


def test_classify_error_message():
    assert classify_error_message("Blocked: non-global IP") == ErrorCategory.BLOCKED
    assert classify_error_message("Failed to fetch URL: timeout (x)") == ErrorCategory.TIMEOUT
    assert classify_error_message("(content exceeds download limit of 10 bytes)") == ErrorCategory.OVERFLOW
    assert classify_error_message("(binary content, 12 bytes)") == ErrorCategory.UNSUPPORTED
    assert classify_error_message("Unsupported Content-Encoding: br") == ErrorCategory.DECODE
    assert classify_error_message("Failed to fetch: too many redirects.") == ErrorCategory.REDIRECT
    assert classify_error_message("Failed to fetch URL: HTTP 429") == ErrorCategory.RATE_LIMIT
    assert classify_error_message("Failed to fetch URL: HTTP 500") == ErrorCategory.UNAVAILABLE
