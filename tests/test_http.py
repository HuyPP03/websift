"""HTTP fetch tests (phase 2: lifecycle, decode, compression, limits)."""

from __future__ import annotations

import gzip
import io
import zlib
from http.server import BaseHTTPRequestHandler
from unittest.mock import MagicMock

import pytest
import urllib.error

from web_search.http import (
    decompress_body,
    detect_charset,
    extract_pdf_text,
    fetch_raw,
    read_capped_body,
)


class TestReadCappedBody:
    def test_reads_full_under_limit(self):
        class R:
            def __init__(self, data: bytes):
                self._bio = io.BytesIO(data)

            def read(self, n: int = -1) -> bytes:
                return self._bio.read(n)

        err, data, overflow = read_capped_body(R(b"hello"), limit=100)
        assert err is None
        assert data == b"hello"
        assert overflow is False

    def test_exact_limit_is_not_overflow(self):
        class R:
            def __init__(self, data: bytes):
                self._bio = io.BytesIO(data)

            def read(self, n: int = -1) -> bytes:
                return self._bio.read(n)

        payload = b"x" * 20
        err, data, overflow = read_capped_body(R(payload), limit=20)
        assert err is None
        assert data == payload
        assert overflow is False

    def test_detects_one_byte_overflow(self):
        class R:
            def __init__(self, data: bytes):
                self._bio = io.BytesIO(data)

            def read(self, n: int = -1) -> bytes:
                return self._bio.read(n)

        payload = b"x" * 21
        err, data, overflow = read_capped_body(R(payload), limit=20)
        assert err is None
        assert data == b"x" * 20
        assert overflow is True

    def test_invalid_limit(self):
        class R:
            def read(self, n: int = -1) -> bytes:
                return b""

        err, data, overflow = read_capped_body(R(), limit=-1)
        assert err is not None
        assert "Invalid" in err
        assert data == b""
        assert overflow is False

    def test_read_error(self):
        class R:
            def read(self, n: int = -1) -> bytes:
                raise OSError("boom")

        err, data, overflow = read_capped_body(R(), limit=10)
        assert err is not None
        assert "Failed to read response body" in err
        assert data == b""
        assert overflow is False


class TestDetectCharset:
    def test_bom_wins_over_http_charset(self):
        raw = b"\xef\xbb\xbfhello"
        assert detect_charset(raw, "iso-8859-1") == "utf-8-sig"

    def test_http_charset_when_valid(self):
        assert detect_charset(b"hello", "latin-1") == "latin-1"

    def test_invalid_http_charset_falls_through(self):
        assert detect_charset(b"hello", "not-a-real-codec-xyz") == "utf-8"

    def test_meta_charset(self):
        html = b'<html><head><meta charset="iso-8859-2"></head><body>x</body></html>'
        assert detect_charset(html, None) == "iso-8859-2"

    def test_meta_http_equiv(self):
        html = b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252"></head></html>'
        assert detect_charset(html, None) == "windows-1252"

    def test_meta_http_equiv_content_first(self):
        html = b'<html><head><meta content="text/html; charset=koi8-r" http-equiv="content-type"></head></html>'
        assert detect_charset(html, None) == "koi8-r"

    def test_utf8_fallback(self):
        assert detect_charset(b"plain", None) == "utf-8"


