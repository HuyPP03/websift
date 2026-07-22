"""MCP HTTP/SSE bearer auth and request body guards.

STDIO transport does not use bearer tokens (process-local trust). Remote
streamable-http/SSE transports may require ``Authorization: Bearer <token>``
when ``MCP_AUTH_MODE=bearer``.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any, Callable

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings as McpAuthSettings
from pydantic import AnyHttpUrl

from web_search.settings import AppSettings, AuthSettings

# Synthetic OAuth resource identity for static shared-secret bearer mode.
# MCP SDK requires issuer/resource URLs when auth middleware is enabled; they
# are metadata only for this verifier (no OAuth dance).
_CLIENT_ID = "static-bearer"


class StaticBearerTokenVerifier:
    """Verify a single shared secret with constant-time comparison.

    Comparison is length-independent: SHA-256 digests of provided vs expected
    tokens are compared via :func:`secrets.compare_digest`. The raw token is
    never logged by this class.
    """

    def __init__(self, token: str) -> None:
        expected = (token or "").encode("utf-8")
        if not expected:
            raise ValueError("Bearer token must be non-empty")
        self._expected_digest = hashlib.sha256(expected).digest()

    async def verify_token(self, token: str) -> AccessToken | None:
        provided = (token or "").encode("utf-8")
        provided_digest = hashlib.sha256(provided).digest()
        if not secrets.compare_digest(provided_digest, self._expected_digest):
            return None
        # Do not store the raw secret on the AccessToken beyond a placeholder.
        return AccessToken(token="ok", client_id=_CLIENT_ID, scopes=[])

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "StaticBearerTokenVerifier(token=***)"


class RequestBodyLimitMiddleware:
    """ASGI middleware rejecting bodies larger than ``max_bytes``.

    Uses ``Content-Length`` when present; otherwise counts streamed body chunks
    and aborts with 413 before the downstream app receives overflow bytes.
    Does not log request bodies or Authorization headers.
    """

    def __init__(self, app: Any, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be >= 1")
        self.app = app
        self.max_bytes = int(max_bytes)

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
        cl = headers.get(b"content-length")
        if cl is not None:
            try:
                length = int(cl.decode("latin-1"))
            except ValueError:
                await _send_json_error(send, 400, "invalid_content_length", "Invalid Content-Length")
                return
            if length > self.max_bytes:
                await _send_json_error(
                    send,
                    413,
                    "payload_too_large",
                    "Request body exceeds configured limit",
                )
                return
            await self.app(scope, receive, send)
            return

        received = 0
        rejected = False

        async def limited_receive() -> dict:
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body") or b""
                received += len(body)
                if received > self.max_bytes:
                    rejected = True
                    return {"type": "http.disconnect"}
            return message

        response_started = False

        async def limited_send(message: dict) -> None:
            nonlocal response_started
            if rejected and not response_started:
                response_started = True
                await _send_json_error(
                    send,
                    413,
                    "payload_too_large",
                    "Request body exceeds configured limit",
                )
                return
            if rejected:
                return
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, limited_receive, limited_send)
        if rejected and not response_started:
            await _send_json_error(
                send,
                413,
                "payload_too_large",
                "Request body exceeds configured limit",
            )


async def _send_json_error(send: Callable, status: int, error: str, description: str) -> None:
    body = json.dumps({"error": error, "error_description": description}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def resource_base_url(host: str, port: int) -> str:
    """Build a synthetic base URL for MCP resource metadata."""
    h = (host or "127.0.0.1").strip().strip("[]")
    if h in {"0.0.0.0", "::", ""}:
        h = "127.0.0.1"
    if ":" in h:
        h = f"[{h}]"
    return f"http://{h}:{int(port)}"


def mcp_auth_kwargs(settings: AppSettings) -> dict[str, Any]:
    """Return FastMCP ``auth`` / ``token_verifier`` kwargs when bearer is enabled.

    Empty dict when auth mode is ``none`` (default). STDIO ignores these; only
    HTTP/SSE apps mount auth middleware.
    """
    auth: AuthSettings = settings.auth
    mode = (auth.mode or settings.server.auth_mode or "none").strip().lower()
    if mode != "bearer":
        return {}
    token = (auth.bearer_token or "").strip()
    if not token:
        # validate() should have caught this; fail closed.
        raise ValueError("Bearer auth enabled but token is empty")

    base = resource_base_url(settings.server.host, settings.server.port)
    return {
        "auth": McpAuthSettings(
            issuer_url=AnyHttpUrl(base),
            resource_server_url=AnyHttpUrl(f"{base}/mcp"),
            required_scopes=None,
        ),
        "token_verifier": StaticBearerTokenVerifier(token),
    }


def install_http_guards(mcp: Any, settings: AppSettings) -> None:
    """Wrap FastMCP HTTP/SSE app builders with body-limit middleware when set."""
    max_body = settings.server.max_request_body_bytes
    if max_body is None:
        return

    max_bytes = int(max_body)
    orig_streamable = mcp.streamable_http_app
    orig_sse = mcp.sse_app

    def streamable_http_app() -> Any:
        app = orig_streamable()
        return RequestBodyLimitMiddleware(app, max_bytes)

    def sse_app(mount_path: str | None = None) -> Any:
        app = orig_sse(mount_path=mount_path)
        return RequestBodyLimitMiddleware(app, max_bytes)

    mcp.streamable_http_app = streamable_http_app  # type: ignore[method-assign]
    mcp.sse_app = sse_app  # type: ignore[method-assign]
