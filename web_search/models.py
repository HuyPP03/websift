"""Structured request/result models and error categories."""

from __future__ import annotations

from dataclasses import dataclass


class ErrorCategory:
    """Stable internal error taxonomy (not a public string API)."""

    EMPTY_INPUT = "empty_input"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    UNAVAILABLE = "unavailable"
    OVERFLOW = "overflow"
    UNSUPPORTED = "unsupported_content"
    EMPTY_CONTENT = "empty_content"
    HTTP_ERROR = "http_error"
    NETWORK = "network"
    DECODE = "decode"
    REDIRECT = "redirect"
    PROVIDER = "provider"
    PROVIDER_IMPORT = "provider_import"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SearchRequest:
    query: str
    max_results: int
    safe_search: str | None = None
    region: str | None = None
    time_range: str | None = None


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    rank: int | None = None
    source: str | None = None


@dataclass(frozen=True)
class SearchResponse:
    """Internal search outcome; public API still formats this to ``str``."""

    request: SearchRequest
    results: tuple[SearchResult, ...] = ()
    error_category: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_category is None


@dataclass(frozen=True)
class FetchResult:
    """Internal fetch outcome for HTTP + client body pipeline."""

    requested_url: str
    final_url: str = ""
    content: str = ""
    content_type: str = ""
    status_code: int | None = None
    bytes_read: int = 0
    redirect_count: int = 0
    truncated: bool = False
    overflow: bool = False
    error_category: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_category is None

    @classmethod
    def failure(
        cls,
        requested_url: str,
        message: str,
        category: str,
        *,
        final_url: str = "",
        content_type: str = "",
        status_code: int | None = None,
        bytes_read: int = 0,
        redirect_count: int = 0,
        overflow: bool = False,
    ) -> FetchResult:
        return cls(
            requested_url=requested_url,
            final_url=final_url or requested_url,
            content="",
            content_type=content_type,
            status_code=status_code,
            bytes_read=bytes_read,
            redirect_count=redirect_count,
            truncated=False,
            overflow=overflow,
            error_category=category,
            error_message=message,
        )

    @classmethod
    def success(
        cls,
        requested_url: str,
        content: str,
        *,
        final_url: str = "",
        content_type: str = "",
        status_code: int | None = None,
        bytes_read: int = 0,
        redirect_count: int = 0,
        truncated: bool = False,
        overflow: bool = False,
    ) -> FetchResult:
        return cls(
            requested_url=requested_url,
            final_url=final_url or requested_url,
            content=content,
            content_type=content_type,
            status_code=status_code,
            bytes_read=bytes_read,
            redirect_count=redirect_count,
            truncated=truncated,
            overflow=overflow,
            error_category=None,
            error_message=None,
        )


def classify_http_status(status: int) -> str:
    if status in (401, 403, 407):
        return ErrorCategory.AUTH
    if status == 429:
        return ErrorCategory.RATE_LIMIT
    if status >= 500:
        return ErrorCategory.UNAVAILABLE
    if status >= 400:
        return ErrorCategory.HTTP_ERROR
    return ErrorCategory.UNKNOWN


def classify_error_message(message: str) -> str:
    """Best-effort classification for legacy/string errors."""
    m = (message or "").lower()
    if "blocked" in m or "non-global" in m or "credential" in m:
        return ErrorCategory.BLOCKED
    if "timeout" in m:
        return ErrorCategory.TIMEOUT
    if "exceeds download limit" in m or "overflow" in m or "pdf exceeds" in m:
        return ErrorCategory.OVERFLOW
    if "non-text content" in m or "binary content" in m:
        return ErrorCategory.UNSUPPORTED
    if "unsupported content-encoding" in m or "decompress" in m or "charset" in m:
        return ErrorCategory.DECODE
    if "too many redirects" in m or "redirect" in m:
        return ErrorCategory.REDIRECT
    if "http 401" in m or "http 403" in m or "http 407" in m:
        return ErrorCategory.AUTH
    if "http 429" in m:
        return ErrorCategory.RATE_LIMIT
    if "http 5" in m:
        return ErrorCategory.UNAVAILABLE
    if "http " in m:
        return ErrorCategory.HTTP_ERROR
    if "failed to fetch" in m or "dns" in m:
        return ErrorCategory.NETWORK
    if "no readable" in m or "no extractable" in m:
        return ErrorCategory.EMPTY_CONTENT
    return ErrorCategory.UNKNOWN
