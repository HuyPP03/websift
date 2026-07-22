# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-07-22

Provider-owned fetch. Public Python/MCP tool names and string APIs stay compatible.

### Changed

- Fetch is owned by providers via `BaseProvider.fetch` (generic SSRF-safe default). Tavily/Exa override with exact-URL extract/contents when keyed; URL-level failures fall back to generic. Optional `PROVIDER_NATIVE_FETCH=false` forces generic fetch.
- `WebSearchClient.fetch_structured` delegates to the primary provider only; search fallback chains do not run extract.

### Compatibility notes

| Item                                       | Behavior in 0.3.1                                              |
| ------------------------------------------ | -------------------------------------------------------------- |
| `from web_search import WebSearchClient` | Unchanged                                                      |
| PyPI / CLI`websift`                      | Unchanged names                                                |
| MCP tools`web_search` / `web_fetch`    | Same names and`query` / `url` schemas                      |
| Default fetch path                         | Still SSRF-safe generic when provider has no native extract    |
| `PROVIDER_NATIVE_FETCH`                  | Default`true`; set `false` to force generic for Tavily/Exa |

## [0.3.0] - 2026-07-22

Providers, optional MCP auth, and hardened packaging/Docker. Public Python/MCP tool names and string APIs stay compatible.

### Added

- Search providers beyond default DDGS: **SearXNG**, **Brave**, **Tavily**, **Exa** (allowlisted server-wide via `SEARCH_PROVIDER` / optional fallbacks; adapters use stdlib HTTP).
- Optional install extras: `searxng`, `brave`, `tavily`, `exa`, `providers` (markers; modules ship in the base package).
- Optional MCP **bearer auth** for HTTP/SSE (`MCP_AUTH_MODE=bearer` + `MCP_BEARER_TOKEN`); STDIO unchanged.
- Request body size limit for HTTP MCP (`MCP_MAX_REQUEST_BODY_BYTES`).
- Hardened Docker image: multi-stage wheel install, non-root `websift` (uid 10001), `websift` entrypoint, TCP healthcheck, `.dockerignore`.
- Compose no longer requires a local `.env`; secrets inject at runtime only.
- CI: optional-extra smoke installs; Docker build + non-root smoke job.
- Runtime flag matrix wired for fetch/HTML/logging settings (cache storage reserved for a later release).
- README / VI docs: full search-provider matrix (env keys, fallback, extras) and auth/Docker guidance.

### Security

- Optional shared-secret bearer for remote MCP HTTP/SSE; tokens compared in constant time and never logged or echoed in 401 bodies.
- Credential isolation retained: provider secrets never ride the arbitrary page-fetch path.

### Compatibility notes

| Item                                       | Behavior in 0.3.0                                                    |
| ------------------------------------------ | -------------------------------------------------------------------- |
| `from web_search import WebSearchClient` | Unchanged                                                            |
| PyPI / CLI`websift`                      | Unchanged names                                                      |
| MCP tools`web_search` / `web_fetch`    | Same names and`query` / `url` schemas                            |
| `MCP_HOST` default                       | Loopback (`127.0.0.1`); Docker image sets bind for published ports |
| `MCP_AUTH_MODE`                          | Default`none`; opt-in `bearer` for HTTP/SSE only                 |
| Provider selection                         | Server-wide env only (not per tool call)                             |

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

| Item                                                                  | Behavior in 0.2.0                                         |
| --------------------------------------------------------------------- | --------------------------------------------------------- |
| `from web_search import WebSearchClient`                            | Unchanged                                                 |
| PyPI / CLI`websift`                                                 | Unchanged names                                           |
| `WebSearchClient(max_results=..., timeout=..., max_page_chars=...)` | Supported;`timeout` still maps to both search and fetch |
| MCP tools`web_search` / `web_fetch`                               | Same names and`query` / `url` schemas                 |
| `MCP_HOST` default                                                  | **Breaking default**: `0.0.0.0` → `127.0.0.1`  |
| `SEARCH_TIMEOUT`                                                    | Still read as alias for timeouts                          |

## [0.1.0] - 2026-07-20

Initial alpha: DDGS search, urllib fetch, basic SSRF, MCP FastMCP server.
