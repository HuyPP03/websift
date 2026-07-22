"""ProviderHttpClient GET/JSON (mocked urllib)."""

from __future__ import annotations

import io
import json
from email.message import Message

import pytest

from web_search.provider_http import ProviderHttpClient, ProviderHttpConfig
from web_search.providers.errors import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)


class _FakeHTTPResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        super().__init__(body)
        self.status = status
        self._headers = Message()
        for k, v in (headers or {}).items():
            self._headers[k] = v

    def getcode(self):
        return self.status

    @property
    def headers(self):
        return self._headers


def test_build_url_relative_and_params():
    c = ProviderHttpClient(ProviderHttpConfig(base_url="https://api.example.com/v1"))
    assert c.build_url("/search", {"q": "x y", "n": 2}) == "https://api.example.com/v1/search?q=x+y&n=2"


def test_build_url_rejects_absolute_path():
    c = ProviderHttpClient(ProviderHttpConfig(base_url="https://api.example.com"))
    with pytest.raises(ProviderConfigError) as ei:
        c.build_url("https://evil.example/path")
    assert ei.value.code == "absolute_path_forbidden"


def test_get_json_success(monkeypatch: pytest.MonkeyPatch):
    body = json.dumps({"ok": True}).encode()

    def fake_urlopen(req, timeout=None):
        assert "https://api.example.com/ping" in req.full_url
        assert req.get_header("X-subscription-token") == "sec" or req.headers.get("X-Subscription-Token") == "sec"
        return _FakeHTTPResponse(body, 200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c = ProviderHttpClient(
        ProviderHttpConfig(
            base_url="https://api.example.com",
            headers={"X-Subscription-Token": "sec"},
            retry_max=0,
        )
    )
    data = c.get_json("/ping", provider="brave")
    assert data == {"ok": True}


def test_get_json_401(monkeypatch: pytest.MonkeyPatch):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", hdrs=Message(), fp=io.BytesIO(b"nope"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c = ProviderHttpClient(ProviderHttpConfig(base_url="https://api.example.com", retry_max=0))
    with pytest.raises(ProviderAuthError):
        c.get_json("/x", provider="brave")


def test_get_json_429(monkeypatch: pytest.MonkeyPatch):
    import urllib.error

    hdrs = Message()
    hdrs["Retry-After"] = "3"

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", hdrs=hdrs, fp=io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c = ProviderHttpClient(ProviderHttpConfig(base_url="https://api.example.com", retry_max=0))
    with pytest.raises(ProviderRateLimitError) as ei:
        c.get_json("/x", provider="searxng")
    assert ei.value.retry_after == 3.0


def test_get_json_500(monkeypatch: pytest.MonkeyPatch):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", hdrs=Message(), fp=io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c = ProviderHttpClient(ProviderHttpConfig(base_url="https://api.example.com", retry_max=0))
    with pytest.raises(ProviderUnavailableError):
        c.get_json("/x", provider="searxng")


def test_get_json_invalid_json(monkeypatch: pytest.MonkeyPatch):
    def fake_urlopen(req, timeout=None):
        return _FakeHTTPResponse(b"not-json", 200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c = ProviderHttpClient(ProviderHttpConfig(base_url="https://api.example.com", retry_max=0))
    with pytest.raises(ProviderResponseError):
        c.get_json("/x", provider="searxng")


def test_retry_on_503_then_success(monkeypatch: pytest.MonkeyPatch):
    import urllib.error

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", hdrs=Message(), fp=io.BytesIO(b""))
        return _FakeHTTPResponse(json.dumps({"results": []}).encode(), 200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("web_search.provider_http.time.sleep", lambda s: None)
    c = ProviderHttpClient(
        ProviderHttpConfig(base_url="https://api.example.com", retry_max=2, retry_backoff_seconds=0.01)
    )
    data = c.get_json("/search", provider="searxng")
    assert data == {"results": []}
    assert calls["n"] == 2
