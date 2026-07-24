"""Fetch backend contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from websift.models import FetchResult


@dataclass(frozen=True)
class FetchBackendOutcome:
    """Internal backend result with bounded pre-extraction HTML evidence."""

    result: FetchResult
    raw_html: str = ""


class CallableFetchBackend:
    """Adapt an existing fetch callable to the backend contract."""

    def __init__(self, fetch: Callable[[str], FetchResult], *, fingerprint: str):
        self._fetch = fetch
        self.fingerprint = fingerprint

    def fetch(self, url: str) -> FetchResult:
        return self._fetch(url)


@runtime_checkable
class FetchBackend(Protocol):
    """Backend capable of fetching and extracting one URL."""

    fingerprint: str

    def fetch(self, url: str) -> FetchResult: ...
