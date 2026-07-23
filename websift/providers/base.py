"""Search provider contract, base class, and default fetch implementation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from websift.config import (
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
from websift.content import looks_like_html, looks_like_html_document
from websift.html import html_to_markdown, truncate
from websift.http import fetch_raw
from websift.models import ErrorCategory, FetchResult, SearchRequest, SearchResult
from websift.security import validate_http_url

_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_GITHUB_NON_OWNER_SEGMENTS = {
    "features",
    "pricing",
    "about",
    "contact",
    "login",
    "signup",
    "topics",
    "trending",
    "explore",
    "marketplace",
    "settings",
    "notifications",
    "issues",
    "pulls",
    "discussions",
}

GITHUB_README_HEADERS = {
    "Accept": "application/vnd.github.raw+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider supports; unsupported request filters must not be silently ignored."""

    safe_search: bool = False
    region: bool = False
    time_range: bool = False
    pagination: bool = False
    domain_filter: bool = False


@dataclass(frozen=True)
class FetchContext:
    """Fetch/extraction knobs injected into providers (never mixes provider secrets)."""

    timeout_seconds: float = 30.0
    max_bytes: int = MAX_FETCH_BYTES
    max_pdf_bytes: int = MAX_PDF_FETCH_BYTES
    max_redirects: int = MAX_REDIRECTS
    max_compressed_bytes: int = MAX_COMPRESSED_BYTES
    max_decompressed_bytes: int = MAX_DECOMPRESSED_BYTES
    pdf_max_pages: int = PDF_MAX_PAGES
    pdf_max_chars: int = PDF_MAX_CHARS
    allow_http: bool = True
    allowed_ports: frozenset[int] = frozenset()
    allowed_domains: frozenset[str] = frozenset()
    denied_domains: frozenset[str] = frozenset()
    max_page_chars: int = MAX_PAGE_CHARS
    min_main_content_chars: int = MIN_MAIN_CONTENT_CHARS
    include_links: bool = True
    include_images: bool = False
    output_format: str = "markdown"
    # When False, Tavily/Exa skip native extract and use generic fetch.
    native_fetch: bool = True

    @classmethod
    def defaults(cls) -> FetchContext:
        return cls()


@runtime_checkable
class SearchProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def search(self, request: SearchRequest) -> list[SearchResult]:
        """Execute search and return normalized results.

        Raises provider errors from ``websift.providers.errors`` on failure.
        """
        ...

    def fetch(self, url: str) -> FetchResult:
        """Fetch page content for ``url`` (default generic or provider-native)."""
        ...


def validate_request_capabilities(
    request: SearchRequest,
    capabilities: ProviderCapabilities,
    *,
    allow_unsupported: bool = False,
) -> None:
    """Raise ``ProviderConfigError`` if request uses unsupported filters."""
    from websift.providers.errors import ProviderConfigError

    if allow_unsupported:
        return
    unsupported: list[str] = []
    if request.safe_search is not None and not capabilities.safe_search:
        unsupported.append("safe_search")
    if request.region is not None and not capabilities.region:
        unsupported.append("region")
    if request.time_range is not None and not capabilities.time_range:
        unsupported.append("time_range")
    if unsupported:
        raise ProviderConfigError(
            f"Provider does not support filter(s): {', '.join(unsupported)}",
            code="unsupported_filter",
        )


def process_fetched_body(
    body: str,
    content_type: str,
    *,
    max_page_chars: int,
    base_url: str | None = None,
    prefix: str = "",
    include_links: bool = True,
    include_images: bool = False,
    min_main_content_chars: int = MIN_MAIN_CONTENT_CHARS,
    output_format: str = "markdown",
) -> tuple[str, bool]:
    """Shared body pipeline for ordinary fetch and GitHub README shortcut.

    Returns ``(rendered_text, truncated)``.
    """
    if "html" not in (content_type or "") and not looks_like_html(body):
        text = body.strip()
    else:
        text = html_to_markdown(
            body,
            main_content=True,
            base_url=base_url,
            include_links=include_links,
            include_images=include_images,
            min_main_content_chars=min_main_content_chars,
            output_format=output_format,
        )
        if not text.strip() and body.strip():
            text = body.strip()

    if prefix:
        text = f"{prefix}{text}"

    pre_len = len(text)
    rendered = truncate(text, max_page_chars)
    truncated = pre_len > max_page_chars
    return rendered, truncated


