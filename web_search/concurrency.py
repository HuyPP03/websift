"""Bounded concurrency for search, fetch, and PDF work."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Callable, TypeVar

from web_search.settings import ConcurrencySettings

T = TypeVar("T")


@dataclass
class WorkLimits:
    """Separate limits: async semaphores for MCP tools; thread semaphore for PDF parse."""

    search_max: int
    fetch_max: int
    pdf_max: int
    _search: asyncio.Semaphore
    _fetch: asyncio.Semaphore
    _pdf: threading.BoundedSemaphore

    @classmethod
    def from_settings(cls, settings: ConcurrencySettings | None = None) -> WorkLimits:
        c = settings or ConcurrencySettings()
        search_max = max(1, int(c.search_max))
        fetch_max = max(1, int(c.fetch_max))
        pdf_max = max(1, int(c.pdf_max))
        return cls(
            search_max=search_max,
            fetch_max=fetch_max,
            pdf_max=pdf_max,
            _search=asyncio.Semaphore(search_max),
            _fetch=asyncio.Semaphore(fetch_max),
            _pdf=threading.BoundedSemaphore(pdf_max),
        )

    @property
    def search_semaphore(self) -> asyncio.Semaphore:
        return self._search

    @property
    def fetch_semaphore(self) -> asyncio.Semaphore:
        return self._fetch

    @property
    def pdf_semaphore(self) -> threading.BoundedSemaphore:
        return self._pdf

    async def run_search(self, fn: Callable[..., T], /, *args, **kwargs) -> T:
        async with self._search:
            return await asyncio.to_thread(fn, *args, **kwargs)

    async def run_fetch(self, fn: Callable[..., T], /, *args, **kwargs) -> T:
        async with self._fetch:
            return await asyncio.to_thread(fn, *args, **kwargs)

    def pdf_section(self):
        """Context manager around CPU-bound PDF extraction (thread-safe)."""
        return self._pdf
