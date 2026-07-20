"""HTTP helpers: redirect suppression, SNI handler, body reader, PDF extractor."""

import http.client
import random
import socket
import ssl
import urllib.error
import urllib.request
from typing import Optional

from web_search.config import MAX_REDIRECTS, UNICODE_BOM_CODECS, USER_AGENTS
from web_search.content import has_binary_magic, has_pdf_magic, is_text_mime, looks_binary
from web_search.security import resolve_host

from urllib.parse import urljoin, urlparse, urlunparse
import re


class _NoRedirect(urllib.request.HTTPErrorProcessor):
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


def fetch_raw(
    url: str,
    timeout: int,
    max_fetch_bytes: int,
    max_pdf_fetch_bytes: int,
    extra_headers: Optional[dict] = None,
) -> tuple[Optional[str], str, str]:
    """Fetch URL with SSRF protection, DNS pinning, redirect following."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Blocked: only http/https allowed (got {parsed.scheme!r}).", "", ""
    if not parsed.hostname:
        return "Blocked: URL missing hostname.", "", ""

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ok, reason, pinned_ip = resolve_host(parsed.hostname, port)
    if not ok:
        return reason, "", ""

    try:
        current_url = url
        current_host = parsed.hostname
        ua = random.choice(USER_AGENTS)

        for _ in range(MAX_REDIRECTS):
            cp = urlparse(current_url)
            ip_str = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
            ip_netloc = f"{ip_str}:{cp.port}" if cp.port else ip_str
            pinned_url = urlunparse(cp._replace(netloc=ip_netloc))

            opener = urllib.request.build_opener(_NoRedirect, _SNIHTTPSHandler(current_host))
            headers = {"User-Agent": ua, "Host": current_host}
            if extra_headers:
                headers.update(extra_headers)

            req = urllib.request.Request(pinned_url, headers=headers)
            try:
                resp = opener.open(req, timeout=timeout)
            except urllib.error.HTTPError as e:
                if e.code not in (301, 302, 303, 307, 308):
                    return f"Failed to fetch URL: HTTP {e.code} {getattr(e, 'reason', '')}", "", ""
                location = e.headers.get("Location")
                if not location:
                    return "Failed to fetch: redirect missing Location.", "", ""
                current_url = urljoin(current_url, location)
                rp = urlparse(current_url)
                if rp.scheme not in ("http", "https") or not rp.hostname:
                    return "Blocked: redirect target not valid http/https.", "", ""
                rp_port = rp.port or (443 if rp.scheme == "https" else 80)
                ok2, reason2, pinned_ip = resolve_host(rp.hostname, rp_port)
                if not ok2:
                    return reason2, "", ""
                current_host = rp.hostname
                continue

            content_type = (resp.headers.get_content_type() or "").lower() if resp.headers.get("Content-Type") else ""
            declared_pdf = content_type == "application/pdf"
            read_limit = max_pdf_fetch_bytes + 1 if declared_pdf else max_fetch_bytes
            err, raw_bytes = read_capped_body(resp, read_limit)
            if err:
                return err, "", ""

            if not declared_pdf and len(raw_bytes) == max_fetch_bytes and has_pdf_magic(raw_bytes):
                err2, tail = read_capped_body(resp, max_pdf_fetch_bytes - max_fetch_bytes + 1)
                if err2:
                    return err2, "", ""
                raw_bytes += tail

            break
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

        declared_enc = resp.headers.get_content_charset()
        bom_codec = next((c for bom, c in UNICODE_BOM_CODECS if raw_bytes.startswith(bom)), None)
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
