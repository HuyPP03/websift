"""Provider HTTP transport (credential-aware) — separate from page-fetch SSRF path.

Arbitrary ``fetch_raw`` / ``web_fetch`` must never use this module's secret headers.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping

_SECRET_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "api-key",
        "x-subscription-token",
        "x-auth-token",
    }
)
_SECRET_KEY_HINTS = (
    "authorization",
    "api_key",
    "apikey",
    "api-key",
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "subscription",
)
_REDACTED = "[REDACTED]"
# Bearer tokens, long hex/base64-looking secrets in free text.
# Use re.IGNORECASE (not mid-pattern (?i)): Python 3.11+ rejects global flags after start.
_TOKEN_RE = re.compile(
    r"\b(bearer\s+)[a-z0-9._\-+/=]{8,}\b"
    r"|\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([^\s'\",;]+)",
    re.IGNORECASE,
)


def is_secret_header_name(name: str) -> bool:
    n = (name or "").strip().lower()
    if n in _SECRET_HEADER_NAMES:
        return True
    return any(h in n for h in ("token", "secret", "password", "api-key", "apikey"))


def redact_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Return a copy of headers with secret values redacted (for logs/errors)."""
    if not headers:
        return {}
    out: dict[str, str] = {}
    for k, v in headers.items():
        out[str(k)] = _REDACTED if is_secret_header_name(str(k)) else str(v)
    return out


def redact_secrets(text: str) -> str:
    """Best-effort redaction of secrets in free-form error/log text."""
    if not text:
        return ""
    s = str(text)
    s = _TOKEN_RE.sub(
        lambda m: (m.group(1) or "") + _REDACTED if m.group(1) else f"{m.group(2)}={_REDACTED}",
        s,
    )
    # Query-string style key=value for common secret names.
    for hint in _SECRET_KEY_HINTS:
        s = re.sub(
            rf"(?i)({re.escape(hint)}\s*[=:]\s*)([^\s&,;]+)",
            rf"\1{_REDACTED}",
            s,
        )
    return s


def validate_provider_base_url(
    url: str,
    *,
    allow_http: bool = False,
) -> tuple[bool, str, str]:
    """Validate a configured provider base URL (not MCP caller input).

    Returns ``(ok, reason, normalized_url)``.
    """
    raw = (url or "").strip()
    if not raw:
        return False, "Provider base_url is required.", ""
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return False, "Provider base_url must be http or https.", ""
    if parsed.scheme == "http" and not allow_http:
        return False, "Provider base_url must use https (set allow_http for local dev).", ""
    if parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""):
        return False, "Provider base_url must not contain embedded credentials.", ""
    if not parsed.hostname:
        return False, "Provider base_url must include a hostname.", ""
    # Normalize: strip fragment; keep path.
    normalized = parsed._replace(fragment="").geturl()
    return True, "", normalized.rstrip("/")


@dataclass
class ProviderHttpConfig:
    """Typed config for provider HTTP calls (never mixed into page fetch)."""

    base_url: str
    timeout: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)
    allow_http: bool = False
    retry_max: int = 1
    retry_backoff_seconds: float = 0.5
    max_body_bytes: int = 2_000_000


@dataclass(frozen=True)
class ProviderHttpResponse:
    """Raw provider HTTP response (body may be truncated by max_body_bytes)."""

    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str  # request URL without credentials


