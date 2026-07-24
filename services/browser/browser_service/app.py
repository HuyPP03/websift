from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings
from .policy import BlockedTarget, merge_policy
from .runtime import BrowserRuntime, RenderFailure, RenderOptions

PROTOCOL = "1"
PROTOCOL_HEADER = "X-Websift-Browser-Protocol"
ERROR_CATEGORIES = {
    "blocked",
    "timeout",
    "auth",
    "rate_limit",
    "unavailable",
    "overflow",
    "unsupported_content",
    "empty_content",
    "http_error",
    "network",
    "decode",
    "redirect",
    "provider",
    "unknown",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RenderConfig(StrictModel):
    timeout_seconds: float = Field(gt=0)
    post_load_wait_ms: int = Field(ge=0)
    max_html_bytes: int = Field(gt=0)


class RequestPolicy(StrictModel):
    allow_http: bool
    allowed_ports: set[int]
    allowed_domains: set[str]
    denied_domains: set[str]


class RenderRequest(StrictModel):
    protocol_version: Literal["1"]
    url: HttpUrl
    render: RenderConfig
    policy: RequestPolicy


class AuthProtocolMiddleware:
    def __init__(self, app: ASGIApp, token: str | None):
        self.app = app
        self.token = token
        self.expected = f"Bearer {token}".encode() if token else b""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/v1/render":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        if headers.get(PROTOCOL_HEADER.lower().encode()) != PROTOCOL.encode():
            await protocol_response(error_body("provider", "Browser protocol header mismatch."))(scope, receive, send)
            return
        if self.token and not hmac.compare_digest(headers.get(b"authorization", b""), self.expected):
            await protocol_response(error_body("auth", "Authentication failed."))(scope, receive, send)
            return
        await self.app(scope, receive, send)


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content_length = dict(scope.get("headers", [])).get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send)
                return
        messages: list[Message] = []
        consumed = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            consumed += len(message.get("body", b""))
            if consumed > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive() -> Message:
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content=error_body("overflow", "Request body exceeds configured limit."),
            headers={PROTOCOL_HEADER: PROTOCOL},
        )
        await response(scope, receive, send)


def error_body(category: str, message: str) -> dict[str, Any]:
    safe_category = category if category in ERROR_CATEGORIES else "unknown"
    return {"protocol_version": PROTOCOL, "ok": False, "error": {"category": safe_category, "message": message[:500]}}


def protocol_response(content: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=content, status_code=status_code, headers={PROTOCOL_HEADER: PROTOCOL})


def create_app(settings: Settings | None = None, runtime: BrowserRuntime | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    browser_runtime = runtime or BrowserRuntime(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = browser_runtime
        await browser_runtime.start()
        try:
            yield
        finally:
            await browser_runtime.close()

    app = FastAPI(title="WebSift Browser Service", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(BodyLimitMiddleware, max_bytes=config.max_request_bytes)
    app.add_middleware(AuthProtocolMiddleware, token=config.token)
    app.state.runtime = browser_runtime

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return protocol_response(error_body("provider", "Request schema is invalid."))

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        ready = bool(browser_runtime.ready)
        return JSONResponse({"status": "ready" if ready else "starting"}, status_code=200 if ready else 503)

    @app.get("/livez")
    async def livez() -> dict[str, str]:
        return {"status": "alive"}

    @app.post("/v1/render")
    async def render(payload: RenderRequest) -> JSONResponse:
        if not browser_runtime.ready:
            return protocol_response(error_body("unavailable", "Browser is not ready."))
        requested_timeout = min(payload.render.timeout_seconds, config.max_timeout_seconds)
        requested_html = min(payload.render.max_html_bytes, config.max_html_bytes)
        try:
            policy = merge_policy(
                config,
                allow_http=payload.policy.allow_http,
                allowed_ports=payload.policy.allowed_ports,
                allowed_domains=payload.policy.allowed_domains,
                denied_domains=payload.policy.denied_domains,
            )
            result = await browser_runtime.render(
                str(payload.url),
                RenderOptions(
                    timeout_seconds=requested_timeout,
                    post_load_wait_ms=payload.render.post_load_wait_ms,
                    max_html_bytes=requested_html,
                ),
                policy,
            )
        except BlockedTarget as exc:
            return protocol_response(error_body("blocked", str(exc)))
        except RenderFailure as exc:
            return protocol_response(error_body(exc.category, exc.message))
        return protocol_response(
            {
                "protocol_version": PROTOCOL,
                "ok": True,
                "result": {
                    "html": result.html,
                    "final_url": result.final_url,
                    "content_type": result.content_type,
                    "status_code": result.status_code,
                    "bytes_read": result.bytes_read,
                    "redirect_count": result.redirect_count,
                    "truncated": result.truncated,
                },
            }
        )

    return app