def github_readme_api_url(url: str) -> str | None:
    """Return GitHub raw README API URL for a repo root page, else None."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().lstrip("www.")
    if host != "github.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2:
        return None
    owner, repo = parts
    if owner.lower() in _GITHUB_NON_OWNER_SEGMENTS:
        return None
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not (_GITHUB_NAME_RE.match(owner) and _GITHUB_NAME_RE.match(repo)):
        return None
    return f"https://api.github.com/repos/{owner}/{repo}/readme"


class BaseProvider:
    """Base search provider with default SSRF-safe generic fetch.

    Subclasses implement ``search``. Tavily/Exa may override ``fetch`` for
    native extraction while calling ``super().fetch()`` on URL-level failure.
    """

    name: str = "base"
    capabilities: ProviderCapabilities = ProviderCapabilities()

    def __init__(
        self,
        *,
        fetch_context: FetchContext | None = None,
        pdf_semaphore: Any = None,
    ):
        self._fetch_context = fetch_context or FetchContext.defaults()
        self._pdf_semaphore = pdf_semaphore

    def search(self, request: SearchRequest) -> list[SearchResult]:
        raise NotImplementedError(f"{type(self).__name__}.search is not implemented")

    def fetch(self, url: str) -> FetchResult:
        """Default generic fetch (SSRF/DNS pin, GitHub README shortcut, extraction)."""
        url = (url or "").strip()
        if not url:
            return FetchResult.failure(url, "No URL provided.", ErrorCategory.EMPTY_INPUT)

        ctx = self._fetch_context
        fetch_timeout = float(ctx.timeout_seconds)
        max_bytes = int(ctx.max_bytes)
        max_pdf = int(ctx.max_pdf_bytes)

        readme_url = github_readme_api_url(url)
        if readme_url:
            gh = fetch_raw(
                readme_url,
                fetch_timeout,
                max_bytes,
                max_pdf,
                extra_headers=dict(GITHUB_README_HEADERS),
                pdf_semaphore=self._pdf_semaphore,
                **self._fetch_kwargs(),
            )
            if gh.ok and gh.content.strip():
                body = gh.content
                ct = gh.content_type
                if looks_like_html_document(body):
                    rendered, truncated = process_fetched_body(
                        body,
                        "text/html",
                        max_page_chars=ctx.max_page_chars,
                        base_url=url,
                        prefix=f"README of {url} (via GitHub API):\n\n",
                        **self._extraction_kwargs(),
                    )
                else:
                    text = f"README of {url} (via GitHub API):\n\n{body.strip()}"
                    pre_len = len(text)
                    rendered = truncate(text, ctx.max_page_chars)
                    truncated = pre_len > ctx.max_page_chars
                if rendered.strip():
                    return FetchResult.success(
                        url,
                        rendered,
                        final_url=gh.final_url or readme_url,
                        content_type=ct or "text/plain",
                        status_code=gh.status_code,
                        bytes_read=gh.bytes_read,
                        redirect_count=gh.redirect_count,
                        truncated=truncated,
                    )

        raw = fetch_raw(
            url,
            fetch_timeout,
            max_bytes,
            max_pdf,
            pdf_semaphore=self._pdf_semaphore,
            **self._fetch_kwargs(),
        )
        if not raw.ok:
            return FetchResult.failure(
                url,
                raw.error_message or "Fetch failed",
                raw.error_category or ErrorCategory.UNKNOWN,
                final_url=raw.final_url,
                content_type=raw.content_type,
                status_code=raw.status_code,
                bytes_read=raw.bytes_read,
                redirect_count=raw.redirect_count,
                overflow=raw.overflow,
            )

        rendered, truncated = process_fetched_body(
            raw.content,
            raw.content_type,
            max_page_chars=ctx.max_page_chars,
            base_url=raw.final_url or url,
            **self._extraction_kwargs(),
        )
        return FetchResult.success(
            url,
            rendered,
            final_url=raw.final_url or url,
            content_type=raw.content_type,
            status_code=raw.status_code,
            bytes_read=raw.bytes_read,
            redirect_count=raw.redirect_count,
            truncated=truncated,
            overflow=raw.overflow,
        )

    def validate_url_for_provider(self, url: str) -> FetchResult | None:
        """Validate caller URL before disclosing it to a paid extract API.

        Returns a failure ``FetchResult`` when blocked; ``None`` when allowed.
        Does not perform DNS resolution (provider resolves from its network).
        """
        ctx = self._fetch_context
        ports = ctx.allowed_ports or None
        ok, reason, _validated = validate_http_url(
            url,
            allow_http=ctx.allow_http,
            allowed_ports=ports if ports else None,
            allowed_domains=ctx.allowed_domains or None,
            denied_domains=ctx.denied_domains or None,
        )
        if ok:
            return None
        return FetchResult.failure(url, f"Fetch failed: {reason}", ErrorCategory.BLOCKED)

    def truncate_native_content(
        self,
        url: str,
        content: str,
        *,
        final_url: str = "",
        content_type: str = "text/plain",
    ) -> FetchResult:
        """Apply PAGE_MAX_CHARS to already-cleaned provider extract content."""
        text = (content or "").strip()
        if not text:
            return FetchResult.failure(url, "Fetch failed: empty content.", ErrorCategory.EMPTY_CONTENT)
        pre_len = len(text)
        rendered = truncate(text, self._fetch_context.max_page_chars)
        return FetchResult.success(
            url,
            rendered,
            final_url=final_url or url,
            content_type=content_type,
            truncated=pre_len > self._fetch_context.max_page_chars,
        )

    def _fetch_kwargs(self) -> dict[str, Any]:
        ports = self._fetch_context.allowed_ports or None
        return {
            "max_compressed_bytes": self._fetch_context.max_compressed_bytes,
            "max_decompressed_bytes": self._fetch_context.max_decompressed_bytes,
            "pdf_max_pages": self._fetch_context.pdf_max_pages,
            "pdf_max_chars": self._fetch_context.pdf_max_chars,
            "max_redirects": self._fetch_context.max_redirects,
            "allow_http": self._fetch_context.allow_http,
            "allowed_ports": ports if ports else None,
            "allowed_domains": self._fetch_context.allowed_domains or None,
            "denied_domains": self._fetch_context.denied_domains or None,
        }

    def _extraction_kwargs(self) -> dict[str, Any]:
        return {
            "include_links": self._fetch_context.include_links,
            "include_images": self._fetch_context.include_images,
            "min_main_content_chars": self._fetch_context.min_main_content_chars,
            "output_format": self._fetch_context.output_format,
        }