class ProviderHttpClient:
    """Minimal credential-aware HTTP helper for search providers.

    Intentionally separate from ``websift.http.fetch_raw`` so API keys never
    ride on the arbitrary page-fetch path.
    """

    def __init__(self, config: ProviderHttpConfig):
        ok, reason, base = validate_provider_base_url(config.base_url, allow_http=config.allow_http)
        if not ok:
            from websift.providers.errors import ProviderConfigError

            raise ProviderConfigError(reason, code="invalid_base_url")
        self.base_url = base
        self.timeout = float(config.timeout)
        self._headers = dict(config.headers or {})
        self.retry_max = max(0, int(config.retry_max))
        self.retry_backoff_seconds = max(0.0, float(config.retry_backoff_seconds))
        self.max_body_bytes = max(1, int(config.max_body_bytes))

    @property
    def public_headers(self) -> dict[str, str]:
        """Headers safe for logging (secrets redacted)."""
        return redact_headers(self._headers)

    def build_headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = dict(self._headers)
        if extra:
            headers.update(extra)
        return headers

    def build_url(self, path: str = "", params: Mapping[str, Any] | None = None) -> str:
        """Join base_url + path + query. Path must be relative (no scheme)."""
        rel = (path or "").strip()
        if rel.startswith("http://") or rel.startswith("https://"):
            from websift.providers.errors import ProviderConfigError

            raise ProviderConfigError(
                "Provider request path must be relative to configured base_url.",
                code="absolute_path_forbidden",
            )
        if rel.startswith("/"):
            url = f"{self.base_url}{rel}"
        elif rel:
            url = f"{self.base_url}/{rel}"
        else:
            url = self.base_url
        if params:
            # Drop empty values; stringify for query encoding.
            q = {str(k): str(v) for k, v in params.items() if v is not None and str(v) != ""}
            if q:
                url = f"{url}?{urllib.parse.urlencode(q)}"
        return url

    def get(
        self,
        path: str = "",
        *,
        params: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
        provider: str | None = None,
    ) -> ProviderHttpResponse:
        """GET with bounded retries for timeout / 429 / selected 5xx."""
        return self._request(
            "GET",
            path,
            params=params,
            extra_headers=extra_headers,
            provider=provider,
        )

    def post(
        self,
        path: str = "",
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        extra_headers: Mapping[str, str] | None = None,
        provider: str | None = None,
    ) -> ProviderHttpResponse:
        """POST JSON with the same retry/status policy as GET."""
        return self._request(
            "POST",
            path,
            params=params,
            json_body=json_body,
            extra_headers=extra_headers,
            provider=provider,
        )

    def get_json(
        self,
        path: str = "",
        *,
        params: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
        provider: str | None = None,
    ) -> Any:
        """GET and parse JSON body; map non-2xx to provider errors."""
        resp = self.get(path, params=params, extra_headers=extra_headers, provider=provider)
        return self._parse_json_response(resp, provider=provider)

    def post_json(
        self,
        path: str = "",
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        extra_headers: Mapping[str, str] | None = None,
        provider: str | None = None,
    ) -> Any:
        """POST JSON and parse JSON body; map non-2xx to provider errors."""
        resp = self.post(
            path,
            params=params,
            json_body=json_body,
            extra_headers=extra_headers,
            provider=provider,
        )
        return self._parse_json_response(resp, provider=provider)

    def _request(
        self,
        method: str,
        path: str = "",
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        extra_headers: Mapping[str, str] | None = None,
        provider: str | None = None,
    ) -> ProviderHttpResponse:
        url = self.build_url(path, params)
        headers = self.build_headers(extra_headers)
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
            headers.setdefault("Accept", "application/json")
        attempts = self.retry_max + 1
        last_exc: BaseException | None = None
        last_resp: ProviderHttpResponse | None = None
        for attempt in range(attempts):
            try:
                resp = self._request_once(method, url, headers, data=data)
            except Exception as e:
                last_exc = e
                mapped = _map_http_exception(e, provider=provider)
                if attempt + 1 >= attempts or not _is_retryable(mapped, e):
                    raise mapped from e
                delay = self.retry_backoff_seconds * (2**attempt)
                if delay > 0:
                    time.sleep(min(delay, 5.0))
                continue

            last_resp = resp
            retryable_status = resp.status == 429 or resp.status >= 500
            if retryable_status and attempt + 1 < attempts:
                delay = self.retry_backoff_seconds * (2**attempt)
                ra = _parse_retry_after(resp.headers)
                if ra is not None and ra > 0:
                    delay = min(max(delay, float(ra)), 30.0)
                if delay > 0:
                    time.sleep(min(delay, 5.0))
                continue
            return resp

        if last_resp is not None:
            return last_resp
        raise _map_http_exception(last_exc or RuntimeError("request failed"), provider=provider)

    def _parse_json_response(self, resp: ProviderHttpResponse, *, provider: str | None) -> Any:
        from websift.providers.errors import (
            ProviderAuthError,
            ProviderBillingError,
            ProviderRateLimitError,
            ProviderResponseError,
            ProviderUnavailableError,
            sanitize_provider_message,
        )

        if resp.status in {401, 403}:
            raise ProviderAuthError(
                "Provider authentication failed.",
                provider=provider,
            )
        if resp.status in {402, 432, 433}:
            raise ProviderBillingError(
                "Provider billing or plan limit failure.",
                provider=provider,
            )
        if resp.status == 429:
            raise ProviderRateLimitError(
                "Provider rate limited.",
                provider=provider,
                retry_after=_parse_retry_after(resp.headers),
            )
        if resp.status >= 500:
            raise ProviderUnavailableError(
                f"Provider unavailable (HTTP {resp.status}).",
                provider=provider,
            )
        if resp.status < 200 or resp.status >= 300:
            raise ProviderResponseError(
                f"Provider returned HTTP {resp.status}.",
                provider=provider,
            )
        if not resp.body:
            return None
        try:
            text = resp.body.decode("utf-8")
            return json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ProviderResponseError(
                sanitize_provider_message(f"Invalid JSON from provider: {e}"),
                provider=provider,
                cause=e,
            ) from e

    def _request_once(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        *,
        data: bytes | None = None,
    ) -> ProviderHttpResponse:
        req = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = int(getattr(resp, "status", None) or resp.getcode() or 0)
                raw_headers = {str(k): str(v) for k, v in resp.headers.items()}
                body = _read_capped(resp, self.max_body_bytes)
                return ProviderHttpResponse(status=status, headers=raw_headers, body=body, url=url)
        except urllib.error.HTTPError as e:
            # HTTPError is also a file-like response body.
            status = int(e.code or 0)
            raw_headers = {str(k): str(v) for k, v in (e.headers.items() if e.headers else [])}
            try:
                body = _read_capped(e, self.max_body_bytes)
            except Exception:
                body = b""
            # Return non-2xx as response so JSON helpers can map status codes.
            return ProviderHttpResponse(status=status, headers=raw_headers, body=body, url=url)

    def assert_no_page_fetch_leak(self, page_fetch_headers: Mapping[str, str] | None) -> None:
        """Raise if any secret header appears on a page-fetch header map."""
        if not page_fetch_headers:
            return
        for name, value in page_fetch_headers.items():
            if is_secret_header_name(str(name)):
                from websift.providers.errors import ProviderConfigError

                raise ProviderConfigError(
                    f"Refusing to attach secret header {name!r} to page fetch.",
                    code="credential_isolation",
                )
            # Also refuse values that equal known secret values from this client.
            for secret in self._headers.values():
                if secret and str(value) == str(secret):
                    from websift.providers.errors import ProviderConfigError

                    raise ProviderConfigError(
                        "Refusing to attach provider secret value to page fetch.",
                        code="credential_isolation",
                    )


