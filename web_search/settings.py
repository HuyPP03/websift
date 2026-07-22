from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Mapping

from web_search.config import (
    MAX_COMPRESSED_BYTES,
    MAX_DECOMPRESSED_BYTES,
    MAX_FETCH_BYTES,
    MAX_PAGE_CHARS,
    MAX_PDF_FETCH_BYTES,
    MAX_REDIRECTS,
    MIN_MAIN_CONTENT_CHARS,
    PDF_MAX_CHARS,
    PDF_MAX_PAGES,
)

_VALID_TRANSPORTS = frozenset({"streamable-http", "sse", "stdio"})
_VALID_AUTH_MODES = frozenset({"none", "bearer"})
_VALID_LOG_FORMATS = frozenset({"text", "json"})
_VALID_OUTPUT_FORMATS = frozenset({"markdown", "text"})
_REDACTED = "[REDACTED]"


class SettingsError(ValueError):
    """Invalid configuration (safe for logs — no secrets in message)."""

    def __init__(self, message: str, *, code: str = "settings_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def _env_map(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return environ if environ is not None else os.environ


def _raw(env: Mapping[str, str], key: str) -> str | None:
    if key not in env:
        return None
    val = env[key]
    if val is None:
        return None
    s = str(val).strip()
    return s if s != "" else None


def _parse_bool(raw: str, *, key: str) -> bool:
    v = raw.strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    raise SettingsError(f"Invalid boolean for {key}: {raw!r}", code="invalid_bool")


def _parse_int(raw: str, *, key: str, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        n = int(raw.strip())
    except ValueError as e:
        raise SettingsError(f"Invalid integer for {key}: {raw!r}", code="invalid_int") from e
    if min_value is not None and n < min_value:
        raise SettingsError(f"{key} must be >= {min_value}", code="out_of_range")
    if max_value is not None and n > max_value:
        raise SettingsError(f"{key} must be <= {max_value}", code="out_of_range")
    return n


def _parse_float(raw: str, *, key: str, min_value: float | None = None) -> float:
    try:
        n = float(raw.strip())
    except ValueError as e:
        raise SettingsError(f"Invalid number for {key}: {raw!r}", code="invalid_float") from e
    if min_value is not None and n < min_value:
        raise SettingsError(f"{key} must be >= {min_value}", code="out_of_range")
    return n


def _get_int(
    env: Mapping[str, str],
    key: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw = _raw(env, key)
    if raw is None:
        return default
    return _parse_int(raw, key=key, min_value=min_value, max_value=max_value)


def _get_float(
    env: Mapping[str, str],
    key: str,
    default: float,
    *,
    min_value: float | None = None,
) -> float:
    raw = _raw(env, key)
    if raw is None:
        return default
    return _parse_float(raw, key=key, min_value=min_value)


def _get_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = _raw(env, key)
    if raw is None:
        return default
    return _parse_bool(raw, key=key)


def _get_str(env: Mapping[str, str], key: str, default: str) -> str:
    raw = _raw(env, key)
    return default if raw is None else raw


def _get_optional_str(env: Mapping[str, str], key: str) -> str | None:
    return _raw(env, key)


def _parse_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(p.strip() for p in raw.split(",") if p.strip())


@dataclass(frozen=True)
class ServerSettings:
    host: str = "127.0.0.1"
    port: int = 8787
    transport: str = "streamable-http"
    auth_mode: str = "none"
    max_request_body_bytes: int | None = None


@dataclass(frozen=True)
class ProviderSettings:
    name: str = "ddgs"
    max_results: int = 5
    timeout_seconds: float = 30.0
    safe_search: str | None = None
    region: str | None = None
    time_range: str | None = None
    fallback_providers: tuple[str, ...] = ()
    retry_max: int = 1
    retry_backoff_seconds: float = 0.5
    allow_unsupported_filters: bool = False
    base_url: str | None = None
    api_key: str | None = None

    def __repr__(self) -> str:  # pragma: no cover - trivial
        key = _REDACTED if self.api_key else None
        return (
            f"ProviderSettings(name={self.name!r}, max_results={self.max_results}, "
            f"timeout_seconds={self.timeout_seconds}, base_url={self.base_url!r}, api_key={key!r})"
        )


@dataclass(frozen=True)
class FetchSettings:
    timeout_seconds: float = 30.0
    max_bytes: int = MAX_FETCH_BYTES
    max_pdf_bytes: int = MAX_PDF_FETCH_BYTES
    max_redirects: int = MAX_REDIRECTS
    max_compressed_bytes: int = MAX_COMPRESSED_BYTES
    max_decompressed_bytes: int = MAX_DECOMPRESSED_BYTES
    pdf_max_pages: int = PDF_MAX_PAGES
    pdf_max_chars: int = PDF_MAX_CHARS
    allow_http: bool = True


@dataclass(frozen=True)
class ExtractionSettings:
    max_page_chars: int = MAX_PAGE_CHARS
    min_main_content_chars: int = MIN_MAIN_CONTENT_CHARS
    include_links: bool = True
    include_images: bool = False
    output_format: str = "markdown"


@dataclass(frozen=True)
class ConcurrencySettings:
    search_max: int = 8
    fetch_max: int = 16
    pdf_max: int = 2


@dataclass(frozen=True)
class CacheSettings:
    enabled: bool = False
    search_ttl_seconds: int = 300
    fetch_ttl_seconds: int = 600
    max_entries: int = 256
    max_bytes: int = 32 * 1024 * 1024


@dataclass(frozen=True)
class LoggingSettings:
    level: str = "INFO"
    format: str = "text"
    include_urls: bool = False
    include_queries: bool = False


@dataclass(frozen=True)
class AuthSettings:
    mode: str = "none"
    bearer_token: str | None = None

    def __repr__(self) -> str:  # pragma: no cover - trivial
        tok = _REDACTED if self.bearer_token else None
        return f"AuthSettings(mode={self.mode!r}, bearer_token={tok!r})"


@dataclass(frozen=True)
class AppSettings:
    """Application settings tree. Defaults only — no env I/O on construction."""

    server: ServerSettings = field(default_factory=ServerSettings)
    provider: ProviderSettings = field(default_factory=ProviderSettings)
    fetch: FetchSettings = field(default_factory=FetchSettings)
    extraction: ExtractionSettings = field(default_factory=ExtractionSettings)
    concurrency: ConcurrencySettings = field(default_factory=ConcurrencySettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    auth: AuthSettings = field(default_factory=AuthSettings)

    def with_overrides(self, **sections: object) -> AppSettings:
        """Replace whole top-level sections (``provider=...``, ``server=...``, …)."""
        allowed = {
            "server",
            "provider",
            "fetch",
            "extraction",
            "concurrency",
            "cache",
            "logging",
            "auth",
        }
        unknown = set(sections) - allowed
        if unknown:
            raise SettingsError(
                f"Unknown settings section(s): {', '.join(sorted(unknown))}",
                code="unknown_section",
            )
        return replace(self, **sections)

    def validate(self) -> None:
        """Fail-fast validation (no secrets in messages)."""
        if self.server.transport not in _VALID_TRANSPORTS:
            raise SettingsError(
                f"Invalid MCP_TRANSPORT {self.server.transport!r}. "
                f"Allowed: {', '.join(sorted(_VALID_TRANSPORTS))}",
                code="invalid_transport",
            )
        if not (1 <= self.server.port <= 65535):
            raise SettingsError("MCP_PORT must be between 1 and 65535", code="invalid_port")
        if not self.server.host.strip():
            raise SettingsError("MCP_HOST must not be empty", code="invalid_host")
        if self.server.auth_mode not in _VALID_AUTH_MODES:
            raise SettingsError(
                f"Invalid MCP_AUTH_MODE {self.server.auth_mode!r}. Allowed: none, bearer",
                code="invalid_auth_mode",
            )
        if self.auth.mode not in _VALID_AUTH_MODES:
            raise SettingsError(
                f"Invalid auth mode {self.auth.mode!r}. Allowed: none, bearer",
                code="invalid_auth_mode",
            )
        if self.auth.mode == "bearer" and not (self.auth.bearer_token or "").strip():
            raise SettingsError(
                "Bearer auth enabled but MCP_BEARER_TOKEN is empty",
                code="missing_bearer_token",
            )
        if self.provider.max_results < 1:
            raise SettingsError("SEARCH_MAX_RESULTS must be >= 1", code="invalid_max_results")
        if self.provider.timeout_seconds <= 0:
            raise SettingsError("SEARCH_TIMEOUT_SECONDS must be > 0", code="invalid_timeout")
        if self.fetch.timeout_seconds <= 0:
            raise SettingsError("FETCH_TIMEOUT_SECONDS must be > 0", code="invalid_timeout")
        if self.provider.retry_max < 0:
            raise SettingsError("SEARCH_RETRY_MAX must be >= 0", code="invalid_retry")
        if self.extraction.max_page_chars < 1:
            raise SettingsError("PAGE_MAX_CHARS must be >= 1", code="invalid_page_chars")
        if self.extraction.output_format not in _VALID_OUTPUT_FORMATS:
            raise SettingsError(
                f"Invalid HTML_OUTPUT_FORMAT {self.extraction.output_format!r}",
                code="invalid_output_format",
            )
        if self.logging.format not in _VALID_LOG_FORMATS:
            raise SettingsError(
                f"Invalid LOG_FORMAT {self.logging.format!r}",
                code="invalid_log_format",
            )
        if self.concurrency.search_max < 1 or self.concurrency.fetch_max < 1 or self.concurrency.pdf_max < 1:
            raise SettingsError("Concurrency limits must be >= 1", code="invalid_concurrency")
        name = (self.provider.name or "").strip().lower()
        if not name:
            raise SettingsError("SEARCH_PROVIDER must not be empty", code="missing_provider")
        # Allowlist check only when registry available; avoid circular import issues at module load.
        from web_search.providers.registry import is_registered

        if not is_registered(name):
            from web_search.providers.registry import list_providers

            known = ", ".join(list_providers()) or "(none)"
            raise SettingsError(
                f"Unknown SEARCH_PROVIDER {self.provider.name!r}. Allowed: {known}",
                code="unknown_provider",
            )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AppSettings:
        """Parse settings from an env mapping (default: ``os.environ``). Does not mutate global state."""
        env = _env_map(environ)

        legacy_timeout_raw = _raw(env, "SEARCH_TIMEOUT")
        legacy_timeout: float | None = None
        if legacy_timeout_raw is not None:
            legacy_timeout = _parse_float(legacy_timeout_raw, key="SEARCH_TIMEOUT", min_value=0.001)

        search_timeout_raw = _raw(env, "SEARCH_TIMEOUT_SECONDS")
        fetch_timeout_raw = _raw(env, "FETCH_TIMEOUT_SECONDS")
        if search_timeout_raw is not None:
            search_timeout = _parse_float(
                search_timeout_raw, key="SEARCH_TIMEOUT_SECONDS", min_value=0.001
            )
        elif legacy_timeout is not None:
            search_timeout = legacy_timeout
        else:
            search_timeout = 30.0

        if fetch_timeout_raw is not None:
            fetch_timeout = _parse_float(
                fetch_timeout_raw, key="FETCH_TIMEOUT_SECONDS", min_value=0.001
            )
        elif legacy_timeout is not None:
            fetch_timeout = legacy_timeout
        else:
            fetch_timeout = 30.0

        provider_name = _get_str(env, "SEARCH_PROVIDER", "ddgs").strip().lower()
        # Provider-specific secrets (P1 adapters; stored only, not used by ddgs).
        api_key = None
        base_url = None
        if provider_name == "searxng":
            base_url = _get_optional_str(env, "SEARXNG_BASE_URL")
            api_key = _get_optional_str(env, "SEARXNG_API_KEY")
        elif provider_name == "brave":
            base_url = _get_optional_str(env, "BRAVE_BASE_URL")
            api_key = _get_optional_str(env, "BRAVE_API_KEY")
        elif provider_name == "tavily":
            base_url = _get_optional_str(env, "TAVILY_BASE_URL")
            api_key = _get_optional_str(env, "TAVILY_API_KEY")
        elif provider_name == "exa":
            base_url = _get_optional_str(env, "EXA_BASE_URL")
            api_key = _get_optional_str(env, "EXA_API_KEY")

        auth_mode = _get_str(env, "MCP_AUTH_MODE", "none").strip().lower()
        bearer = _get_optional_str(env, "MCP_BEARER_TOKEN")
        body_limit_raw = _raw(env, "MCP_MAX_REQUEST_BODY_BYTES")
        max_request_body_bytes = (
            _parse_int(body_limit_raw, key="MCP_MAX_REQUEST_BODY_BYTES", min_value=1)
            if body_limit_raw is not None
            else None
        )

        settings = cls(
            server=ServerSettings(
                host=_get_str(env, "MCP_HOST", "127.0.0.1"),
                port=_get_int(env, "MCP_PORT", 8787, min_value=1, max_value=65535),
                transport=_get_str(env, "MCP_TRANSPORT", "streamable-http").strip().lower(),
                auth_mode=auth_mode,
                max_request_body_bytes=max_request_body_bytes,
            ),
            provider=ProviderSettings(
                name=provider_name,
                max_results=_get_int(env, "SEARCH_MAX_RESULTS", 5, min_value=1),
                timeout_seconds=search_timeout,
                safe_search=_get_optional_str(env, "SEARCH_SAFE_SEARCH"),
                region=_get_optional_str(env, "SEARCH_REGION"),
                time_range=_get_optional_str(env, "SEARCH_TIME_RANGE"),
                fallback_providers=_parse_csv(_get_optional_str(env, "SEARCH_FALLBACK_PROVIDERS")),
                retry_max=_get_int(env, "SEARCH_RETRY_MAX", 1, min_value=0),
                retry_backoff_seconds=_get_float(
                    env, "SEARCH_RETRY_BACKOFF_SECONDS", 0.5, min_value=0.0
                ),
                allow_unsupported_filters=_get_bool(
                    env, "SEARCH_ALLOW_UNSUPPORTED_FILTERS", False
                ),
                base_url=base_url,
                api_key=api_key,
            ),
            fetch=FetchSettings(
                timeout_seconds=fetch_timeout,
                max_bytes=_get_int(env, "FETCH_MAX_BYTES", MAX_FETCH_BYTES, min_value=1),
                max_pdf_bytes=_get_int(
                    env, "FETCH_MAX_PDF_BYTES", MAX_PDF_FETCH_BYTES, min_value=1
                ),
                max_redirects=_get_int(env, "FETCH_MAX_REDIRECTS", MAX_REDIRECTS, min_value=0),
                max_compressed_bytes=_get_int(
                    env, "FETCH_MAX_COMPRESSED_BYTES", MAX_COMPRESSED_BYTES, min_value=1
                ),
                max_decompressed_bytes=_get_int(
                    env, "FETCH_MAX_DECOMPRESSED_BYTES", MAX_DECOMPRESSED_BYTES, min_value=1
                ),
                pdf_max_pages=_get_int(env, "PDF_MAX_PAGES", PDF_MAX_PAGES, min_value=1),
                pdf_max_chars=_get_int(env, "PDF_MAX_CHARS", PDF_MAX_CHARS, min_value=1),
                allow_http=_get_bool(env, "FETCH_ALLOW_HTTP", True),
            ),
            extraction=ExtractionSettings(
                max_page_chars=_get_int(env, "PAGE_MAX_CHARS", MAX_PAGE_CHARS, min_value=1),
                min_main_content_chars=_get_int(
                    env, "HTML_MIN_MAIN_CONTENT_CHARS", MIN_MAIN_CONTENT_CHARS, min_value=0
                ),
                include_links=_get_bool(env, "HTML_INCLUDE_LINKS", True),
                include_images=_get_bool(env, "HTML_INCLUDE_IMAGES", False),
                output_format=_get_str(env, "HTML_OUTPUT_FORMAT", "markdown").strip().lower(),
            ),
            concurrency=ConcurrencySettings(
                search_max=_get_int(env, "SEARCH_MAX_CONCURRENCY", 8, min_value=1),
                fetch_max=_get_int(env, "FETCH_MAX_CONCURRENCY", 16, min_value=1),
                pdf_max=_get_int(env, "PDF_MAX_CONCURRENCY", 2, min_value=1),
            ),
            cache=CacheSettings(
                enabled=_get_bool(env, "CACHE_ENABLED", False),
                search_ttl_seconds=_get_int(env, "SEARCH_CACHE_TTL_SECONDS", 300, min_value=0),
                fetch_ttl_seconds=_get_int(env, "FETCH_CACHE_TTL_SECONDS", 600, min_value=0),
                max_entries=_get_int(env, "CACHE_MAX_ENTRIES", 256, min_value=1),
                max_bytes=_get_int(env, "CACHE_MAX_BYTES", 32 * 1024 * 1024, min_value=1),
            ),
            logging=LoggingSettings(
                level=_get_str(env, "LOG_LEVEL", "INFO").strip().upper(),
                format=_get_str(env, "LOG_FORMAT", "text").strip().lower(),
                include_urls=_get_bool(env, "LOG_INCLUDE_URLS", False),
                include_queries=_get_bool(env, "LOG_INCLUDE_QUERIES", False),
            ),
            auth=AuthSettings(
                mode=auth_mode,
                bearer_token=bearer,
            ),
        )
        settings.validate()
        return settings
