"""WorkLimits unit tests."""

from __future__ import annotations

import asyncio
import threading

import pytest

from websift.concurrency import WorkLimits
from websift.settings import ConcurrencySettings


def test_from_settings_defaults():
    w = WorkLimits.from_settings()
    assert w.search_max == 8
    assert w.fetch_max == 16
    assert w.pdf_max == 2


def test_from_settings_custom():
    w = WorkLimits.from_settings(ConcurrencySettings(search_max=1, fetch_max=2, pdf_max=3))
    assert w.search_max == 1
    assert w.fetch_max == 2
    assert w.pdf_max == 3


@pytest.mark.asyncio
async def test_run_search_serializes_when_max_one():
    w = WorkLimits.from_settings(ConcurrencySettings(search_max=1, fetch_max=1, pdf_max=1))
    order: list[str] = []
    lock = threading.Lock()
    release_first = threading.Event()

    def job(name: str) -> str:
        with lock:
            order.append(f"start:{name}")
        if name == "a":
            release_first.wait(timeout=2)
        with lock:
            order.append(f"end:{name}")
        return name

    t1 = asyncio.create_task(w.run_search(job, "a"))
    await asyncio.sleep(0.05)
    t2 = asyncio.create_task(w.run_search(job, "b"))
    await asyncio.sleep(0.05)
    with lock:
        # b must not start until a finishes
        assert order == ["start:a"]
    release_first.set()
    assert await t1 == "a"
    assert await t2 == "b"
    assert order == ["start:a", "end:a", "start:b", "end:b"]


def test_pdf_section_is_context_manager():
    w = WorkLimits.from_settings(ConcurrencySettings(pdf_max=1))
    with w.pdf_section():
        assert not w.pdf_semaphore.acquire(blocking=False)
    assert w.pdf_semaphore.acquire(blocking=False)
    w.pdf_semaphore.release()
