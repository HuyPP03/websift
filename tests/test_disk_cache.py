"""Disk TTL cache tests."""

from __future__ import annotations

import json
import time

from websift.cache import DiskTtlCache, _serialize_cache_value
from websift.client import WebSearchClient
from websift.models import FetchResult, SearchRequest, SearchResponse, SearchResult
from websift.settings import AppSettings, CacheSettings, ProviderSettings


def _search_resp(query: str = "q") -> SearchResponse:
    return SearchResponse(
        request=SearchRequest(query=query, max_results=3),
        results=(SearchResult(title="T", url="https://x", snippet="S", rank=1, source="ddgs"),),
    )


def _fetch_resp(url: str = "https://example.com/") -> FetchResult:
    return FetchResult(
        requested_url=url,
        final_url=url,
        content="body",
        content_type="text/html",
        status_code=200,
    )


def test_disk_cache_roundtrip(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=1_000_000)
    resp = _search_resp()
    assert cache.set("k1", resp, ttl_seconds=60) is True
    hit = cache.get("k1")
    assert isinstance(hit, SearchResponse)
    assert hit.request.query == "q"
    assert hit.results[0].title == "T"
    assert len(cache) == 1
    assert cache.size_bytes > 0


def test_disk_cache_fetch_roundtrip(tmp_path):
    cache: DiskTtlCache[FetchResult] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=1_000_000)
    resp = _fetch_resp()
    assert cache.set("fk", resp, ttl_seconds=30) is True
    hit = cache.get("fk")
    assert isinstance(hit, FetchResult)
    assert hit.content == "body"
    assert hit.requested_url == "https://example.com/"


def test_disk_cache_expires(tmp_path, monkeypatch):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=1_000_000)
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(time, "time", lambda: now["t"])
    resp = SearchResponse(request=SearchRequest(query="q", max_results=1), results=())
    assert cache.set("k", resp, ttl_seconds=10) is True
    assert cache.get("k") is not None
    now["t"] = 1_000_020.0
    assert cache.get("k") is None


def test_disk_cache_ttl_zero_skips(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path))
    assert cache.set("k", _search_resp(), ttl_seconds=0) is False
    assert cache.get("k") is None


def test_disk_cache_rejects_unknown_type(tmp_path):
    cache: DiskTtlCache[object] = DiskTtlCache(str(tmp_path))
    assert cache.set("k", {"not": "supported"}, ttl_seconds=10) is False
    assert _serialize_cache_value("x") == (None, None)


def test_disk_cache_evicts_by_max_entries(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=2, max_bytes=1_000_000)
    assert cache.set("a", _search_resp("a"), ttl_seconds=60) is True
    time.sleep(0.01)
    assert cache.set("b", _search_resp("b"), ttl_seconds=60) is True
    time.sleep(0.01)
    # Touch "a" so "b" is older by last_access when we insert "c".
    assert cache.get("a") is not None
    time.sleep(0.01)
    assert cache.set("c", _search_resp("c"), ttl_seconds=60) is True
    assert len(cache) == 2
    assert cache.get("b") is None  # LRU victim
    assert cache.get("a") is not None
    assert cache.get("c") is not None


def test_disk_cache_oversized_entry_skipped(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=50)
    # Force size argument larger than max_bytes.
    assert cache.set("big", _search_resp(), ttl_seconds=60, size=10_000) is False
    assert cache.get("big") is None


def test_disk_cache_corrupt_payload_drops(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=1_000_000)
    assert cache.set("k", _search_resp(), ttl_seconds=60) is True
    # Corrupt the payload file while keeping index.
    for path in tmp_path.glob("*.json"):
        if path.name.startswith("."):
            continue
        path.write_text("{not-json", encoding="utf-8")
        break
    assert cache.get("k") is None


def test_disk_cache_missing_file_drops(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=1_000_000)
    assert cache.set("k", _search_resp(), ttl_seconds=60) is True
    for path in tmp_path.glob("*.json"):
        if path.name.startswith("."):
            continue
        path.unlink()
        break
    assert cache.get("k") is None


def test_disk_cache_clear(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=1_000_000)
    assert cache.set("k1", _search_resp("1"), ttl_seconds=60) is True
    assert cache.set("k2", _search_resp("2"), ttl_seconds=60) is True
    cache.clear()
    assert len(cache) == 0
    assert cache.get("k1") is None
    assert cache.size_bytes == 0


def test_disk_cache_corrupt_index_resets(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=1_000_000)
    index = tmp_path / ".websift-cache-index.json"
    index.write_text("not-json", encoding="utf-8")
    assert len(cache) == 0
    assert cache.set("k", _search_resp(), ttl_seconds=60) is True
    assert cache.get("k") is not None


def test_disk_cache_bad_kind_payload(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=1_000_000)
    assert cache.set("k", _search_resp(), ttl_seconds=60) is True
    for path in tmp_path.glob("*.json"):
        if path.name.startswith("."):
            continue
        path.write_text(json.dumps({"kind": "other", "data": {"query": "q"}}), encoding="utf-8")
        break
    assert cache.get("k") is None


def test_disk_cache_replace_existing_key(tmp_path):
    cache: DiskTtlCache[SearchResponse] = DiskTtlCache(str(tmp_path), max_entries=8, max_bytes=1_000_000)
    assert cache.set("k", _search_resp("old"), ttl_seconds=60) is True
    assert cache.set("k", _search_resp("new"), ttl_seconds=60) is True
    hit = cache.get("k")
    assert hit is not None
    assert hit.request.query == "new"
    assert len(cache) == 1


def test_client_disk_cache_integration(tmp_path, monkeypatch):
    calls = {"n": 0}

    class _P:
        name = "fake"
        capabilities = type(
            "C",
            (),
            {"safe_search": False, "region": False, "time_range": False, "pagination": False, "domain_filter": False},
        )()

        def search(self, request):
            calls["n"] += 1
            return [SearchResult(title="Hit", url="https://h.example", snippet="s", rank=1, source="fake")]

        def fetch(self, url):
            raise NotImplementedError

    settings = AppSettings(
        provider=ProviderSettings(name="ddgs"),
        cache=CacheSettings(
            enabled=True, backend="disk", directory=str(tmp_path), search_ttl_seconds=60, fetch_ttl_seconds=60
        ),
    )
    client = WebSearchClient(settings=settings, provider=_P())
    a = client.search_structured("hello")
    b = client.search_structured("hello")
    assert a.ok and b.ok
    assert calls["n"] == 1


def test_settings_disk_requires_dir():
    s = AppSettings(cache=CacheSettings(enabled=True, backend="disk", directory=None))
    try:
        s.validate()
        raise AssertionError("expected SettingsError")
    except Exception as e:
        assert "CACHE_DIR" in str(e) or getattr(e, "code", "") == "missing_cache_dir"
