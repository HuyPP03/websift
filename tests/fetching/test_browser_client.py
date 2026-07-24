"""Remote browser backend tests without network or optional httpx install."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from websift.models import ErrorCategory
from websift.providers.base import FetchContext
from websift.settings import BrowserSettings


class FakeHTTPError(Exception):
    pass


class FakeTimeout(FakeHTTPError):
    pass


class FakeConnectError(FakeHTTPError):
    pass


class FakeConnectTimeout(FakeTimeout, FakeConnectError):
    pass


def FakeTimeoutFactory(**kwargs):
    """Return a dummy timeout object (accepts any kwargs)."""
    return SimpleNamespace(**kwargs)


class FakeResponse:
    def __init__(self, payload, *, status=200, headers=None, chunks=None):
        body = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
        self.status_code = status
        self.headers = {"X-Websift-Browser-Protocol": "1", **(headers or {})}
        self._chunks = chunks if chunks is not None else [body]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def iter_bytes(self):
        yield from self._chunks


class FakeClient:
    instances = []
    response = None
    raise_exception = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.closed = False
        self.__class__.instances.append(self)

    def stream(self, method, url, json):
        self.calls.append((method, url, json))
        if self.__class__.raise_exception is not None:
            raise self.__class__.raise_exception
        return self.__class__.response

    def close(self):
        self.closed = True


@pytest.fixture
def fake_httpx(monkeypatch):
    FakeClient.instances.clear()
    FakeClient.response = None
    FakeClient.raise_exception = None
    module = SimpleNamespace(
        Client=FakeClient,
        HTTPError=FakeHTTPError,
        TimeoutException=FakeTimeout,
        Timeout=FakeTimeoutFactory,
        ConnectError=FakeConnectError,
        ConnectTimeout=FakeConnectTimeout,
    )
    monkeypatch.setitem(sys.modules, "httpx", module)
    return module


def success_payload(**overrides):
    result = {
        "html": "<html><main><h1>Rendered</h1><p>Browser content</p></main></html>",
        "final_url": "https://example.com/final",
        "content_type": "text/html",
        "status_code": 200,
        "bytes_read": 70,
        "redirect_count": 1,
    }
    result.update(overrides)
    return {"protocol_version": "1", "ok": True, "result": result}


def make_backend(fake_httpx, **settings):
    from websift.fetching.browser_client import RemoteBrowserBackend

    defaults = {"endpoint": "https://browser.example", "bearer_token": "secret"}
    defaults.update(settings)
    return RemoteBrowserBackend(BrowserSettings(**defaults), FetchContext(max_page_chars=1000))


def test_lazy_missing_extra_hint(monkeypatch):
    import builtins

    from websift.fetching import browser_client

    real_import = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(ImportError, match=r"pip install 'websift\[browser\]'"):
        browser_client.RemoteBrowserBackend(BrowserSettings(endpoint="https://browser.example"), FetchContext())


def test_fixed_endpoint_auth_no_redirects_and_request_policy(fake_httpx):
    FakeClient.response = FakeResponse(success_payload())
    backend = make_backend(fake_httpx)
    result = backend.fetch("https://example.com/page")
    client = FakeClient.instances[-1]
    assert result.ok
    assert client.kwargs["follow_redirects"] is False
    assert client.kwargs["headers"]["Authorization"] == "Bearer secret"
    method, endpoint, request = client.calls[0]
    assert (method, endpoint) == ("POST", "https://browser.example/v1/render")
    assert request["url"] == "https://example.com/page"
    assert request["protocol_version"] == "1"
    assert request["policy"]["allow_http"] is True


def test_protocol_mismatch(fake_httpx):
    FakeClient.response = FakeResponse(success_payload(), headers={"X-Websift-Browser-Protocol": "2"})
    result = make_backend(fake_httpx).fetch("https://example.com")
    assert result.error_category == ErrorCategory.PROVIDER
    assert "mismatch" in result.error_message


@pytest.mark.parametrize("response", [b"not json", b"[]"])
def test_malformed_response(fake_httpx, response):
    FakeClient.response = FakeResponse(response)
    result = make_backend(fake_httpx).fetch("https://example.com")
    assert result.error_category == ErrorCategory.DECODE


def test_oversized_stream_response(fake_httpx):
    FakeClient.response = FakeResponse(b"{}", chunks=[b"x" * 8, b"y" * 8])
    result = make_backend(fake_httpx, max_html_bytes=10, max_response_bytes=10).fetch("https://example.com")
    assert result.error_category == ErrorCategory.DECODE
    assert "byte limit" in result.error_message


def test_failure_mapping_sanitizes_token_and_unknown_category(fake_httpx):
    FakeClient.response = FakeResponse(
        {
            "protocol_version": "1",
            "ok": False,
            "error": {"category": "service_internal", "message": "failure secret\nAuthorization: Bearer secret"},
        }
    )
    result = make_backend(fake_httpx).fetch("https://example.com")
    assert result.error_category == ErrorCategory.UNKNOWN
    assert "secret" not in result.error_message
    assert "\n" not in result.error_message


def test_success_extracts_rendered_html_and_preserves_metadata(fake_httpx):
    FakeClient.response = FakeResponse(success_payload())
    result = make_backend(fake_httpx).fetch("https://example.com")
    assert result.ok
    assert "Rendered" in result.content
    assert "Browser content" in result.content
    assert result.final_url == "https://example.com/final"
    assert result.status_code == 200
    assert result.bytes_read == 70
    assert result.redirect_count == 1


def test_fingerprint_excludes_token_and_close(fake_httpx):
    FakeClient.response = FakeResponse(success_payload())
    backend = make_backend(fake_httpx)
    assert "secret" not in backend.fingerprint
    assert "browser.example" not in backend.fingerprint
    client = FakeClient.instances[-1]
    backend.close()
    assert client.closed is True


def test_connect_error_returns_network_failure(fake_httpx):
    FakeClient.raise_exception = fake_httpx.ConnectError("connection refused")
    result = make_backend(fake_httpx).fetch("https://example.com")
    assert not result.ok
    assert result.error_category == ErrorCategory.NETWORK
    assert "unreachable" in result.error_message


def test_connect_timeout_returns_network_failure(fake_httpx):
    FakeClient.raise_exception = fake_httpx.ConnectTimeout("connect timeout")
    result = make_backend(fake_httpx).fetch("https://example.com")
    assert not result.ok
    assert result.error_category == ErrorCategory.NETWORK
    assert "unreachable" in result.error_message


def test_circuit_breaker_opens_after_consecutive_failures(fake_httpx):
    backend = make_backend(fake_httpx)
    assert backend.is_available is True

    for _ in range(3):
        FakeClient.raise_exception = fake_httpx.ConnectError("connection refused")
        result = backend.fetch("https://example.com")
        assert result.error_category == ErrorCategory.NETWORK

    assert backend.is_available is False
    assert backend._circuit_open is True


def test_circuit_breaker_closes_on_success(fake_httpx):
    backend = make_backend(fake_httpx)

    # Open circuit with 3 failures
    for _ in range(3):
        FakeClient.raise_exception = fake_httpx.ConnectError("connection refused")
        backend.fetch("https://example.com")
    assert backend.is_available is False

    # One success resets circuit
    FakeClient.raise_exception = None
    FakeClient.response = FakeResponse(success_payload())
    result = backend.fetch("https://example.com")
    assert result.ok
    assert backend.is_available is True
    assert backend._circuit_open is False


def test_circuit_breaker_half_open_after_reset(fake_httpx, monkeypatch):
    backend = make_backend(fake_httpx)

    # Open circuit
    for _ in range(3):
        FakeClient.raise_exception = fake_httpx.ConnectError("connection refused")
        backend.fetch("https://example.com")
    assert backend.is_available is False

    # Monkeypatch time.monotonic to simulate reset period elapsed
    import time as _time

    original_mono = _time.monotonic
    _time.monotonic = lambda: (backend._last_connect_failure_time or 0) + 60
    try:
        assert backend.is_available is True  # half-open for one probe
    finally:
        _time.monotonic = original_mono


def test_read_timeout_does_not_open_circuit(fake_httpx):
    backend = make_backend(fake_httpx)

    FakeClient.raise_exception = fake_httpx.TimeoutException("read timeout")
    result = backend.fetch("https://example.com")
    assert not result.ok
    assert result.error_message == "Remote browser request timed out."
    assert backend.is_available is True
    assert backend._consecutive_connect_failures == 0


def test_token_redacted_in_connect_error(fake_httpx):
    FakeClient.raise_exception = fake_httpx.ConnectError("connection refused: Bearer secret leaked in logs")
    result = make_backend(fake_httpx).fetch("https://example.com")
    assert not result.ok
    assert "secret" not in result.error_message
    assert "REDACTED" in result.error_message
