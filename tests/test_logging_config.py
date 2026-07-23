"""Logging configuration from settings."""

from __future__ import annotations

import logging

from websift.logging_config import configure_logging, log_fetch, log_search
from websift.settings import LoggingSettings


def test_configure_logging_text_and_json():
    configure_logging(LoggingSettings(level="DEBUG", format="text"), force=True)
    assert logging.getLogger().level == logging.DEBUG
    configure_logging(LoggingSettings(level="INFO", format="json"), force=True)
    handler = logging.getLogger().handlers[0]
    assert "Json" in type(handler.formatter).__name__ or handler.formatter is not None


def test_log_search_query_gated(caplog):
    # Do not call configure_logging here: it replaces root handlers and drops caplog.
    with caplog.at_level(logging.INFO, logger="websift"):
        log_search(LoggingSettings(include_queries=False), "secret query", provider="ddgs")
    assert "secret query" not in caplog.text
    with caplog.at_level(logging.INFO, logger="websift"):
        log_search(LoggingSettings(include_queries=True), "secret query", provider="ddgs")
    assert "secret query" in caplog.text


def test_log_fetch_url_gated(caplog):
    with caplog.at_level(logging.INFO, logger="websift"):
        log_fetch(LoggingSettings(include_urls=False), "https://secret.example")
    assert "secret.example" not in caplog.text
    with caplog.at_level(logging.INFO, logger="websift"):
        log_fetch(LoggingSettings(include_urls=True), "https://secret.example")
    assert "secret.example" in caplog.text
