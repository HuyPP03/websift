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
    timeout_seconds: float,
    max_bytes: int,
    max_pdf_bytes: int,
    max_redirects: int,
    max_compressed_bytes: int,
    max_decompressed_bytes: int,
    pdf_max_pages: int,
    pdf_max_chars: int,
    allow_http: bool,
    allowed_ports: frozenset[int],
    allowed_domains: frozenset[str],
    denied_domains: frozenset[str],
    max_page_chars: int,
    min_main_content_chars: int,
    include_links: bool,
    include_images: bool,
    output_format: str,
    native_fetch: bool,
    backend: str,
    provider: str,
    implementation_fingerprint: str,
) -> str:
    return _digest(
        "fetch-v2",
        provider,
        url,
        timeout_seconds,
        max_bytes,
        max_pdf_bytes,
        max_redirects,
        max_compressed_bytes,
        max_decompressed_bytes,
        pdf_max_pages,
        pdf_max_chars,
        allow_http,
        tuple(sorted(allowed_ports)),
        tuple(sorted(allowed_domains)),
        tuple(sorted(denied_domains)),
        max_page_chars,
        min_main_content_chars,
        include_links,
        include_images,
        output_format,
        native_fetch,
        backend,
        implementation_fingerprint,
    )


def _digest(*parts: object) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(repr(part).encode("utf-8", errors="replace"))
        h.update(b"\0")
    return h.hexdigest()


class DiskTtlCache(Generic[T]):
    """Opt-in on-disk TTL cache (stdlib JSON files). Survives process restarts.

    Values must be ``SearchResponse`` or ``FetchResult`` (round-tripped via
    ``to_dict`` / ``from_dict``). Keys are hashed so paths stay safe.
    """

    def __init__(
        self,
        directory: str,
        *,
        max_entries: int = 256,
        max_bytes: int = 32 * 1024 * 1024,
    ):
        import os
        from pathlib import Path as _Path

        self._root = _Path(os.path.expanduser(str(directory))).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._max_entries = max(1, int(max_entries))
        self._max_bytes = max(1, int(max_bytes))
        self._lock = threading.RLock()
        self._index_name = ".websift-cache-index.json"

    @property
    def size_bytes(self) -> int:
        with self._lock:
            return int(self._load_index().get("bytes", 0))

    def __len__(self) -> int:
        with self._lock:
            return len(self._load_index().get("entries", {}))

    def clear(self) -> None:
        with self._lock:
            for path in self._root.glob("*.json"):
                if path.name == self._index_name:
                    continue
                try:
                    path.unlink()
                except OSError:
                    pass
            self._write_index({"bytes": 0, "entries": {}})

    def get(self, key: str) -> T | None:
        import json

        now = time.time()
        with self._lock:
            index = self._load_index()
            meta = (index.get("entries") or {}).get(key)
            if not meta:
                return None
            expires_at = float(meta.get("expires_at", 0))
            path = self._root / str(meta.get("file", ""))
            if expires_at <= now or not path.is_file():
                self._drop_locked(index, key)
                self._write_index(index)
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                self._drop_locked(index, key)
                self._write_index(index)
                return None
            kind = payload.get("kind")
            data = payload.get("data")
            if not isinstance(data, dict):
                self._drop_locked(index, key)
                self._write_index(index)
                return None
            # touch LRU order
            meta["last_access"] = now
            index["entries"][key] = meta
            self._write_index(index)
            if kind == "search":
                return SearchResponse.from_dict(data)  # type: ignore[return-value]
            if kind == "fetch":
                return FetchResult.from_dict(data)  # type: ignore[return-value]
            return None

    def set(self, key: str, value: T, *, ttl_seconds: float, size: int | None = None) -> bool:
        import json

        ttl = float(ttl_seconds)
        if ttl <= 0:
            return False
        kind, data = _serialize_cache_value(value)
        if kind is None or data is None:
            return False
        est = max(1, int(size) if size is not None else _approx_size(value))
        if est > self._max_bytes:
            return False
        expires_at = time.time() + ttl
        file_name = f"{_digest(key)[:40]}.json"
        path = self._root / file_name
        with self._lock:
            index = self._load_index()
            if key in (index.get("entries") or {}):
                self._drop_locked(index, key)
            # Evict until we have room.
            while index.get("entries") and (
                len(index["entries"]) >= self._max_entries or int(index.get("bytes", 0)) + est > self._max_bytes
            ):
                # LRU by last_access
                oldest_key = min(
                    index["entries"].items(),
                    key=lambda kv: float(kv[1].get("last_access", 0)),
                )[0]
                self._drop_locked(index, oldest_key)
            if int(index.get("bytes", 0)) + est > self._max_bytes:
                return False
            try:
                path.write_text(
                    json.dumps({"kind": kind, "data": data}, ensure_ascii=False),
                    encoding="utf-8",
                )
            except OSError:
                return False
            index.setdefault("entries", {})[key] = {
                "file": file_name,
                "expires_at": expires_at,
                "size": est,
                "last_access": time.time(),
            }
            index["bytes"] = int(index.get("bytes", 0)) + est
            self._write_index(index)
            return True

    def _load_index(self) -> dict:
        import json

        path = self._root / self._index_name
        if not path.is_file():
            return {"bytes": 0, "entries": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {"bytes": 0, "entries": {}}
        if not isinstance(data, dict):
            return {"bytes": 0, "entries": {}}
        data.setdefault("bytes", 0)
        data.setdefault("entries", {})
        if not isinstance(data["entries"], dict):
            data["entries"] = {}
        return data

    def _write_index(self, index: dict) -> None:
        import json

        path = self._root / self._index_name
        tmp = self._root / (self._index_name + ".tmp")
        try:
            tmp.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass

    def _drop_locked(self, index: dict, key: str) -> None:
        meta = (index.get("entries") or {}).pop(key, None)
        if not meta:
            return
        index["bytes"] = max(0, int(index.get("bytes", 0)) - int(meta.get("size", 0)))
        path = self._root / str(meta.get("file", ""))
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass


def _serialize_cache_value(value: object) -> tuple[str | None, dict | None]:
    if isinstance(value, SearchResponse):
        return "search", value.to_dict()
    if isinstance(value, FetchResult):
        return "fetch", value.to_dict()
    return None, None
