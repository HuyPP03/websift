"""Shared fixtures for offline characterization tests."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

import pytest


@pytest.fixture
def public_ip() -> str:
    # Must be a true global address (TEST-NET ranges are not is_global).
    return "8.8.8.8"


@pytest.fixture
def patch_dns(monkeypatch: pytest.MonkeyPatch, public_ip: str):
    """Patch socket.getaddrinfo so tests never hit real DNS."""

    def _getaddrinfo(host, port, *args, **kwargs):
        family = socket.AF_INET6 if ":" in public_ip else socket.AF_INET
        sockaddr = (public_ip, port if isinstance(port, int) else 0)
        return [(family, socket.SOCK_STREAM, 0, "", sockaddr)]

    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)
    return public_ip


class _FixtureState:
    def __init__(self) -> None:
        self.routes: dict[str, Callable[[BaseHTTPRequestHandler], None]] = {}
        self.requests: list[tuple[str, str, dict[str, str]]] = []


def _make_handler(state: _FixtureState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _dispatch(self) -> None:
            state.requests.append((self.command, self.path, dict(self.headers)))
            handler = state.routes.get(self.path) or state.routes.get("*")
            if handler is None:
                self.send_error(404, "not found")
                return
            handler(self)

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch()

        def do_HEAD(self) -> None:  # noqa: N802
            self._dispatch()

    return Handler


@pytest.fixture
def http_server():
    """Local HTTP server bound to 127.0.0.1 for offline fetch tests.

    Note: production SSRF blocks loopback, so tests that call fetch_raw against
    this server must either patch resolve_host or test only the handler layer.
    Prefer patching resolve_host to return 127.0.0.1 after validation bypass
    for integration-style tests that intentionally exercise urllib paths.
    """
    state = _FixtureState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base_url = f"http://{host}:{port}"

    class Server:
        def route(self, path: str, handler: Callable[[BaseHTTPRequestHandler], None]) -> None:
            state.routes[path] = handler

        def respond(
            self,
            path: str,
            *,
            body: bytes = b"ok",
            status: int = 200,
            headers: dict[str, str] | None = None,
        ) -> None:
            hdrs = {"Content-Type": "text/plain; charset=utf-8"}
            if headers:
                hdrs.update(headers)

            def _handler(h: BaseHTTPRequestHandler) -> None:
                h.send_response(status)
                for k, v in hdrs.items():
                    h.send_header(k, v)
                h.send_header("Content-Length", str(len(body)))
                h.end_headers()
                if h.command != "HEAD":
                    h.wfile.write(body)

            state.routes[path] = _handler

        def redirect(self, path: str, location: str, status: int = 302) -> None:
            def _handler(h: BaseHTTPRequestHandler) -> None:
                h.send_response(status)
                h.send_header("Location", location)
                h.send_header("Content-Length", "0")
                h.end_headers()

            state.routes[path] = _handler

        @property
        def base_url(self) -> str:
            return base_url

        @property
        def port(self) -> int:
            return int(port)

        @property
        def requests(self):
            return state.requests

        def url(self, path: str) -> str:
            return f"{base_url}{path}"

    try:
        yield Server()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def allow_loopback_fetch(monkeypatch: pytest.MonkeyPatch, http_server):
    """Allow fetch_raw against the local fixture server (loopback is blocked in prod)."""
    from urllib.parse import urlparse

    from web_search.security import ValidatedURL
    from web_search.security import resolve_host as real_resolve
    from web_search.security import validate_http_url as real_validate

    def _validate(url: str, *, allow_http: bool = True, allowed_ports=None):
        ok, reason, validated = real_validate(url, allow_http=allow_http, allowed_ports=allowed_ports)
        if ok:
            return ok, reason, validated
        parsed = urlparse(str(url).strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme in {"http", "https"} and host in {"127.0.0.1", "localhost"}:
            if parsed.scheme == "http" and not allow_http:
                return False, "Blocked: http URLs are not allowed (set FETCH_ALLOW_HTTP=true).", None
            if parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""):
                return False, "Blocked: URL must not contain embedded credentials.", None
            try:
                port = parsed.port
            except ValueError:
                return False, "Blocked: invalid port.", None
            eff = port if port is not None else (443 if parsed.scheme == "https" else 80)
            if allowed_ports is not None and len(allowed_ports) > 0 and eff not in allowed_ports:
                return False, f"Blocked: port {eff} is not in FETCH_ALLOWED_PORTS.", None
            return (
                True,
                "",
                ValidatedURL(
                    original=str(url).strip(),
                    scheme=parsed.scheme,
                    hostname=host,
                    port=eff,
                    parsed=parsed,
                ),
            )
        return ok, reason, validated

    def _resolve(hostname: str, port: int):
        if hostname in {"127.0.0.1", "localhost"}:
            return True, "", "127.0.0.1"
        return real_resolve(hostname, port)

    monkeypatch.setattr("web_search.http.validate_http_url", _validate)
    monkeypatch.setattr("web_search.http.resolve_host", _resolve)
    return http_server


def minimal_pdf_bytes(text: str = "hello pdf") -> bytes:
    """Build a tiny one-page PDF without external tools."""
    # Minimal valid-enough PDF for pypdf; if parsing fails tests still cover magic.
    content = f"""BT /F1 12 Tf 100 700 Td ({text}) Tj ET"""
    stream = content.encode("latin-1")
    parts = [
        b"%PDF-1.4\n",
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n",
        b"4 0 obj<< /Length " + str(len(stream)).encode() + b" >>stream\n",
        stream + b"\nendstream\nendobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]
    body = b"".join(parts)
    xref_offset = len(body)
    xref = (
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000000 00000 n \n"
    )
    # Offsets above are approximate; pypdf may still open via rebuild. Magic is enough for many tests.
    trailer = b"trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
    return body + xref + trailer


@pytest.fixture
def sample_pdf() -> bytes:
    return minimal_pdf_bytes()
