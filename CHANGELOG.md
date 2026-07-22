# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-22

Hardening release (P0). Public Python/MCP tool names and string APIs stay compatible.

### Security

- SSRF: global-only IP policy; multi-answer DNS validation; reject URL userinfo; re-validate redirects with DNS pinning + SNI.
- Credential isolation: provider secrets never ride the arbitrary page-fetch path; GitHub README shortcut uses non-credential headers only.
- Error/log redaction for common secret patterns.
- Default MCP bind address is now **loopback** (`127.0.0.1`). Set `MCP_HOST=0.0.0.0` only when intentionally exposing (e.g. Docker).

### Changed

- Search goes through an allowlisted **provider** contract (default **DDGS**); no dynamic provider import from MCP callers.
- HTTP fetch: bounded body/decompress limits, charset order BOM → HTTP → meta → UTF-8, PDF via **pypdf only** (no pdfminer).
- HTML → Markdown: block-flow converter, main-content selection, boundary-aware truncation.
- Structured internals (`SearchResponse` / `FetchResult`) with public `search()` / `fetch()` still returning `str`.
- Typed runtime settings (`AppSettings.from_env()`); import of library/server modules does **not** read the environment.
- MCP server factory (`create_server`) with bounded concurrency for search/fetch and PDF parse.
- `SEARCH_TIMEOUT` remains a deprecated alias mapping to search and/or fetch timeouts.
- Packaging: single version source (`web_search.__version__`), CI matrix Python 3.10–3.13, offline pytest + coverage gate, publish only after quality jobs.

### Fixed

- Oversized downloads report overflow clearly instead of silent partial reads.
- Provider/network failures return sanitized messages (no raw secret-bearing exceptions to MCP).

### Compatibility notes

| Item | Behavior in 0.2.0 |
| ---- | ----------------- |
| `from web_search import WebSearchClient` | Unchanged |
| PyPI / CLI `websift` | Unchanged names |
| `WebSearchClient(max_results=..., timeout=..., max_page_chars=...)` | Supported; `timeout` still maps to both search and fetch |
| MCP tools `web_search` / `web_fetch` | Same names and `query` / `url` schemas |
| `MCP_HOST` default | **Breaking default**: `0.0.0.0` → `127.0.0.1` |
| `SEARCH_TIMEOUT` | Still read as alias for timeouts |

## [0.1.0] - 2026-07-20

Initial alpha: DDGS search, urllib fetch, basic SSRF, MCP FastMCP server.
