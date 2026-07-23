"""Bearer auth and request body limit guards (phase 7 P1)."""

from __future__ import annotations

import pytest
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Mount
from starlette.testclient import TestClient

from websift.auth import (
    RequestBodyLimitMiddleware,
    StaticBearerTokenVerifier,
    mcp_auth_kwargs,
    resource_base_url,
)
from websift.server import create_server
from websift.settings import AppSettings, AuthSettings, ServerSettings


@pytest.mark.asyncio
async def test_static_verifier_accepts_matching_token():
    v = StaticBearerTokenVerifier("s3cret-token")
    ok = await v.verify_token("s3cret-token")
    assert ok is not None
    assert ok.client_id == "static-bearer"
    # Raw secret must not be stored on AccessToken
    assert ok.token != "s3cret-token"


@pytest.mark.asyncio
async def test_static_verifier_rejects_wrong_and_empty():
    v = StaticBearerTokenVerifier("s3cret-token")
    assert await v.verify_token("wrong") is None
    assert await v.verify_token("") is None
    assert await v.verify_token("s3cret-tokenx") is None
    assert await v.verify_token("s3cret-toke") is None


def test_static_verifier_rejects_empty_config():
    with pytest.raises(ValueError):
        StaticBearerTokenVerifier("")


def test_static_verifier_repr_redacts_token():
    assert "s3cret" not in repr(StaticBearerTokenVerifier("s3cret-token"))


def test_resource_base_url_maps_wildcard_hosts():
    assert resource_base_url("0.0.0.0", 8787) == "http://127.0.0.1:8787"
    assert resource_base_url("::", 9) == "http://127.0.0.1:9"
    assert resource_base_url("127.0.0.1", 1) == "http://127.0.0.1:1"
    assert resource_base_url("::1", 80) == "http://[::1]:80"


def test_mcp_auth_kwargs_none_mode():
    assert mcp_auth_kwargs(AppSettings()) == {}


def test_mcp_auth_kwargs_bearer():
    settings = AppSettings(
        server=ServerSettings(host="127.0.0.1", port=8787, auth_mode="bearer"),
        auth=AuthSettings(mode="bearer", bearer_token="tok-abc"),
    )
    kwargs = mcp_auth_kwargs(settings)
    assert "auth" in kwargs and "token_verifier" in kwargs
    assert isinstance(kwargs["token_verifier"], StaticBearerTokenVerifier)
    assert "8787" in str(kwargs["auth"].issuer_url)


def test_create_server_wires_bearer_verifier():
    settings = AppSettings(
        server=ServerSettings(auth_mode="bearer"),
        auth=AuthSettings(mode="bearer", bearer_token="server-secret"),
    )
    app = create_server(settings, warn_public_bind=False)
    assert app.mcp._token_verifier is not None
    assert app.mcp.settings.auth is not None
    assert "server-secret" not in repr(app.mcp._token_verifier)


def test_create_server_no_auth_by_default():
    app = create_server(warn_public_bind=False)
    assert app.mcp._token_verifier is None
    assert app.mcp.settings.auth is None


def _ok_asgi():
    async def _app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    return _app


def _auth_app(token: str) -> Starlette:
    verifier = StaticBearerTokenVerifier(token)
    protected = RequireAuthMiddleware(_ok_asgi(), [], None)
    return Starlette(
        routes=[Mount("/mcp", app=protected)],
        middleware=[
            Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(verifier)),
        ],
    )


def test_http_rejects_missing_bearer():
    client = TestClient(_auth_app("good-token"))
    r = client.get("/mcp")
    assert r.status_code == 401
    body = r.text
    assert "good-token" not in body
    assert "Authentication required" in body or "invalid_token" in body


def test_http_rejects_wrong_bearer():
    client = TestClient(_auth_app("good-token"))
    r = client.get("/mcp", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401
    assert "good-token" not in r.text
    assert "wrong-token" not in r.text


def test_http_accepts_valid_bearer():
    client = TestClient(_auth_app("good-token"))
    r = client.get("/mcp", headers={"Authorization": "Bearer good-token"})
    assert r.status_code == 200
    assert r.text == "ok"


def test_body_limit_content_length():
    async def ok_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = RequestBodyLimitMiddleware(ok_app, max_bytes=8)
    starlette = Starlette(routes=[Mount("/", app=app)])
    client = TestClient(starlette)
    r = client.post("/", content=b"1234567890", headers={"content-length": "10"})
    assert r.status_code == 413
    assert "payload_too_large" in r.text
    r2 = client.post("/", content=b"1234")
    assert r2.status_code == 200


def test_body_limit_invalid_content_length():
    async def ok_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = RequestBodyLimitMiddleware(ok_app, max_bytes=100)
    starlette = Starlette(routes=[Mount("/", app=app)])
    client = TestClient(starlette)
    r = client.post("/", content=b"x", headers={"content-length": "nope"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_body_limit_streaming_oversize():
    async def ok_app(scope, receive, send):
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                break
            if msg["type"] == "http.request" and not msg.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = RequestBodyLimitMiddleware(ok_app, max_bytes=5)
    status: dict = {}

    async def receive():
        return {"type": "http.request", "body": b"0123456789", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
        if message["type"] == "http.response.body":
            status["body"] = message.get("body", b"")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("127.0.0.1", 80),
        "scheme": "http",
    }
    await app(scope, receive, send)
    assert status["code"] == 413
    assert b"payload_too_large" in status["body"]


def test_install_http_guards_wraps_apps():
    settings = AppSettings(
        server=ServerSettings(max_request_body_bytes=1024),
        auth=AuthSettings(mode="none"),
    )
    app = create_server(settings, warn_public_bind=False)
    wrapped = app.mcp.streamable_http_app()
    assert isinstance(wrapped, RequestBodyLimitMiddleware)
    assert wrapped.max_bytes == 1024


def test_body_limit_ctor_rejects_zero():
    async def ok_app(scope, receive, send):
        pass

    with pytest.raises(ValueError):
        RequestBodyLimitMiddleware(ok_app, 0)
