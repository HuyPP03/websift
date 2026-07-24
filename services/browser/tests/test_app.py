from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from browser_service.app import PROTOCOL_HEADER, create_app
from browser_service.config import Settings
from browser_service.runtime import RenderResult


@dataclass
class FakeRuntime:
    ready: bool = True
    seen_url: str | None = None

    async def start(self):
        self.ready = True

    async def close(self):
        self.ready = False

    async def render(self, url, options, policy):
        self.seen_url = url
        return RenderResult(
            html="<html><body>ok</body></html>",
            final_url=url,
            content_type="text/html; charset=utf-8",
            status_code=200,
            bytes_read=28,
            redirect_count=0,
            truncated=False,
            blocked_request_count=2,
        )


def payload(**changes):
    result = {
        "protocol_version": "1",
        "url": "https://example.com/",
        "render": {"timeout_seconds": 10, "post_load_wait_ms": 0, "max_html_bytes": 1000},
        "policy": {
            "allow_http": False,
            "allowed_ports": [443],
            "allowed_domains": [],
            "denied_domains": [],
        },
    }
    result.update(changes)
    return result


@pytest.fixture
async def client():
    runtime = FakeRuntime()
    app = create_app(Settings(token="test-token", max_request_bytes=2048), runtime)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as value:
            yield value, runtime


@pytest.mark.asyncio
async def test_auth_protocol_and_success_response(client):
    http, runtime = client
    missing_protocol = await http.post("/v1/render", json=payload(), headers={"Authorization": "Bearer test-token"})
    assert missing_protocol.json()["error"]["category"] == "provider"
    assert missing_protocol.headers[PROTOCOL_HEADER] == "1"

    unauthorized = await http.post("/v1/render", json=payload(), headers={PROTOCOL_HEADER: "1"})
    assert unauthorized.json()["error"]["category"] == "auth"

    response = await http.post(
        "/v1/render",
        json=payload(),
        headers={PROTOCOL_HEADER: "1", "Authorization": "Bearer test-token"},
    )
    body = response.json()
    assert response.status_code == 200
    assert response.headers[PROTOCOL_HEADER] == "1"
    assert body == {
        "protocol_version": "1",
        "ok": True,
        "result": {
            "html": "<html><body>ok</body></html>",
            "final_url": "https://example.com/",
            "content_type": "text/html; charset=utf-8",
            "status_code": 200,
            "bytes_read": 28,
            "redirect_count": 0,
            "truncated": False,
        },
    }
    assert runtime.seen_url == "https://example.com/"


@pytest.mark.asyncio
async def test_strict_schema_health_and_body_limit(client):
    http, _runtime = client
    bad = payload(extra="rejected")
    response = await http.post(
        "/v1/render",
        json=bad,
        headers={PROTOCOL_HEADER: "1", "Authorization": "Bearer test-token"},
    )
    assert response.json()["error"]["category"] == "provider"
    assert (await http.get("/healthz")).json() == {"status": "ready"}
    oversized = await http.post(
        "/v1/render",
        content=b"x" * 2049,
        headers={
            "content-type": "application/json",
            "content-length": "2049",
            PROTOCOL_HEADER: "1",
            "Authorization": "Bearer test-token",
        },
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["category"] == "overflow"
