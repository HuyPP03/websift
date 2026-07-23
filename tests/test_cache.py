"""In-memory TTL/LRU cache unit + client integration tests."""

from __future__ import annotations

import time

from websift.cache import (
    TtlLruCache,
    estimate_fetch_result_size,
    estimate_search_response_size,
    make_fetch_cache_key,
    make_search_cache_key,
)
from websift.client import WebSearchClient
from websift.models import FetchResult, SearchRequest, SearchResponse, SearchResult
from websift.settings import AppSettings, CacheSettings


def test_ttl_lru_basic_get_set():
    cache: TtlLruCache[str] = TtlLruCache(max_entries=4, max_bytes=10_000)
    assert cache.get("a") is None
    assert cache.set("a", "hello", ttl_seconds=60, size=5) is True
    assert cache.get("a") == "hello"
    assert len(cache) == 1


def test_ttl_lru_expires(monkeypatch):
    cache: TtlLruCache[str] = TtlLruCache(max_entries=4, max_bytes=10_000)
    mono = {"t": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: mono["t"])
    assert cache.set("k", "v", ttl_seconds=10, size=1) is True
    assert cache.get("k") == "v"
    mono["t"] = 1011.0
    assert cache.get("k") is None
    assert len(cache) == 0


def test_ttl_lru_evicts_by_entry_count():
    cache: TtlLruCache[str] = TtlLruCache(max_entries=2, max_bytes=10_000)
    cache.set("a", "1", ttl_seconds=60, size=1)
    cache.set("b", "2", ttl_seconds=60, size=1)
    cache.set("c", "3", ttl_seconds=60, size=1)
    assert cache.get("a") is None
    assert cache.get("b") == "2"
    assert cache.get("c") == "3"


def test_ttl_lru_evicts_by_bytes():
    cache: TtlLruCache[str] = TtlLruCache(max_entries=10, max_bytes=10)
    cache.set("a", "1", ttl_seconds=60, size=6)
    cache.set("b", "2", ttl_seconds=60, size=6)
    assert cache.get("a") is None
    assert cache.get("b") == "2"


def test_ttl_zero_skips_store():
    cache: TtlLruCache[str] = TtlLruCache()
    assert cache.set("a", "x", ttl_seconds=0, size=1) is False
    assert cache.get("a") is None


def test_ttl_lru_overwrite_and_clear():
    cache: TtlLruCache[str] = TtlLruCache(max_entries=4, max_bytes=1000)
    cache.set("a", "one", ttl_seconds=60, size=3)
    cache.set("a", "two", ttl_seconds=60, size=3)
    assert cache.get("a") == "two"
    assert cache.size_bytes == 3
    cache.clear()
    assert len(cache) == 0
    assert cache.size_bytes == 0


def test_ttl_lru_rejects_oversized_entry():
    cache: TtlLruCache[str] = TtlLruCache(max_entries=4, max_bytes=10)
    assert cache.set("huge", "x", ttl_seconds=60, size=100) is False
    assert len(cache) == 0


def test_approx_size_via_default_estimate():
    cache: TtlLruCache[object] = TtlLruCache(max_entries=4, max_bytes=10_000)
    assert cache.set("obj", {"k": "v"}, ttl_seconds=30) is True
    assert cache.get("obj") == {"k": "v"}


def test_estimate_with_error_message():
    resp = SearchResponse(
        request=SearchRequest(query="q", max_results=1),
        error_category="provider",
        error_message="boom",
    )
    assert estimate_search_response_size(resp) > 0


def test_cache_key_helpers_stable():
    req = SearchRequest(query="q", max_results=3, region="us-en")
    k1 = make_search_cache_key(req, provider="ddgs")
    k2 = make_search_cache_key(req, provider="ddgs")
    k3 = make_search_cache_key(req, provider="brave")
    assert k1 == k2
    assert k1 != k3
    f1 = make_fetch_cache_key(
        "https://example.com",
        max_page_chars=1000,
        include_links=True,
        include_images=False,
        output_format="markdown",
        native_fetch=True,
        allow_http=True,
        provider="ddgs",
    )
    f2 = make_fetch_cache_key(
        "https://example.com",
        max_page_chars=1000,
        include_links=True,
        include_images=False,
        output_format="markdown",
        native_fetch=True,
        allow_http=True,
        provider="ddgs",
    )
    assert f1 == f2


def test_estimate_sizes_positive():
    resp = SearchResponse(
        request=SearchRequest(query="q", max_results=1),
        results=(SearchResult(title="t", url="https://x", snippet="s", rank=1),),
    )
    fetch = FetchResult.success("https://x", "body" * 20, final_url="https://x/", status_code=200)
    assert estimate_search_response_size(resp) > 0
    assert estimate_fetch_result_size(fetch) > 0


def test_client_cache_disabled_by_default():
    client = WebSearchClient()
    assert client._cache is None


def test_client_search_cache_hits(monkeypatch):
    calls = {"n": 0}

    class FakeProvider:
        name = "fake"

        def search(self, request):
            calls["n"] += 1
            return [
                SearchResult(
                    title="T",
                    url="https://example.com/",
                    snippet="S",
                    rank=1,
                    source="fake",
                )
            ]

        def fetch(self, url: str):
            calls["n"] += 1
            return FetchResult.success(url, "content body", final_url=url, status_code=200)

    settings = AppSettings(
        cache=CacheSettings(enabled=True, search_ttl_seconds=300, fetch_ttl_seconds=300, max_entries=32)
    )
    client = WebSearchClient(settings=settings, provider=FakeProvider())
    assert client._cache is not None

    r1 = client.search_structured("hello")
    r2 = client.search_structured("hello")
    assert r1.ok and r2.ok
    assert calls["n"] == 1  # second call served from cache
    assert r1.results[0].title == r2.results[0].title

    f1 = client.fetch_structured("https://example.com/page")
    f2 = client.fetch_structured("https://example.com/page")
    assert f1.ok and f2.ok
    assert calls["n"] == 2  # one search + one fetch


def test_client_does_not_cache_errors():
    class BoomProvider:
        name = "boom"

        def search(self, request):
            raise RuntimeError("rate limit 429")

        def fetch(self, url: str):
            raise RuntimeError("fail")

    settings = AppSettings(cache=CacheSettings(enabled=True, search_ttl_seconds=60, fetch_ttl_seconds=60))
    client = WebSearchClient(settings=settings, provider=BoomProvider())
    a = client.search_structured("q")
    b = client.search_structured("q")
    assert not a.ok and not b.ok
    # Cache should remain empty for failures
    assert client._cache is not None
    assert len(client._cache) == 0
