"""HTTP helpers: redirect suppression, SNI handler, body reader, PDF extractor."""

from __future__ import annotations

import http.client
import random
import re
import socket
import ssl
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

from web_search.config import MAX_REDIRECTS, UNICODE_BOM_CODECS, USER_AGENTS
from web_search.content import has_binary_magic, has_pdf_magic, is_text_mime, looks_binary
from web_search.security import resolve_host, validate_http_url


_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    """Return responses as-is so callers can validate redirects manually (SSRF)."""

    def http_response(self, request, response):
        return response

    https_response = http_response


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection to a pinned IP that presents the real hostname for SNI
    and certificate validation."""

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


def read_capped_body(resp, limit: int, chunk: int = 65536) -> tuple[Optional[str], bytes]:
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            data = resp.read(min(chunk, limit - total))
            if not data:
                break
            chunks.append(data)
            total += len(data)
            if total >= limit:
                break
    except Exception as e:
        return f"Failed to read response body: {e}", b""
    return None, b"".join(chunks)


def extract_pdf_text(raw: bytes) -> str:
    try:
        import io

        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if text:
            return text
    except Exception:
        pass
    try:
        import io
        from pdfminer.high_level import extract_text as pm_extract

        return (pm_extract(io.BytesIO(raw)) or "").strip()
    except Exception:
        pass
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
    """Build netloc for a connection to pinned_ip while preserving non-default ports."""
    ip_str = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
    default = 443 if scheme == "https" else 80
    if port == default:
        return ip_str
    return f"{ip_str}:{port}"


def fetch_raw(
    url: str,
    timeout: int,
    max_fetch_bytes: int,
    max_pdf_fetch_bytes: int,
    extra_headers: Optional[dict] = None,
) -> tuple[Optional[str], str, str]:
    """Fetch URL with SSRF protection, DNS pinning, redirect following."""
    ok, reason, validated = validate_http_url(url)
    if not ok or validated is None:
        return reason, "", ""

    # Literal IPs already checked in validate_http_url; still resolve hostnames.
    ok, reason, pinned_ip = resolve_host(validated.hostname, validated.port)
    if not ok:
        return reason, "", ""

    try:
        current_url = validated.original
        current_host = validated.hostname
        current_port = validated.port
        current_scheme = validated.scheme
        ua = random.choice(USER_AGENTS)

        for _ in range(MAX_REDIRECTS):
            cp = urlparse(current_url)
            ip_netloc = _pinned_netloc(current_port, current_scheme, pinned_ip)
            pinned_url = urlunparse(cp._replace(netloc=ip_netloc, scheme=current_scheme))

            opener = urllib.request.build_opener(_NoRedirect, _SNIHTTPSHandler(current_host))
            headers = {"User-Agent": ua, "Host": current_host}
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
                        _close_quiet(resp)
                        return f"Failed to fetch URL: HTTP {e.code} {reason_txt}".rstrip(), "", ""

                if status in _REDIRECT_CODES:
                    location = resp.headers.get("Location") if resp is not None else None
                    _close_quiet(resp)
                    resp = None
                    if not location:
                        return "Failed to fetch: redirect missing Location.", "", ""

                    next_url = urljoin(current_url, location)
                    ok_u, reason_u, vnext = validate_http_url(next_url)
                    if not ok_u or vnext is None:
                        return reason_u or "Blocked: redirect target not valid http/https.", "", ""

                    ok2, reason2, pinned_ip = resolve_host(vnext.hostname, vnext.port)
                    if not ok2:
                        return reason2, "", ""

                    current_url = next_url
                    current_host = vnext.hostname
                    current_port = vnext.port
                    current_scheme = vnext.scheme
                    continue

                if status >= 400:
                    _close_quiet(resp)
                    return f"Failed to fetch URL: HTTP {status}", "", ""

                content_type = (
                    (resp.headers.get_content_type() or "").lower()
                    if resp.headers.get("Content-Type")
                    else ""
                )
                declared_enc = resp.headers.get_content_charset()
                declared_pdf = content_type == "application/pdf"
                read_limit = max_pdf_fetch_bytes + 1 if declared_pdf else max_fetch_bytes
                err, raw_bytes = read_capped_body(resp, read_limit)
                if err:
                    _close_quiet(resp)
                    return err, "", ""

                if not declared_pdf and len(raw_bytes) == max_fetch_bytes and has_pdf_magic(raw_bytes):
                    err2, tail = read_capped_body(resp, max_pdf_fetch_bytes - max_fetch_bytes + 1)
                    if err2:
                        _close_quiet(resp)
                        return err2, "", ""
                    raw_bytes += tail

                _close_quiet(resp)
                resp = None
                break
            finally:
                _close_quiet(resp)
        else:
            return "Failed to fetch: too many redirects.", "", ""

        is_pdf = declared_pdf or has_pdf_magic(raw_bytes)
        if is_pdf:
            if len(raw_bytes) > max_pdf_fetch_bytes:
                return "(PDF exceeds download limit)", "", content_type
            pdf_text = extract_pdf_text(raw_bytes)
            return None, pdf_text or "(PDF contains no extractable text)", "application/pdf"

        if content_type and not is_text_mime(content_type):
            m = re.match(r"[\w.+-]+/[\w.+-]+", content_type)
            return f"(non-text content: {m.group(0) if m else 'unknown type'})", "", content_type

        if has_binary_magic(raw_bytes):
            return f"(binary content, {len(raw_bytes)} bytes)", "", content_type

        bom_codec = next((c for bom, c in UNICODE_BOM_CODECS if raw_bytes.startswith(bom)), None)
        # Phase 2 will enforce BOM → HTTP → meta → utf-8. Keep prior order for now.
        text = raw_bytes.decode(declared_enc or bom_codec or "utf-8", errors="replace")

        if looks_binary(text):
            if declared_enc in (None, "iso8859-1"):
                alt = raw_bytes.decode("cp1252", "replace")
                if not looks_binary(alt):
                    text = alt
                else:
                    return f"(binary content, {len(raw_bytes)} bytes)", "", content_type
            else:
                return f"(binary content, {len(raw_bytes)} bytes)", "", content_type

        return None, text, content_type

    except urllib.error.HTTPError as e:
        return f"Failed to fetch URL: HTTP {e.code} {getattr(e, 'reason', '')}", "", ""
    except Exception as e:
        return f"Failed to fetch URL: {e}", "", ""
