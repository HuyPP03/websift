"""Opt-in in-memory TTL + LRU cache for search/fetch results."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, TypeVar

from websift.models import FetchResult, SearchRequest, SearchResponse

T = TypeVar("T")


@dataclass(frozen=True)
class _Entry(Generic[T]):
    value: T
    expires_at: float
    size: int


class TtlLruCache(Generic[T]):
    """Thread-safe in-memory cache with per-entry TTL and global LRU eviction."""

    def __init__(self, *, max_entries: int = 256, max_bytes: int = 32 * 1024 * 1024):
        self._max_entries = max(1, int(max_entries))
        self._max_bytes = max(1, int(max_bytes))
        self._data: OrderedDict[str, _Entry[T]] = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()

    @property
    def size_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._bytes = 0

    def get(self, key: str) -> T | None:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._drop(key)
                return None
            self._data.move_to_end(key)
            return entry.value

    def set(self, key: str, value: T, *, ttl_seconds: float, size: int | None = None) -> bool:
        """Store ``value`` under ``key``. Returns False if skipped (TTL/size)."""
        ttl = float(ttl_seconds)
        if ttl <= 0:
            return False
        est = max(1, int(size) if size is not None else _approx_size(value))
        if est > self._max_bytes:
            return False
        expires_at = time.monotonic() + ttl
        with self._lock:
            if key in self._data:
                self._drop(key)
            while self._data and (len(self._data) >= self._max_entries or self._bytes + est > self._max_bytes):
                oldest, _ = next(iter(self._data.items()))
                self._drop(oldest)
            if self._bytes + est > self._max_bytes:
                return False
            self._data[key] = _Entry(value=value, expires_at=expires_at, size=est)
            self._bytes += est
            return True

    def _drop(self, key: str) -> None:
        entry = self._data.pop(key, None)
        if entry is not None:
            self._bytes = max(0, self._bytes - entry.size)


def _approx_size(value: object) -> int:
    if isinstance(value, SearchResponse):
        return estimate_search_response_size(value)
    if isinstance(value, FetchResult):
        return estimate_fetch_result_size(value)
    try:
        return max(1, len(repr(value)))
    except Exception:
        return 64


def estimate_search_response_size(response: SearchResponse) -> int:
    n = 128
    for r in response.results:
        n += len(r.title or "") + len(r.url or "") + len(r.snippet or "") + 48
    if response.error_message:
        n += len(response.error_message)
    return max(1, n)


def estimate_fetch_result_size(result: FetchResult) -> int:
    return max(
        1,
        256
        + len(result.content or "")
        + len(result.requested_url or "")
        + len(result.final_url or "")
        + len(result.content_type or "")
        + len(result.error_message or ""),
    )


def make_search_cache_key(request: SearchRequest, *, provider: str) -> str:
    return _digest(
        "search",
        provider,
        request.query,
        request.max_results,
        request.safe_search or "",
        request.region or "",
        request.time_range or "",
    )


def make_fetch_cache_key(
    url: str,
    *,
    max_page_chars: int,
    include_links: bool,
    include_images: bool,
    output_format: str,
    native_fetch: bool,
    allow_http: bool,
    provider: str,
) -> str:
    return _digest(
        "fetch",
        provider,
        url,
        max_page_chars,
        include_links,
        include_images,
        output_format,
        native_fetch,
        allow_http,
    )


def _digest(*parts: object) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(repr(part).encode("utf-8", errors="replace"))
        h.update(b"\0")
    return h.hexdigest()