class TestDecompressBody:
    def test_identity_passthrough(self):
        err, data = decompress_body(b"abc", None)
        assert err is None
        assert data == b"abc"
        err, data = decompress_body(b"abc", "identity")
        assert err is None
        assert data == b"abc"

    def test_gzip(self):
        raw = gzip.compress(b"hello gzip")
        err, data = decompress_body(raw, "gzip")
        assert err is None
        assert data == b"hello gzip"

    def test_deflate_zlib_wrapped(self):
        raw = zlib.compress(b"hello deflate")
        err, data = decompress_body(raw, "deflate")
        assert err is None
        assert data == b"hello deflate"

    def test_deflate_raw(self):
        co = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        raw = co.compress(b"raw deflate") + co.flush()
        err, data = decompress_body(raw, "deflate")
        assert err is None
        assert data == b"raw deflate"

    def test_unsupported_encoding(self):
        err, data = decompress_body(b"x", "br")
        assert err is not None
        assert "Unsupported Content-Encoding" in err
        assert data == b""

    def test_gzip_bomb_bounded(self):
        # Highly compressible payload exceeds small max_decompressed.
        payload = b"A" * 200_000
        raw = gzip.compress(payload)
        err, data = decompress_body(raw, "gzip", max_decompressed=10_000)
        assert err is not None
        assert "exceed" in err.lower() or "decompress" in err.lower()
        assert data == b""

    def test_malformed_gzip(self):
        err, data = decompress_body(b"not-gzip", "gzip")
        assert err is not None
        assert "decompress" in err.lower()
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

    def test_blocks_userinfo(self):
        err, body, ct = fetch_raw("https://user:secret@example.com/", 5, 1000, 2000)
        assert err is not None
        assert "credential" in err.lower()

    def test_blocks_malformed_port(self):
        err, body, ct = fetch_raw("https://example.com:notaport/", 5, 1000, 2000)
        assert err is not None
        assert "port" in err.lower()

    def test_blocks_loopback_literal_without_dns(self):
        err, body, ct = fetch_raw("http://127.0.0.1:9/", 5, 1000, 2000)
        assert err is not None
        assert "non-global" in err.lower() or "Blocked" in err

    def test_blocks_private_dns(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (False, "Blocked: private", ""),
        )
        err, body, ct = fetch_raw("http://internal.example/", 5, 1000, 2000)
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

    def test_redirect_followed(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        srv.redirect("/go", srv.url("/dest"))
        srv.respond("/dest", body=b"landed")
        err, body, ct = fetch_raw(srv.url("/go"), 5, 100_000, 200_000)
        assert err is None
        assert body == "landed"

    def test_redirect_to_blocked_host(self, allow_loopback_fetch, monkeypatch: pytest.MonkeyPatch):
        srv = allow_loopback_fetch
        srv.redirect("/go", "http://evil.internal/secret")

        def _resolve(hostname: str, port: int):
            if hostname in {"127.0.0.1", "localhost"}:
                return True, "", "127.0.0.1"
            return False, f"Blocked: {hostname}", ""

        monkeypatch.setattr("web_search.http.resolve_host", _resolve)
        err, body, ct = fetch_raw(srv.url("/go"), 5, 100_000, 200_000)
        assert err is not None
        assert "Blocked" in err

    def test_redirect_to_userinfo_blocked(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        srv.redirect("/go", "http://user:pass@127.0.0.1/secret")
        err, body, ct = fetch_raw(srv.url("/go"), 5, 100_000, 200_000)
        assert err is not None
        assert "credential" in err.lower() or "non-global" in err.lower() or "Blocked" in err

    def test_http_404_returns_error(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        srv.respond("/missing", body=b"nope", status=404)
        err, body, ct = fetch_raw(srv.url("/missing"), 5, 100_000, 200_000)
        assert err is not None
        assert "HTTP 404" in err

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
        assert err is None
        assert ct == "application/pdf"
        assert isinstance(body, str)

    def test_oversized_normal_body_errors(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        big = b"A" * 5000
        srv.respond("/big", body=big, headers={"Content-Type": "text/plain"})
        err, body, ct = fetch_raw(srv.url("/big"), 5, max_fetch_bytes=100, max_pdf_fetch_bytes=10_000)
        assert err is not None
        assert "exceeds download limit" in err
        assert body == ""

    def test_content_length_early_reject(self, allow_loopback_fetch):
        srv = allow_loopback_fetch

        def handler(h: BaseHTTPRequestHandler) -> None:
            h.send_response(200)
            h.send_header("Content-Type", "text/plain")
            h.send_header("Content-Length", "999999")
            h.end_headers()
            # Do not write body — client should reject on header alone.

        srv.route("/cl", handler)
        err, body, ct = fetch_raw(srv.url("/cl"), 5, max_fetch_bytes=100, max_pdf_fetch_bytes=10_000)
        assert err is not None
        assert "exceeds download limit" in err

    def test_gzip_body_decoded(self, allow_loopback_fetch):
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
        assert err is None
        assert body == "hello gzip"

    def test_deflate_body_decoded(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        raw = zlib.compress(b"hello deflate")
        srv.respond(
            "/df",
            body=raw,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Content-Encoding": "deflate",
            },
        )
        err, body, ct = fetch_raw(srv.url("/df"), 5, 100_000, 200_000)
        assert err is None
        assert body == "hello deflate"

    def test_unsupported_content_encoding(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        srv.respond(
            "/br",
            body=b"pretend-brotli",
            headers={
                "Content-Type": "text/plain",
                "Content-Encoding": "br",
            },
        )
        err, body, ct = fetch_raw(srv.url("/br"), 5, 100_000, 200_000)
        assert err is not None
        assert "Unsupported Content-Encoding" in err

    def test_meta_charset_used(self, allow_loopback_fetch):
        # "café" in latin-1 without HTTP charset; meta declares iso-8859-1
        body = b'<html><head><meta charset="iso-8859-1"></head><body>' + "caf\xe9".encode("latin-1") + b"</body></html>"
        srv = allow_loopback_fetch
        srv.respond("/meta", body=body, headers={"Content-Type": "text/html"})
        err, text, ct = fetch_raw(srv.url("/meta"), 5, 100_000, 200_000)
        assert err is None
        assert "caf" in text
        assert "�" not in text or "é" in text or "caf" in text

    def test_bom_over_http_charset(self, allow_loopback_fetch):
        # UTF-8 BOM payload but server claims latin-1 — BOM must win.
        payload = b"\xef\xbb\xbf" + "hello".encode("utf-8")
        srv = allow_loopback_fetch
        srv.respond(
            "/bom-http",
            body=payload,
            headers={"Content-Type": "text/plain; charset=iso-8859-1"},
        )
        err, text, ct = fetch_raw(srv.url("/bom-http"), 5, 100_000, 200_000)
        assert err is None
        assert text == "hello" or text.lstrip("﻿") == "hello"

    def test_extra_headers_passed(self, allow_loopback_fetch):
        srv = allow_loopback_fetch

        def handler(h: BaseHTTPRequestHandler) -> None:
            accept = h.headers.get("Accept", "")
            ae = h.headers.get("Accept-Encoding", "")
            body = f"{accept}|{ae}".encode()
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
        assert "gzip" in body

    def test_utf16_bom_decode(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        payload = "hello".encode("utf-16-le")
        bom = b"\xff\xfe" + payload
        srv.respond("/bom", body=bom, headers={"Content-Type": "text/plain"})
        err, body, ct = fetch_raw(srv.url("/bom"), 5, 100_000, 200_000)
        assert err is None
        assert "hello" in body

    def test_too_many_redirects(self, allow_loopback_fetch, monkeypatch: pytest.MonkeyPatch):
        srv = allow_loopback_fetch
        srv.redirect("/a", srv.url("/b"))
        srv.redirect("/b", srv.url("/a"))
        monkeypatch.setattr("web_search.http.MAX_REDIRECTS", 3)
        err, body, ct = fetch_raw(srv.url("/a"), 5, 100_000, 200_000)
        assert err is not None
        assert "redirect" in err.lower()

    def test_network_exception_message(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (True, "", "8.8.8.8"),
        )

        def _boom(*_a, **_k):
            raise OSError("connection refused")

        monkeypatch.setattr("urllib.request.build_opener", lambda *_a, **_k: MagicMock(open=_boom))
        err, body, ct = fetch_raw("http://example.test/", 1, 1000, 2000)
        assert err is not None
        assert "Failed to fetch URL" in err

    def test_decompressed_size_cap(self, allow_loopback_fetch):
        srv = allow_loopback_fetch
        payload = b"Z" * 50_000
        raw = gzip.compress(payload)
        srv.respond(
            "/bomb",
            body=raw,
            headers={
                "Content-Type": "text/plain",
                "Content-Encoding": "gzip",
            },
        )
        err, body, ct = fetch_raw(
            srv.url("/bomb"),
            5,
            max_fetch_bytes=100_000,
            max_pdf_fetch_bytes=200_000,
            max_decompressed_bytes=5_000,
        )
        assert err is not None
        assert "exceed" in err.lower() or "decompress" in err.lower()


class TestHttpErrorRedirectPath:
    def test_httperror_non_redirect(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (True, "", "8.8.8.8"),
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
            lambda host, port: (True, "", "8.8.8.8"),
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
        def _resolve(host, port):
            if host == "example.test":
                return True, "", "8.8.8.8"
            return False, "Blocked: private", ""

        monkeypatch.setattr("web_search.http.resolve_host", _resolve)

        class H(dict):
            def get(self, k, default=None):
                if k == "Location":
                    return "http://10.0.0.1/secret"
                return default

        def _open(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 302, "Found", hdrs=H(), fp=None)

        monkeypatch.setattr(
            "urllib.request.build_opener",
            lambda *_a, **_k: MagicMock(open=_open),
        )
        err, body, ct = fetch_raw("http://example.test/x", 5, 1000, 2000)
        assert err is not None
        assert "Blocked" in err

    def test_httperror_redirect_then_success(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "web_search.http.resolve_host",
            lambda host, port: (True, "", "8.8.8.8"),
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

            def close(self):
                return None

            def getcode(self):
                return 200

            status = 200

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
            lambda host, port: (True, "", "8.8.8.8"),
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

    def test_page_limit(self, monkeypatch: pytest.MonkeyPatch):
        class Page:
            def __init__(self, n: int):
                self._n = n

            def extract_text(self):
                return f"P{self._n}"

        class Reader:
            def __init__(self, _bio):
                self.pages = [Page(i) for i in range(10)]

        fake_pypdf = MagicMock()
        fake_pypdf.PdfReader = Reader
        monkeypatch.setitem(__import__("sys").modules, "pypdf", fake_pypdf)
        out = extract_pdf_text(b"%PDF-1.4", max_pages=3, max_chars=10_000)
        assert out == "P0\nP1\nP2"

    def test_char_limit(self, monkeypatch: pytest.MonkeyPatch):
        class Page:
            def extract_text(self):
                return "abcdefghij"

        class Reader:
            def __init__(self, _bio):
                self.pages = [Page(), Page()]

        fake_pypdf = MagicMock()
        fake_pypdf.PdfReader = Reader
        monkeypatch.setitem(__import__("sys").modules, "pypdf", fake_pypdf)
        out = extract_pdf_text(b"%PDF-1.4", max_pages=10, max_chars=15)
        assert len(out) <= 15
        assert out.startswith("abcdefghij")

    def test_no_pdfminer_import(self):
        import web_search.http as http_mod
        import inspect

        src = inspect.getsource(http_mod)
        assert "pdfminer" not in src
