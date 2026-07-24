from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .policy import BlockedTarget, EffectivePolicy
from .proxy import EgressProxy


class RenderFailure(Exception):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category
        self.message = message


@dataclass(frozen=True)
class RenderOptions:
    timeout_seconds: float
    post_load_wait_ms: int
    max_html_bytes: int


@dataclass(frozen=True)
class RenderResult:
    html: str
    final_url: str
    content_type: str
    status_code: int
    bytes_read: int
    redirect_count: int
    truncated: bool
    blocked_request_count: int


class BrowserRuntime:
    def __init__(self, settings: Settings, browser_factory: Any | None = None):
        self.settings = settings
        self.browser_factory = browser_factory
        self.proxy = EgressProxy(settings)
        self.browser: Any = None
        self._manager: Any = None
        self.ready = False
        self.semaphore = asyncio.Semaphore(settings.concurrency)

    async def start(self) -> None:
        await self.proxy.start()
        try:
            if self.browser_factory is not None:
                produced = self.browser_factory()
                self.browser = await produced if hasattr(produced, "__await__") else produced
            else:
                from camoufox.async_api import AsyncCamoufox

                self._manager = AsyncCamoufox(headless=True)
                self.browser = await self._manager.__aenter__()
            context = await self.browser.new_context(proxy={"server": self.proxy.url}, viewport=None)
            page = await context.new_page()
            await page.close()
            await context.close()
            self.ready = True
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        self.ready = False
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
            self._manager = None
        elif self.browser is not None:
            await self.browser.close()
        self.browser = None
        await self.proxy.close()

    async def render(self, url: str, options: RenderOptions, policy: EffectivePolicy) -> RenderResult:
        if not self.ready or self.browser is None:
            raise RenderFailure("unavailable", "Browser is not ready.")
        try:
            return await asyncio.wait_for(self._render_with_slot(url, options, policy), options.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise RenderFailure("timeout", "Browser render timed out.") from exc
        except RenderFailure:
            raise
        except Exception as exc:
            name = type(exc).__name__.lower()
            if "timeout" in name:
                raise RenderFailure("timeout", "Browser render timed out.") from exc
            raise RenderFailure("network", "Browser navigation failed.") from exc

    async def _render_with_slot(
        self, url: str, options: RenderOptions, policy: EffectivePolicy
    ) -> RenderResult:
        async with self.semaphore:
            return await self._render(url, options, policy)

    async def _render(self, url: str, options: RenderOptions, policy: EffectivePolicy) -> RenderResult:
        try:
            policy.validate_url(url, allow_local_scheme=False)
        except BlockedTarget as exc:
            raise RenderFailure("blocked", str(exc)) from exc

        context = await self.browser.new_context(proxy={"server": self.proxy.url})
        page = await context.new_page()
        blocked_count = 0
        top_level_block: str | None = None
        redirect_count = 0

        async def route_handler(route: Any, request: Any) -> None:
            nonlocal blocked_count, top_level_block
            try:
                policy.validate_url(request.url)
            except BlockedTarget as exc:
                blocked_count += 1
                is_top_level = request.is_navigation_request() and request.frame == page.main_frame
                if is_top_level:
                    top_level_block = str(exc)
                await route.abort("blockedbyclient")
                return
            await route.continue_()

        def response_handler(response: Any) -> None:
            nonlocal redirect_count
            if 300 <= response.status < 400 and response.headers.get("location"):
                redirect_count += 1

        await page.route("**/*", route_handler)
        page.on("response", response_handler)
        try:
            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=max(1, int(options.timeout_seconds * 1000)),
                )
            except Exception as exc:
                if top_level_block:
                    raise RenderFailure("blocked", top_level_block) from exc
                raise
            if top_level_block:
                raise RenderFailure("blocked", top_level_block)
            if response is None:
                raise RenderFailure("network", "Navigation returned no document response.")
            try:
                idle_budget = min(3000, max(250, options.post_load_wait_ms))
                await page.wait_for_load_state("networkidle", timeout=idle_budget)
            except Exception:
                pass
            if options.post_load_wait_ms:
                await page.wait_for_timeout(options.post_load_wait_ms)
            html = await page.content()
            encoded = html.encode("utf-8")
            if not encoded:
                raise RenderFailure("empty_content", "Browser returned empty HTML.")
            truncated = len(encoded) > options.max_html_bytes
            if truncated:
                encoded = encoded[: options.max_html_bytes]
                html = encoded.decode("utf-8", errors="ignore")
                encoded = html.encode("utf-8")
            content_type = response.headers.get("content-type", "text/html; charset=utf-8")
            is_html = content_type.lower().startswith(("text/html", "application/xhtml+xml"))
            if not is_html:
                raise RenderFailure("unsupported_content", "Target did not return HTML content.")
            return RenderResult(
                html=html,
                final_url=page.url,
                content_type=content_type,
                status_code=response.status,
                bytes_read=len(encoded),
                redirect_count=redirect_count,
                truncated=truncated,
                blocked_request_count=blocked_count,
            )
        finally:
            await page.close()
            await context.close()