def _read_capped(fp: Any, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < max_bytes:
        block = fp.read(min(65_536, max_bytes - total + 1))
        if not block:
            break
        total += len(block)
        if total > max_bytes:
            chunks.append(block[: max(0, max_bytes - (total - len(block)))])
            break
        chunks.append(block)
    return b"".join(chunks)


def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
    raw = None
    for k, v in headers.items():
        if str(k).lower() == "retry-after":
            raw = str(v).strip()
            break
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _is_retryable(mapped: BaseException, original: BaseException) -> bool:
    from websift.providers.errors import (
        ProviderRateLimitError,
        ProviderTimeoutError,
        ProviderUnavailableError,
    )

    if isinstance(mapped, (ProviderTimeoutError, ProviderRateLimitError, ProviderUnavailableError)):
        return True
    if isinstance(original, (TimeoutError, urllib.error.URLError, ConnectionError, OSError)):
        return True
    return False


def _map_http_exception(exc: BaseException | None, *, provider: str | None) -> Exception:
    from websift.providers.errors import (
        ProviderTimeoutError,
        ProviderUnavailableError,
        sanitize_provider_message,
    )

    if exc is None:
        return ProviderUnavailableError("Provider request failed.", provider=provider)
    # Already a provider error.
    from websift.providers.errors import ProviderError

    if isinstance(exc, ProviderError):
        return exc
    msg = sanitize_provider_message(str(exc))
    name = type(exc).__name__.lower()
    text = msg.lower()
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text or "timeout" in name:
        return ProviderTimeoutError(f"Provider timed out: {msg}", provider=provider, cause=exc)
    return ProviderUnavailableError(f"Provider request failed: {msg}", provider=provider, cause=exc)
