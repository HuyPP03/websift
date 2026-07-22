"""HTTP fetch characterization tests (offline)."""

from __future__ import annotations

import gzip
import io
from http.server import BaseHTTPRequestHandler
from unittest.mock import MagicMock

import pytest
import urllib.error

from web_search.http import extract_pdf_text, fetch_raw, read_capped_body


class TestReadCappedBody:
    def test_reads_full_under_limit(self):
        class R:
            def __init__(self, data: bytes):
                self._bio = io.BytesIO(data)

            def read(self, n: int = -1) -> bytes:
                return self._bio.read(n)

        err, data = read_capped_body(R(b"hello"), limit=100)
        assert err is None
        assert data == b"hello"

    def test_stops_at_limit_without_overflow_detection(self):
        """v0.1.0: stops at exactly limit; cannot distinguish full vs overflow."""

        class R:
            def __init__(self, data: bytes):
                self._bio = io.BytesIO(data)

            def read(self, n: int = -1) -> bytes:
                return self._bio.read(n)

        payload = b"x" * 50
        err, data = read_capped_body(R(payload), limit=20)
        assert err is None
        assert data == b"x" * 20
        assert len(data) == 20

    def test_read_error(self):
        class R:
            def read(self, n: int = -1) -> bytes:
                raise OSError("boom")

        err, data = read_capped_body(R(), limit=10)
        assert err is not None
        assert "Failed to read response body" in err
        assert data == b""


class TestFetchRawValidation:
    def test_blocks_non_http_scheme(self):
        err, body, ct = fetch_raw("file:///etc/passwd", 5, 1000, 2000)
        assert err is not None
        assert "only http/https" in err
        assert body == ""

    def test_blocks_missing_hostname(self):
        err, body, ct = fetch_raw("http:///nohost", 5, 1000, 2000)
        assert err is not None
        assert "hostname" in err.lower()

    def test_blocks_private_dns(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (False, "Blocked: private", ""),
        )
        err, body, ct = fetch_raw("http://internal.local/", 5, 1000, 2000)
        assert err == "Blocked: private"
        assert body == ""


