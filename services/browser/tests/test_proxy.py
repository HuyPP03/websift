from __future__ import annotations

import asyncio
import socket

import pytest

from browser_service.policy import BlockedTarget
from browser_service.proxy import filter_headers, parse_connect_target, resolve_global, rewrite_http_request


def test_parse_connect_target():
    assert parse_connect_target("example.com:443") == ("example.com", 443)
    assert parse_connect_target("[2001:4860:4860::8888]:443") == ("2001:4860:4860::8888", 443)
    for target in ("example.com", "user@example.com:443", "example.com:0", "a:b:443"):
        with pytest.raises(BlockedTarget):
            parse_connect_target(target)


def test_rewrite_http_request_and_filter_headers():
    request, host, port = rewrite_http_request(
        "GET",
        "http://example.com:8080/a?q=1",
        "HTTP/1.1",
        [("Host", "example.com:8080"), ("Proxy-Authorization", "secret"), ("Connection", "X-Drop"), ("X-Drop", "yes")],
    )
    assert (host, port) == ("example.com", 8080)
    assert request.startswith(b"GET /a?q=1 HTTP/1.1\r\n")
    assert b"secret" not in request and b"X-Drop" not in request
    assert filter_headers([("Upgrade", "websocket"), ("X-Test", "ok")]) == [("X-Test", "ok")]


@pytest.mark.asyncio
async def test_resolve_rejects_private_and_mixed_answers(monkeypatch):
    loop = asyncio.get_running_loop()

    async def mixed(*_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]

    monkeypatch.setattr(loop, "getaddrinfo", mixed)
    with pytest.raises(BlockedTarget):
        await resolve_global("example.com", 443)


@pytest.mark.asyncio
async def test_resolve_accepts_all_global_answers(monkeypatch):
    loop = asyncio.get_running_loop()

    async def public(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(loop, "getaddrinfo", public)
    assert await resolve_global("example.com", 443) == ["93.184.216.34"]
