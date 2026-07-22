"""Logging helpers driven by LoggingSettings (no env on import)."""

from __future__ import annotations

import json
import logging
from typing import Any

from web_search.settings import LoggingSettings

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: LoggingSettings, *, force: bool = False) -> None:
    """Configure root logging once from settings (idempotent unless force=True)."""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    level_name = (settings.level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    if (settings.format or "text").lower() == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def log_search(settings: LoggingSettings, query: str, *, provider: str | None = None) -> None:
    if not settings.include_queries:
        logging.getLogger("web_search").info("search provider=%s", provider or "-")
        return
    # Truncate query to avoid huge logs even when enabled.
    q = (query or "")[:200]
    logging.getLogger("web_search").info("search provider=%s query=%r", provider or "-", q)


def log_fetch(settings: LoggingSettings, url: str) -> None:
    if not settings.include_urls:
        logging.getLogger("web_search").info("fetch")
        return
    u = (url or "")[:300]
    logging.getLogger("web_search").info("fetch url=%r", u)