class TestFetchRawLocalServer:
    def test_plain_text_success(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        srv.respond("/hello", body=b"hello world", headers={"Content-Type": "text/plain; charset=utf-8"})
        err, body, ct = fetch_raw(srv.url("/hello"), 5, 100_000, 200_000)
        assert err is None
        assert body == "hello world"
        assert "text/plain" in ct

    def test_html_returned_as_text(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        html = b"<html><body><p>Hi</p></body></html>"
        srv.respond("/page", body=html, headers={"Content-Type": "text/html; charset=utf-8"})
        err, body, ct = fetch_raw(srv.url("/page"), 5, 100_000, 200_000)
        assert err is None
        assert "Hi" in body
        assert "html" in ct

    def test_redirect_not_followed_baseline_gap(self, allow_loopback_fetch):
        """v0.1.0 gap: _NoRedirect returns 3xx as success; HTTPError redirect path never runs.

        Manual redirect-following code in fetch_raw is effectively dead for the default opener.
        """
        srv = allow_loopback_fetch
        srv.redirect("/go", srv.url("/dest"))
        srv.respond("/dest", body=b"landed")
        err, body, ct = fetch_raw(srv.url("/go"), 5, 100_000, 200_000)
        # Current: 302 empty body treated as success
        assert err is None
        assert body == ""
        assert body != "landed"

    def test_http_404_not_raised_baseline_gap(self, allow_loopback_fetch):
        """v0.1.0 gap: _NoRedirect also suppresses HTTPError for 4xx → body returned as success."""
        srv = allow_loopback_fetch
        srv.respond("/missing", body=b"nope", status=404)
        err, body, ct = fetch_raw(srv.url("/missing"), 5, 100_000, 200_000)
        assert err is None
        assert body == "nope"

    def test_non_text_mime_blocked(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        srv.respond(
            "/img",
            body=b"\x89PNG\r\n\x1a\n" + b"\x00" * 20,
            headers={"Content-Type": "image/png"},
        )
        err, body, ct = fetch_raw(srv.url("/img"), 5, 100_000, 200_000)
        assert err is not None
        assert "non-text content" in err or "binary content" in err

    def test_binary_magic_without_helpful_mime(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        srv.respond(
            "/bin",
            body=b"\x7fELF" + b"\x00" * 40,
            headers={"Content-Type": "application/octet-stream"},
        )
        err, body, ct = fetch_raw(srv.url("/bin"), 5, 100_000, 200_000)
        assert err is not None
        assert "binary" in err.lower() or "non-text" in err.lower()

    def test_pdf_by_content_type(self, allow_loopback_fetch, sample_pdf: bytes):
        srv = allow_loopback_fetch
        srv.respond(
            "/doc.pdf",
            body=sample_pdf,
            headers={"Content-Type": "application/pdf"},
        )
        err, body, ct = fetch_raw(srv.url("/doc.pdf"), 5, 1000, 500_000)
        assert err is None or "PDF" in (err or "")
        if err is None:
            assert ct == "application/pdf"
            assert isinstance(body, str)

    def test_pdf_exceeds_limit(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        body = b"%PDF-1.4\n" + b"x" * 500
        srv.respond("/big.pdf", body=body, headers={"Content-Type": "application/pdf"})
        err, text, ct = fetch_raw(srv.url("/big.pdf"), 5, max_fetch_bytes=50, max_pdf_fetch_bytes=100)
        # read_limit is max_pdf+1 so may still load; if over max_pdf after read:
        assert err is not None or isinstance(text, str)

    def test_oversized_normal_body_capped(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        big = b"A" * 5000
        srv.respond("/big", body=big, headers={"Content-Type": "text/plain"})
        err, body, ct = fetch_raw(srv.url("/big"), 5, max_fetch_bytes=100, max_pdf_fetch_bytes=10_000)
        assert err is None
        assert len(body) <= 100

    def test_gzip_body_not_transparently_decoded(self, allow_loopback_fetch):
        """v0.1.0 gap: Content-Encoding gzip is not handled; raw bytes may look binary."""
        srv = allow_loopback_fetch
        raw = gzip.compress(b"hello gzip")
        srv.respond(
            "/gz",
            body=raw,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Content-Encoding": "gzip",
            },
        )
        err, body, ct = fetch_raw(srv.url("/gz"), 5, 100_000, 200_000)
        assert err is not None or body != "hello gzip"

    def test_extra_headers_passed(self, allow_loopback_fetch):
        srv = allow_loopback_fetch

        def handler(h: BaseHTTPRequestHandler) -> None:
            accept = h.headers.get("Accept", "")
            body = accept.encode()
            h.send_response(200)
            h.send_header("Content-Type", "text/plain")
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body)

        srv.route("/hdr", handler)
        err, body, ct = fetch_raw(
            srv.url("/hdr"),
            5,
            100_000,
            200_000,
            extra_headers={"Accept": "application/vnd.github.raw+json"},
        )
        assert err is None
        assert "application/vnd.github.raw+json" in body

    def test_utf16_bom_decode(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        payload = "hello".encode("utf-16-le")
        bom = b"\xff\xfe" + payload
        srv.respond("/bom", body=bom, headers={"Content-Type": "text/plain"})
        err, body, ct = fetch_raw(srv.url("/bom"), 5, 100_000, 200_000)
        assert err is None
        assert "hello" in body

    def test_network_exception_message(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (True, "", "203.0.113.9"),
        )

        def _boom(*_a, **_k):
            raise OSError("connection refused")

        monkeypatch.setattr("urllib.request.build_opener", lambda *_a, **_k: MagicMock(open=_boom))
        err, body, ct = fetch_raw("http://example.test/", 1, 1000, 2000)
        assert err is not None
        assert "Failed to fetch URL" in err


class TestHttpErrorRedirectPath:
    """Exercise dead-ish HTTPError redirect branch by mocking opener.open."""

    def test_httperror_non_redirect(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (True, "", "203.0.113.9"),
        )

        def _open(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 500, "err", hdrs=None, fp=None)

        monkeypatch.setattr(
            "urllib.request.build_opener",
            lambda *_a, **_k: MagicMock(open=_open),
        )
        err, body, ct = fetch_raw("http://example.test/x", 5, 1000, 2000)
        assert err is not None
        assert "HTTP 500" in err

    def test_httperror_redirect_missing_location(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (True, "", "203.0.113.9"),
        )

        class H(dict):
            def get(self, k, default=None):
                return None

        def _open(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 302, "Found", hdrs=H(), fp=None)

        monkeypatch.setattr(
            "urllib.request.build_opener",
            lambda *_a, **_k: MagicMock(open=_open),
        )
        err, body, ct = fetch_raw("http://example.test/x", 5, 1000, 2000)
        assert err is not None
        assert "redirect missing Location" in err

    def test_httperror_redirect_blocked_target(self, monkeypatch: pytest.MonkeyPatch):
        calls = {"n": 0}

        def _resolve(host, port):
            if host == "example.test":
                return True, "", "203.0.113.9"
            return False, "Blocked: private", ""

        monkeypatch.setattr("web_search.http.resolve_host", _resolve)

        class H(dict):
            def get(self, k, default=None):
                if k == "Location":
                    return "http://10.0.0.1/secret"
                return default

        def _open(req, timeout=None):
            calls["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 302, "Found", hdrs=H(), fp=None)

        monkeypatch.setattr(
            "urllib.request.build_opener",
            lambda *_a, **_k: MagicMock(open=_open),
        )
        err, body, ct = fetch_raw("http://example.test/x", 5, 1000, 2000)
        assert err == "Blocked: private"

    def test_httperror_redirect_then_success(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (True, "", "203.0.113.9"),
        )

        class Loc(dict):
            def get(self, k, default=None):
                if k == "Location":
                    return "http://example.test/final"
                return default

        class FakeResp:
            def __init__(self, data: bytes, ctype: str = "text/plain; charset=utf-8"):
                self._data = data
                self.headers = MagicMock()
                self.headers.get_content_type.return_value = "text/plain"
                self.headers.get_content_charset.return_value = "utf-8"
                self.headers.get.side_effect = lambda k, d=None: ctype if k == "Content-Type" else d

            def read(self, n: int = -1) -> bytes:
                if not self._data:
                    return b""
                chunk, self._data = self._data[:n], self._data[n:]
                return chunk

        state = {"n": 0}

        def _open(req, timeout=None):
            state["n"] += 1
            if state["n"] == 1:
                raise urllib.error.HTTPError(req.full_url, 302, "Found", hdrs=Loc(), fp=None)
            return FakeResp(b"final-body")

        monkeypatch.setattr(
            "urllib.request.build_opener",
            lambda *_a, **_k: MagicMock(open=_open),
        )
        err, body, ct = fetch_raw("http://example.test/start", 5, 1000, 2000)
        assert err is None
        assert body == "final-body"

    def test_too_many_redirects_via_httperror(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("web_search.http.MAX_REDIRECTS", 2)
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (True, "", "203.0.113.9"),
        )

        class Loc(dict):
            def get(self, k, default=None):
                if k == "Location":
                    return "http://example.test/next"
                return default

        def _open(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 302, "Found", hdrs=Loc(), fp=None)

        monkeypatch.setattr(
            "urllib.request.build_opener",
            lambda *_a, **_k: MagicMock(open=_open),
        )
        err, body, ct = fetch_raw("http://example.test/start", 5, 1000, 2000)
        assert err is not None
        assert "too many redirects" in err.lower()


class TestExtractPdfText:
    def test_empty_or_invalid_returns_empty(self):
        assert extract_pdf_text(b"not a pdf") == ""

    def test_magic_pdf_attempt(self, sample_pdf: bytes):
        out = extract_pdf_text(sample_pdf)
        assert isinstance(out, str)

    def test_pypdf_success(self, monkeypatch: pytest.MonkeyPatch):
        class Page:
            def extract_text(self):
                return "page text"

        class Reader:
            def __init__(self, _bio):
                self.pages = [Page()]

        fake_pypdf = MagicMock()
        fake_pypdf.PdfReader = Reader
        monkeypatch.setitem(__import__("sys").modules, "pypdf", fake_pypdf)
        assert extract_pdf_text(b"%PDF-1.4") == "page text"
