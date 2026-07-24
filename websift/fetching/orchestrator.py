"""Fetch stage orchestration."""

from __future__ import annotations

import logging
from collections.abc import Callable

from websift.fetching.backend import FetchBackend, FetchBackendOutcome
from websift.fetching.detector import DETECTOR_VERSION, is_challenge_or_js_shell
from websift.models import ErrorCategory, FetchResult

_log = logging.getLogger(__name__)

ORCHESTRATOR_VERSION = "orchestrator-v1"
NativeStage = Callable[[str], FetchResult | None]


class FetchOrchestrator:
    """Run optional native extraction, HTTP fetch, then configured browser fallback."""

    def __init__(
        self,
        *,
        http_backend: FetchBackend,
        backend: str = "auto",
        browser_backend: FetchBackend | None = None,
        native_stage: NativeStage | None = None,
    ):
        self.http_backend = http_backend
        self.backend = backend
        self.browser_backend = browser_backend
        self.native_stage = native_stage

    @property
    def fingerprint(self) -> str:
        browser = getattr(self.browser_backend, "fingerprint", "none")
        http = getattr(self.http_backend, "fingerprint", type(self.http_backend).__qualname__)
        native = "native" if self.native_stage is not None else "none"
        return f"{ORCHESTRATOR_VERSION}:{self.backend}:{http}:{browser}:{native}:{DETECTOR_VERSION}"

    def fetch(self, url: str) -> FetchResult:
        if self.backend == "browser":
            if self.browser_backend is None:
                return FetchResult.failure(
                    url,
                    "Fetch failed: FETCH_BACKEND=browser requires a configured browser backend.",
                    ErrorCategory.PROVIDER,
                )
            if not getattr(self.browser_backend, "is_available", True):
                return FetchResult.failure(
                    url,
                    "Fetch failed: Remote browser unreachable (circuit breaker open).",
                    ErrorCategory.NETWORK,
                )
            return self.browser_backend.fetch(url)

        if self.backend == "http":
            return self.http_backend.fetch(url)

        if self.native_stage is not None:
            native = self.native_stage(url)
            if native is not None:
                return native

        outcome = self._fetch_http_outcome(url)
        result = outcome.result
        if self.browser_backend is None:
            return result
        if result.error_category == ErrorCategory.BLOCKED:
            return result
        if result.ok and is_challenge_or_js_shell(result, raw_html=outcome.raw_html or None):
            # Only escalate if circuit breaker allows — skip browser when unreachable
            if getattr(self.browser_backend, "is_available", True):
                return self.browser_backend.fetch(url)
            _log.info(
                "Skipping browser escalation: circuit breaker open for %s",
                url,
            )
        return result

    def _fetch_http_outcome(self, url: str) -> FetchBackendOutcome:
        """Use richer built-in outcomes without changing the public backend contract."""
        fetch_outcome = getattr(self.http_backend, "fetch_outcome", None)
        if callable(fetch_outcome):
            outcome = fetch_outcome(url)
            if isinstance(outcome, FetchBackendOutcome):
                return outcome
        return FetchBackendOutcome(result=self.http_backend.fetch(url))
