"""HTTP helpers: pinned fetch, redirects, body limits, compression, charset, PDF."""

from __future__ import annotations

import codecs
import gzip
import http.client
import io
import random
import re
import socket
import ssl
import urllib.error
import urllib.request
import zlib
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

from web_search.config import (
    MAX_COMPRESSED_BYTES,
    MAX_DECOMPRESSED_BYTES,
    MAX_REDIRECTS,
    PDF_MAX_CHARS,
    PDF_MAX_PAGES,
    SUPPORTED_CONTENT_ENCODINGS,
    UNICODE_BOM_CODECS,
    USER_AGENTS,
)
from web_search.content import has_binary_magic, has_pdf_magic, is_text_mime, looks_binary
from web_search.models import ErrorCategory, FetchResult, classify_http_status
from web_search.security import resolve_host, validate_http_url

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

_META_CHARSET_RE = re.compile(
    rb'(?is)<meta[^>]+charset\s*=\s*[\'"]?\s*([a-zA-Z0-9_\-:]+)',
)
_META_HTTP_EQUIV_RE = re.compile(
    rb'(?is)<meta[^>]+http-equiv\s*=\s*[\'"]?content-type[\'"]?[^>]*'
    rb'content\s*=\s*[\'"][^\'"]*charset\s*=\s*([a-zA-Z0-9_\-:]+)',
)
# Alternate attribute order: content before http-equiv
_META_HTTP_EQUIV_RE2 = re.compile(
    rb'(?is)<meta[^>]+content\s*=\s*[\'"][^\'"]*charset\s*=\s*([a-zA-Z0-9_\-:]+)[^\'"]*[\'"][^>]*'
    rb'http-equiv\s*=\s*[\'"]?content-type',
)


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    """Return responses as-is so callers can validate redirects manually (SSRF)."""

    def http_response(self, request, response):
        return response

    https_response = http_response


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection to a pinned IP with real hostname for SNI/cert validation."""

    def __init__(self, host, sni_hostname: str, **kw):
        kw.pop("context", None)
        super().__init__(host, **kw)
        self._sni_hostname = sni_hostname
        self._ctx = ssl.create_default_context()

    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._ctx.wrap_socket(sock, server_hostname=self._sni_hostname)


class _SNIHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, sni_hostname: str):
        super().__init__()
        self._sni = sni_hostname

    def https_open(self, req):
        return self.do_open(
            lambda host, **kw: _PinnedHTTPSConnection(host, sni_hostname=self._sni, **kw),
            req,
        )


def read_capped_body(
    resp,
    limit: int,
    chunk: int = 65536,
) -> tuple[Optional[str], bytes, bool]:
    """Read at most ``limit + 1`` bytes.

    Returns ``(error, data, overflow)``.
    If overflow, ``data`` is truncated to ``limit`` and ``overflow`` is True.
    """
    if limit < 0:
        return "Invalid read limit.", b"", False

    max_read = limit + 1
    chunks: list[bytes] = []
    total = 0
    try:
        while total < max_read:
            data = resp.read(min(chunk, max_read - total))
            if not data:
                break
            chunks.append(data)
            total += len(data)
    except (OSError, http.client.HTTPException, ValueError) as e:
        return f"Failed to read response body: {e}", b"", False

    raw = b"".join(chunks)
    if total > limit:
        return None, raw[:limit], True
    return None, raw, False


def _codec_exists(name: str) -> bool:
    try:
        codecs.lookup(name)
        return True
    except LookupError:
        return False


def detect_charset(raw: bytes, http_charset: str | None) -> str:
    """BOM → valid HTTP charset → HTML meta → UTF-8."""
    for bom, codec in UNICODE_BOM_CODECS:
        if raw.startswith(bom):
            return codec

    if http_charset:
        cs = http_charset.strip().strip("\"'")
        if cs and _codec_exists(cs):
            return cs

    probe = raw[:8192]
    for pattern in (_META_CHARSET_RE, _META_HTTP_EQUIV_RE, _META_HTTP_EQUIV_RE2):
        m = pattern.search(probe)
        if not m:
            continue
        name = m.group(1).decode("ascii", "ignore").strip()
        if name and _codec_exists(name):
            return name

    return "utf-8"


def decompress_body(
    raw: bytes,
    content_encoding: str | None,
    max_decompressed: int = MAX_DECOMPRESSED_BYTES,
) -> tuple[Optional[str], bytes]:
    """Apply Content-Encoding (gzip/deflate) with a decompressed size cap."""
    if not content_encoding:
        return None, raw

    encodings = [e.strip().lower() for e in content_encoding.split(",") if e.strip()]
    if not encodings or encodings == ["identity"]:
        return None, raw

    for enc in encodings:
        if enc not in SUPPORTED_CONTENT_ENCODINGS:
            return f"Unsupported Content-Encoding: {enc}", b""

    data = raw
    # Content-Encoding is listed in the order applied; decode in reverse.
    for enc in reversed(encodings):
        if enc in ("", "identity"):
            continue
        try:
            if enc in ("gzip", "x-gzip"):
                data = _gzip_decompress_bounded(data, max_decompressed)
            elif enc == "deflate":
                data = _deflate_decompress_bounded(data, max_decompressed)
        except (EOFError, OSError, zlib.error, gzip.BadGzipFile, ValueError) as e:
            return f"Failed to decompress response body: {e}", b""

        if len(data) > max_decompressed:
            return f"(decompressed content exceeds limit of {max_decompressed} bytes)", b""

    return None, data


def _gzip_decompress_bounded(data: bytes, max_out: int) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as gf:
        out = gf.read(max_out + 1)
    if len(out) > max_out:
        raise ValueError(f"decompressed size exceeds {max_out} bytes")
    return out


def _deflate_decompress_bounded(data: bytes, max_out: int) -> bytes:
    # Some servers send zlib-wrapped DEFLATE; others raw DEFLATE.
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            dec = zlib.decompressobj(wbits)
            out = dec.decompress(data, max_out + 1)
            if len(out) > max_out:
                raise ValueError(f"decompressed size exceeds {max_out} bytes")
            # Reject if unused compressed input remains (likely truncated / bomb).
            if dec.unconsumed_tail:
                raise ValueError(f"decompressed size exceeds {max_out} bytes")
            # Ensure stream is finished (or flush yields nothing more within budget).
            tail = dec.flush()
            if tail:
                if len(out) + len(tail) > max_out:
                    raise ValueError(f"decompressed size exceeds {max_out} bytes")
                out = out + tail
            return out
        except zlib.error:
            continue
    raise zlib.error("invalid deflate data")


def extract_pdf_text(
    raw: bytes,
    *,
    max_pages: int = PDF_MAX_PAGES,
    max_chars: int = PDF_MAX_CHARS,
) -> str:
    """Extract text with pypdf only; limits pages and characters."""
    try:
        import pypdf
    except ImportError:
        return ""

    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
        parts: list[str] = []
        total = 0
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            piece = page.extract_text() or ""
            if not piece:
                continue
            remain = max_chars - total
            if remain <= 0:
                break
            if len(piece) > remain:
                parts.append(piece[:remain])
                total = max_chars
                break
            parts.append(piece)
            total += len(piece)
        # Join can add separators; clamp so max_chars is a hard cap.
        return "\n".join(parts).strip()[:max_chars]
    except Exception:
        # pypdf parse failures → empty (caller shows friendly message)
        return ""


def _close_quiet(resp) -> None:
    try:
        if resp is not None:
            resp.close()
    except Exception:
        pass


def _response_status(resp) -> int:
    code = getattr(resp, "status", None)
    if code is None:
        code = resp.getcode()
    return int(code)


def _pinned_netloc(port: int, scheme: str, pinned_ip: str) -> str:
    ip_str = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
    default = 443 if scheme == "https" else 80
    if port == default:
        return ip_str
    return f"{ip_str}:{port}"


def _content_length(headers) -> int | None:
    raw = headers.get("Content-Length") if headers is not None else None
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def fetch_raw(
    url: str,
    timeout: int,
    max_fetch_bytes: int,
    max_pdf_fetch_bytes: int,
    extra_headers: Optional[dict] = None,
    *,
    max_compressed_bytes: int = MAX_COMPRESSED_BYTES,
    max_decompressed_bytes: int = MAX_DECOMPRESSED_BYTES,
    pdf_max_pages: int = PDF_MAX_PAGES,
    pdf_max_chars: int = PDF_MAX_CHARS,
) -> FetchResult:
    """Fetch URL with SSRF protection, DNS pinning, redirect following, body limits.

    Returns a :class:`FetchResult`. On failure ``error_category`` / ``error_message``
    are set and ``content`` is empty. Callers format the public string separately.
    """
    requested = str(url).strip() if url is not None else ""

    ok, reason, validated = validate_http_url(url)
    if not ok or validated is None:
        return FetchResult.failure(requested or str(url), reason, ErrorCategory.BLOCKED)

    ok, reason, pinned_ip = resolve_host(validated.hostname, validated.port)
    if not ok:
        cat = ErrorCategory.BLOCKED if "Blocked" in reason or "non-global" in reason.lower() else ErrorCategory.NETWORK
        if "DNS" in reason:
            cat = ErrorCategory.NETWORK
        return FetchResult.failure(requested, reason, cat)

    redirect_count = 0
    try:
        current_url = validated.original
        current_host = validated.hostname
        current_port = validated.port
        current_scheme = validated.scheme
        ua = random.choice(USER_AGENTS)

        content_type = ""
        declared_enc: str | None = None
        content_encoding: str | None = None
        raw_bytes = b""
        declared_pdf = False
        status = 0

        def _fail(
            message: str,
            category: str,
            *,
            ct: str = "",
            code: int | None = None,
            overflow: bool = False,
            nbytes: int = 0,
        ) -> FetchResult:
            return FetchResult.failure(
                requested,
                message,
                category,
                final_url=current_url,
                content_type=ct,
                status_code=code,
                bytes_read=nbytes,
                redirect_count=redirect_count,
                overflow=overflow,
            )

        for _ in range(MAX_REDIRECTS):
            cp = urlparse(current_url)
            ip_netloc = _pinned_netloc(current_port, current_scheme, pinned_ip)
            pinned_url = urlunparse(cp._replace(netloc=ip_netloc, scheme=current_scheme))

            opener = urllib.request.build_opener(_NoRedirect, _SNIHTTPSHandler(current_host))
            headers = {"User-Agent": ua, "Host": current_host, "Accept-Encoding": "gzip, deflate"}
            if extra_headers:
                headers.update(extra_headers)

            req = urllib.request.Request(pinned_url, headers=headers)
            resp = None
            try:
                try:
                    resp = opener.open(req, timeout=timeout)
                    status = _response_status(resp)
                except urllib.error.HTTPError as e:
                    status = e.code
                    resp = e
                    if status not in _REDIRECT_CODES and status >= 400:
                        reason_txt = getattr(e, "reason", "") or ""
                        msg = f"Failed to fetch URL: HTTP {e.code} {reason_txt}".rstrip()
                        _close_quiet(resp)
                        return _fail(msg, classify_http_status(e.code), code=e.code)

                if status in _REDIRECT_CODES:
                    location = resp.headers.get("Location") if resp is not None else None
                    _close_quiet(resp)
                    resp = None
                    if not location:
                        return _fail(
                            "Failed to fetch: redirect missing Location.",
                            ErrorCategory.REDIRECT,
                            code=status,
                        )

                    next_url = urljoin(current_url, location)
                    ok_u, reason_u, vnext = validate_http_url(next_url)
                    if not ok_u or vnext is None:
                        return _fail(
                            reason_u or "Blocked: redirect target not valid http/https.",
                            ErrorCategory.BLOCKED,
                            code=status,
                        )

                    ok2, reason2, pinned_ip = resolve_host(vnext.hostname, vnext.port)
                    if not ok2:
                        cat = (
                            ErrorCategory.BLOCKED
                            if "Blocked" in reason2 or "non-global" in reason2.lower()
                            else ErrorCategory.NETWORK
                        )
                        return _fail(reason2, cat, code=status)

                    redirect_count += 1
                    current_url = next_url
                    current_host = vnext.hostname
                    current_port = vnext.port
                    current_scheme = vnext.scheme
                    continue

                if status >= 400:
                    _close_quiet(resp)
                    return _fail(
                        f"Failed to fetch URL: HTTP {status}",
                        classify_http_status(status),
                        code=status,
                    )

                content_type = (
                    (resp.headers.get_content_type() or "").lower() if resp.headers.get("Content-Type") else ""
                )
                declared_enc = resp.headers.get_content_charset()
                ce_header = resp.headers.get("Content-Encoding")
                content_encoding = ce_header.strip() if ce_header else None
                declared_pdf = content_type == "application/pdf"

                wire_limit = (
                    max_compressed_bytes
                    if content_encoding
                    else (max_pdf_fetch_bytes if declared_pdf else max_fetch_bytes)
                )
                if declared_pdf:
                    wire_limit = min(wire_limit, max_pdf_fetch_bytes)
                elif not content_encoding:
                    wire_limit = min(wire_limit, max_fetch_bytes)

                cl = _content_length(resp.headers)
                if cl is not None and cl > wire_limit:
                    _close_quiet(resp)
                    return _fail(
                        f"(content exceeds download limit of {wire_limit} bytes)",
                        ErrorCategory.OVERFLOW,
                        ct=content_type,
                        code=status,
                        overflow=True,
                    )

                err, raw_bytes, overflow = read_capped_body(resp, wire_limit)
                if err:
                    _close_quiet(resp)
                    return _fail(err, ErrorCategory.NETWORK, code=status)
                if overflow:
                    _close_quiet(resp)
                    return _fail(
                        f"(content exceeds download limit of {wire_limit} bytes)",
                        ErrorCategory.OVERFLOW,
                        ct=content_type,
                        code=status,
                        overflow=True,
                        nbytes=len(raw_bytes),
                    )

                if (
                    not declared_pdf
                    and not content_encoding
                    and has_pdf_magic(raw_bytes)
                    and len(raw_bytes) == wire_limit
                    and max_pdf_fetch_bytes > wire_limit
                ):
                    extra_limit = max_pdf_fetch_bytes - len(raw_bytes)
                    err2, tail, overflow2 = read_capped_body(resp, extra_limit)
                    if err2:
                        _close_quiet(resp)
                        return _fail(err2, ErrorCategory.NETWORK, code=status)
                    raw_bytes = raw_bytes + tail
                    if overflow2 or len(raw_bytes) > max_pdf_fetch_bytes:
                        _close_quiet(resp)
                        return _fail(
                            f"(content exceeds download limit of {max_pdf_fetch_bytes} bytes)",
                            ErrorCategory.OVERFLOW,
                            ct=content_type,
                            code=status,
                            overflow=True,
                            nbytes=len(raw_bytes),
                        )
                    declared_pdf = True

                _close_quiet(resp)
                resp = None
                break
            finally:
                _close_quiet(resp)
        else:
            return _fail("Failed to fetch: too many redirects.", ErrorCategory.REDIRECT)

        if content_encoding:
            derr, raw_bytes = decompress_body(raw_bytes, content_encoding, max_decompressed_bytes)
            if derr is not None:
                cat = ErrorCategory.OVERFLOW if "exceed" in derr.lower() else ErrorCategory.DECODE
                return _fail(
                    derr,
                    cat,
                    ct=content_type,
                    code=status,
                    overflow=cat == ErrorCategory.OVERFLOW,
                    nbytes=len(raw_bytes) if raw_bytes else 0,
                )

        is_pdf = declared_pdf or has_pdf_magic(raw_bytes)
        if is_pdf:
            if len(raw_bytes) > max_pdf_fetch_bytes:
                return _fail(
                    "(PDF exceeds download limit)",
                    ErrorCategory.OVERFLOW,
                    ct=content_type or "application/pdf",
                    code=status,
                    overflow=True,
                    nbytes=len(raw_bytes),
                )
            pdf_text = extract_pdf_text(raw_bytes, max_pages=pdf_max_pages, max_chars=pdf_max_chars)
            content = pdf_text or "(PDF contains no extractable text)"
            return FetchResult.success(
                requested,
                content,
                final_url=current_url,
                content_type="application/pdf",
                status_code=status,
                bytes_read=len(raw_bytes),
                redirect_count=redirect_count,
            )

        if len(raw_bytes) > max_fetch_bytes:
            return _fail(
                f"(content exceeds download limit of {max_fetch_bytes} bytes)",
                ErrorCategory.OVERFLOW,
                ct=content_type,
                code=status,
                overflow=True,
                nbytes=len(raw_bytes),
            )

        if content_type and not is_text_mime(content_type):
            m = re.match(r"[\w.+-]+/[\w.+-]+", content_type)
            return _fail(
                f"(non-text content: {m.group(0) if m else 'unknown type'})",
                ErrorCategory.UNSUPPORTED,
                ct=content_type,
                code=status,
                nbytes=len(raw_bytes),
            )

        if has_binary_magic(raw_bytes):
            return _fail(
                f"(binary content, {len(raw_bytes)} bytes)",
                ErrorCategory.UNSUPPORTED,
                ct=content_type,
                code=status,
                nbytes=len(raw_bytes),
            )

        charset = detect_charset(raw_bytes, declared_enc)
        try:
            text = raw_bytes.decode(charset, errors="replace")
        except (LookupError, ValueError):
            text = raw_bytes.decode("utf-8", errors="replace")

        if looks_binary(text):
            if charset.lower() in ("utf-8", "utf-8-sig", "iso8859-1", "latin-1", "iso-8859-1") or declared_enc in (
                None,
                "iso8859-1",
                "iso-8859-1",
            ):
                alt = raw_bytes.decode("cp1252", "replace")
                if not looks_binary(alt):
                    text = alt
                else:
                    return _fail(
                        f"(binary content, {len(raw_bytes)} bytes)",
                        ErrorCategory.UNSUPPORTED,
                        ct=content_type,
                        code=status,
                        nbytes=len(raw_bytes),
                    )
            else:
                return _fail(
                    f"(binary content, {len(raw_bytes)} bytes)",
                    ErrorCategory.UNSUPPORTED,
                    ct=content_type,
                    code=status,
                    nbytes=len(raw_bytes),
                )

        return FetchResult.success(
            requested,
            text,
            final_url=current_url,
            content_type=content_type,
            status_code=status,
            bytes_read=len(raw_bytes),
            redirect_count=redirect_count,
        )

    except urllib.error.HTTPError as e:
        msg = f"Failed to fetch URL: HTTP {e.code} {getattr(e, 'reason', '')}"
        return FetchResult.failure(requested, msg, classify_http_status(e.code), status_code=e.code)
    except urllib.error.URLError as e:
        reason_txt = getattr(e, "reason", e)
        return FetchResult.failure(
            requested,
            f"Failed to fetch URL: {reason_txt}",
            ErrorCategory.NETWORK,
        )
    except (TimeoutError, socket.timeout) as e:
        return FetchResult.failure(
            requested,
            f"Failed to fetch URL: timeout ({e})",
            ErrorCategory.TIMEOUT,
        )
    except OSError as e:
        return FetchResult.failure(
            requested,
            f"Failed to fetch URL: {e}",
            ErrorCategory.NETWORK,
        )
