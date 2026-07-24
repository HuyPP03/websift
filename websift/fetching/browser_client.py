"""Remote browser rendering fetch backend."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any

from websift.models import ErrorCategory, FetchResult, classify_http_status
from websift.providers.base import FetchContext, process_fetched_body
from websift.providers.errors import sanitize_provider_message
from websift.settings import BrowserSettings

_log = logging.getLogger(__name__)

BROWSER_PROTOCOL_VERSION = "1"
_PROTOCOL_HEADER = "X-Websift-Browser-Protocol"
_INSTALL_HINT = "Remote browser fetching requires httpx. Install it with: pip install 'websift[browser]'"
_CONNECT_TIMEOUT = 5.0  # fast-fail for unreachable browser endpoints
_HEALTH_TIMEOUT = 2.0  # very short timeout for healthz ping
_CIRCUIT_OPEN_AFTER = 3  # consecutive connect failures before opening circuit
_CIRCUIT_RESET_AFTER = 30.0  # seconds before trying browser again
_ERROR_CATEGORIES = frozenset(
    {
        ErrorCategory.BLOCKED,
        ErrorCategory.TIMEOUT,
        ErrorCategory.AUTH,
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.UNAVAILABLE,
        ErrorCategory.OVERFLOW,
        ErrorCategory.UNSUPPORTED,
        ErrorCategory.EMPTY_CONTENT,
        ErrorCategory.HTTP_ERROR,
        ErrorCategory.NETWORK,
        ErrorCategory.DECODE,
        ErrorCategory.REDIRECT,
        ErrorCategory.PROVIDER,
        ErrorCategory.UNKNOWN,
    }
)


def _load_httpx():
    try:
        import httpx
    except ImportError as e:
        raise ImportError(_INSTALL_HINT) from e
    return httpx


def _safe_message(value: object, *, token: str | None = None) -> str:
    message = sanitize_provider_message(str(value or "Remote browser service failed."))
    if token:
        message = message.replace(token, "[REDACTED]")
    message = " ".join(message.replace("\x00", "").split())
    return message[:500] or "Remote browser service failed."


class RemoteBrowserBackend:
    """Render one URL through a fixed remote endpoint without forwarding redirects."""

    def __init__(self, settings: BrowserSettings, fetch_context: FetchContext):
        endpoint = (settings.endpoint or "").strip().rstrip("/")
        if not endpoint:
            raise ValueError("BROWSER_ENDPOINT is required for the remote browser backend")
        self.settings = settings
        self.fetch_context = fetch_context
        self._render_url = f"{endpoint}/v1/render"
        self._httpx = _load_httpx()
        headers = {_PROTOCOL_HEADER: BROWSER_PROTOCOL_VERSION}
        if settings.bearer_token:
            headers["Authorization"] = f"Bearer {settings.bearer_token}"
        # Separate connect vs. read timeout: connect fails fast (5s) so unreachable
        # browsers don't block the entire orchestrator; read uses the full deadline
        # since rendering legitimately takes time once connected.
        read_timeout = max(settings.timeout_seconds - _CONNECT_TIMEOUT, 1.0)
        self._client = self._httpx.Client(
            headers=headers,
            timeout=self._httpx.Timeout(connect=_CONNECT_TIMEOUT, read=read_timeout, write=_CONNECT_TIMEOUT, pool=_CONNECT_TIMEOUT),
            follow_redirects=False,
        )
        self._semaphore = threading.BoundedSemaphore(settings.max_concurrency)
        # Circuit breaker: skip browser calls after consecutive connect failures
        self._circuit_open = False
        self._consecutive_connect_failures = 0
        self._last_connect_failure_time: float | None = None
        self._health_url = f"{endpoint}/healthz"
        identity = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:16]
        self.fingerprint = (
            f"remote-browser-v1:{BROWSER_PROTOCOL_VERSION}:{identity}:"
            f"{settings.timeout_seconds}:{settings.post_load_wait_ms}:{settings.max_html_bytes}:"
            f"{settings.max_response_bytes}:{settings.max_concurrency}"
        )

    @property
    def is_available(self) -> bool:
        """Return False if the circuit breaker is open (browser known unreachable)."""
        if not self._circuit_open:
            return True
        # Auto-half-open after reset period for a probe
        if self._last_connect_failure_time is not None and (
            time.monotonic() - self._last_connect_failure_time
        ) >= _CIRCUIT_RESET_AFTER:
            return True  # allow one probe request
        return False

    def _record_connect_failure(self) -> None:
        """Record a connect failure and possibly open the circuit breaker."""
        self._consecutive_connect_failures += 1
        self._last_connect_failure_time = time.monotonic()
        if self._consecutive_connect_failures >= _CIRCUIT_OPEN_AFTER:
            if not self._circuit_open:
                self._circuit_open = True
                _log.warning(
                    "Remote browser circuit breaker opened after %d consecutive "
                    "connect failures to %s",
                    self._consecutive_connect_failures,
                    self._render_url,
                )

    def _record_connect_ok(self) -> None:
        """Reset circuit breaker on successful connect."""
        if self._circuit_open or self._consecutive_connect_failures > 0:
            self._circuit_open = False
            self._consecutive_connect_failures = 0
            self._last_connect_failure_time = None
            _log.info("Remote browser circuit breaker closed for %s", self._render_url)

    def fetch(self, url: str) -> FetchResult:
        payload = {
            "protocol_version": BROWSER_PROTOCOL_VERSION,
            "url": url,
            "render": {
                "timeout_seconds": self.settings.timeout_seconds,
                "post_load_wait_ms": self.settings.post_load_wait_ms,
                "max_html_bytes": self.settings.max_html_bytes,
            },
            "policy": {
                "allow_http": bool(self.fetch_context.allow_http),
                "allowed_ports": sorted(self.fetch_context.allowed_ports or {80, 443}),
                "allowed_domains": sorted(self.fetch_context.allowed_domains),
                "denied_domains": sorted(self.fetch_context.denied_domains),
            },
        }
        try:
            with self._semaphore:
                data, response_headers, status_code = self._post_bounded(payload)
        except (self._httpx.ConnectError, self._httpx.ConnectTimeout) as e:
            self._record_connect_failure()
            return FetchResult.failure(
                url,
                f"Remote browser unreachable: {_safe_message(e, token=self.settings.bearer_token)}",
                ErrorCategory.NETWORK,
            )
        except self._httpx.TimeoutException:
            self._record_connect_ok()
            return FetchResult.failure(url, "Remote browser request timed out.", ErrorCategory.TIMEOUT)
        except self._httpx.HTTPError as e:
            self._record_connect_ok()
            return FetchResult.failure(
                url,
                f"Remote browser request failed: {_safe_message(e, token=self.settings.bearer_token)}",
                ErrorCategory.NETWORK,
            )
        except (ValueError, UnicodeDecodeError) as e:
            self._record_connect_ok()
            return FetchResult.failure(
                url,
                f"Remote browser response invalid: {_safe_message(e, token=self.settings.bearer_token)}",
                ErrorCategory.DECODE,
            )

        self._record_connect_ok()
        protocol = response_headers.get(_PROTOCOL_HEADER, "")
        if protocol != BROWSER_PROTOCOL_VERSION:
            return FetchResult.failure(url, "Remote browser protocol mismatch.", ErrorCategory.PROVIDER)
        if status_code >= 400:
            return FetchResult.failure(
                url,
                f"Remote browser service returned HTTP {status_code}.",
                classify_http_status(status_code),
                status_code=status_code,
            )
        return self._parse_response(url, data)

    def _post_bounded(self, payload: dict[str, Any]) -> tuple[dict[str, Any], Any, int]:
        with self._client.stream("POST", self._render_url, json=payload) as response:
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError as e:
                    raise ValueError("invalid response Content-Length") from e
                if declared_size < 0 or declared_size > self.settings.max_response_bytes:
                    raise ValueError("response exceeds configured byte limit")
            body = bytearray()
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > self.settings.max_response_bytes:
                    raise ValueError("response exceeds configured byte limit")
                body.extend(chunk)
            decoded = json.loads(bytes(body).decode("utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("response must be a JSON object")
            return decoded, response.headers, int(response.status_code)

    def _parse_response(self, url: str, data: dict[str, Any]) -> FetchResult:
        if set(data) - {"protocol_version", "ok", "result", "error"}:
            return FetchResult.failure(url, "Remote browser response has unexpected fields.", ErrorCategory.DECODE)
        if data.get("protocol_version") != BROWSER_PROTOCOL_VERSION:
            return FetchResult.failure(url, "Remote browser protocol mismatch.", ErrorCategory.PROVIDER)
        if data.get("ok") is True:
            result = data.get("result")
            if not isinstance(result, dict):
                return FetchResult.failure(url, "Remote browser success response is malformed.", ErrorCategory.DECODE)
            return self._parse_success(url, result)
        if data.get("ok") is False:
            error = data.get("error")
            if not isinstance(error, dict):
                return FetchResult.failure(url, "Remote browser failure response is malformed.", ErrorCategory.DECODE)
            category = str(error.get("category") or ErrorCategory.UNKNOWN)
            if category not in _ERROR_CATEGORIES:
                category = ErrorCategory.UNKNOWN
            message = _safe_message(error.get("message"), token=self.settings.bearer_token)
            return FetchResult.failure(url, f"Remote browser failed: {message}", category)
        return FetchResult.failure(url, "Remote browser response is malformed.", ErrorCategory.DECODE)

    def _parse_success(self, url: str, result: dict[str, Any]) -> FetchResult:
        allowed = {"html", "final_url", "content_type", "status_code", "bytes_read", "redirect_count", "truncated"}
        if set(result) - allowed or not isinstance(result.get("html"), str):
            return FetchResult.failure(url, "Remote browser success response is malformed.", ErrorCategory.DECODE)
        html = result["html"]
        html_bytes = len(html.encode("utf-8"))
        if html_bytes > self.settings.max_html_bytes:
            return FetchResult.failure(
                url,
                "Remote browser HTML exceeds configured byte limit.",
                ErrorCategory.OVERFLOW,
                bytes_read=html_bytes,
                overflow=True,
            )
        final_url = result.get("final_url")
        content_type = result.get("content_type") or "text/html; charset=utf-8"
        if not isinstance(final_url, str) or not isinstance(content_type, str):
            return FetchResult.failure(url, "Remote browser success response is malformed.", ErrorCategory.DECODE)
        try:
            status_code = result.get("status_code")
            status_code = int(status_code) if status_code is not None else 200
            bytes_read = int(result.get("bytes_read", html_bytes))
            redirect_count = int(result.get("redirect_count", 0))
        except (TypeError, ValueError):
            return FetchResult.failure(url, "Remote browser success metadata is malformed.", ErrorCategory.DECODE)
        if status_code < 100 or status_code > 599 or bytes_read < 0 or redirect_count < 0:
            return FetchResult.failure(url, "Remote browser success metadata is malformed.", ErrorCategory.DECODE)
        content, extracted_truncated = process_fetched_body(
            html,
            content_type,
            max_page_chars=self.fetch_context.max_page_chars,
            base_url=final_url or url,
            include_links=self.fetch_context.include_links,
            include_images=self.fetch_context.include_images,
            min_main_content_chars=self.fetch_context.min_main_content_chars,
            output_format=self.fetch_context.output_format,
        )
        if not content.strip():
            return FetchResult.failure(url, "Remote browser returned empty content.", ErrorCategory.EMPTY_CONTENT)
        return FetchResult.success(
            url,
            content,
            final_url=final_url or url,
            content_type=content_type,
            status_code=status_code,
            bytes_read=bytes_read,
            redirect_count=redirect_count,
            truncated=bool(result.get("truncated")) or extracted_truncated,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RemoteBrowserBackend:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
