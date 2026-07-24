from __future__ import annotations

import os

import httpx
import pytest

from browser_service.app import PROTOCOL_HEADER, create_app
from browser_service.config import Settings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_camoufox_smoke():
    if os.getenv("RUN_CAMOUFOX_INTEGRATION") != "1":
        pytest.skip("set RUN_CAMOUFOX_INTEGRATION=1 to run")
    settings = Settings(allow_http=True, allowed_ports=frozenset({80, 443}), max_timeout_seconds=30)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/render",
                headers={PROTOCOL_HEADER: "1"},
                json={
                    "protocol_version": "1",
                    "url": "https://example.com/",
                    "render": {"timeout_seconds": 20, "post_load_wait_ms": 0, "max_html_bytes": 100_000},
                    "policy": {
                        "allow_http": False,
                        "allowed_ports": [443],
                        "allowed_domains": ["example.com"],
                        "denied_domains": [],
                    },
                },
            )
    assert response.json()["ok"] is True
    assert "Example Domain" in response.json()["result"]["html"]
