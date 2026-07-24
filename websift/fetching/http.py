"""Generic HTTP fetch backend."""

from __future__ import annotations

from typing import Any

from websift.fetching.backend import FetchBackendOutcome
from websift.models import FetchResult
from websift.providers.base import BaseProvider, FetchContext

HTTP_BACKEND_VERSION = "http-v1"


class HttpFetchBackend:
    """Reuse the established BaseProvider HTTP fetch pipeline."""

    fingerprint = HTTP_BACKEND_VERSION

    def __init__(self, fetch_context: FetchContext, *, pdf_semaphore: Any = None):
        self._provider = BaseProvider(fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)

    def fetch(self, url: str) -> FetchResult:
        return self.fetch_outcome(url).result

    def fetch_outcome(self, url: str) -> FetchBackendOutcome:
        outcome = self._provider.fetch_generic_outcome(url)
        return FetchBackendOutcome(result=outcome.result, raw_html=outcome.raw_html)
