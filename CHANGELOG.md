# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-07-24

### Added

- **Fetch orchestration** — `FetchOrchestrator` routes fetches through native provider → HTTP → browser with a versioned challenge/JS-shell detector. Orchestrator replaces the monolithic fetch path and enables incremental fallback.
- **Browser rendering** — Optional `[browser]` extra installs a lightweight remote HTTP client (httpx). The browser runtime (Camoufox + Playwright) runs as a separate Docker service (`services/browser/`).
- **`websift[browser]` and `websift[mcp-browser]` extras** — Base wheel remains lightweight (ddgs, bs4, pypdf). Browser client, MCP and provider adapters are optional.
- **`FetchSettings.backend`** — `auto` (default), `http`, and `browser` modes. `auto` conditionally escalates HTTP to browser only on challenge/JS-shell evidence. `http` and `browser` modes skip stages.
- **`BrowserSettings`** — Frozen configuration for `BROWSER_ENDPOINT`, `BROWSER_TOKEN`, `BROWSER_ALLOW_INSECURE_ENDPOINT`, `BROWSER_TIMEOUT_SECONDS`, `BROWSER_POST_LOAD_WAIT_MS`, `BROWSER_MAX_HTML_BYTES`, `BROWSER_MAX_CONCURRENCY`.
- **Raw HTML detection** — `GenericFetchOutcome` / `FetchBackendOutcome` carry bounded raw HTML alongside the extracted `FetchResult`, so the detector inspects original HTML (not post-extraction Markdown).
- **URL/DNS preflight before cache** — `FetchURLPreflight` validates URL and all DNS answers before any cache or backend call, preventing cached results from bypassing security policy changes.
- **Versioned fetch cache key** (`fetch-v2`) — Cache fingerprint includes timeout, max bytes, ports, domains, backend mode, implementation fingerprint, and detector version. HTTP and browser results use separate namespaces.
- **`FetchOrchestrator.fingerprint`** — Combined orchestrator/backend/browser/detector fingerprint for cache key and doctor output.
- **`--backend` flag for `websift fetch` CLI** — Operator-configurable backend mode (`auto|http|browser`).
- **Standalone browser service** — `services/browser/` with FastAPI app, Camoufox runtime, egress proxy, route interception, policy enforcement, and hardened Dockerfile (non-root, no-new-privileges).
- **Context manager** — `WebSearchClient` supports `with` statement and explicit `close()` for proper HTTP connection pool cleanup.
- **Doctor output** — Reports browser client extra, endpoint readiness, and token presence (redacted).

### Changed

- **`BaseProvider.fetch()` refactored** — Split into `fetch_generic_outcome()` (raw HTML + result) and `fetch()` (compatibility shim). Provider native extract is now a discrete stage, not a fallback.
- **`websift/providers/tavily.py` and `websift/providers/exa.py`** — `fetch_native()` extracted as a stage; `fetch()` compatibility shim calls orchestrator pattern.
- **`websift/cache.py`** — Fetch cache key versioned to `fetch-v2` with comprehensive policy fingerprint.
- **`websift/client.py`** — Integrated fetch orchestration: preflight → cache → orchestrator. Added `_init_fetch_orchestrator()`, `fetch_backend` constructor kwarg.
- **`websift/security.py`** — Added `FetchURLPreflight` dataclass and `preflight_fetch_url()` for pre-fetch DNS-aware validation.
- **`websift/settings.py`** — Added `FetchSettings.backend`, `BrowserSettings`, browser validation, and `BROWSER_*` environment variable parsing.
- **`pyproject.toml`** — Added `browser = ["httpx>=0.27,<1"]` and `mcp-browser` extras.
- **`docker-compose.yml`** — Added browser service with `browser` profile, internal network, port 8790.

### Security

- **SSRF-safe egress proxy** — Browser service traffic flows through an internal HTTP/CONNECT forward proxy that validates all DNS answers, pins to global IPs, and blocks private/link-local/metadata destinations.
- **Route interception** — Playwright route handler validates every document, redirect, iframe, script, XHR, fetch, stylesheet, image, font, media, and WebSocket against the fetch policy.
- **Isolated browser contexts** — Each render request gets a fresh browser context and page; no cookies or storage shared between requests.
- **Protocol authentication** — Bearer token required for browser service when exposed beyond loopback.
- **Container hardening** — Browser service runs non-root, drops capabilities, enforces no-new-privileges, resource/PID limits.

### Breaking Changes

| Change | Migration |
| ------ | --------- |
| Fetch cache key versioned to `fetch-v2` | Existing `fetch-v1` cache entries are invalidated on upgrade |
| `BaseProvider.fetch()` internal signature | Custom providers should implement `fetch()` returning `FetchResult`; orchestrator integration uses `fetch_outcome()` |

### Backward Compatibility

- `WebSearchClient.fetch()` / `fetch_structured()` and async wrappers retain the same public signatures and output.
- MCP `web_fetch` still accepts only `url`; backend/endpoint/token are operator configuration.
- Without a browser service configured, `auto` mode (default) behaves identically to v1.3.x.
- Base wheel smoke test confirms no httpx/Playwright/Camoufox dependency.

## [1.3.0] - 2026-07-23

### Added

- CLI `websift doctor` — install/settings/credentials (redacted) / MCP readiness checks; `--json` report.
- CLI `websift providers` — list allowlisted providers and capabilities; `--json` report.
- JSON **schema v2** for `--json` / `to_dict()`: `schema_version`, `filters`, `result_count` (search), stable error object.
- Multi-query search: `WebSearchClient.search_many` / `asearch_many` and CLI `websift search q1 q2 …` (concurrent; order preserved).
- Fetch domain policy: `FETCH_ALLOWED_DOMAINS` / `FETCH_DENIED_DOMAINS` (host suffix allow/deny, settings-only).
- Optional **disk** cache: `CACHE_BACKEND=disk` + `CACHE_DIR` (stdlib JSON files, TTL/LRU index).

### Changed

- Search CLI accepts one or more queries (`nargs=+`); multiple queries emit a batch envelope when `--json`.

## [1.2.0] - 2026-07-23

### Added

- **Serper** search provider (`SEARCH_PROVIDER=serper`, `SERPER_API_KEY`, optional `SERPER_BASE_URL`) — Google SERP via `google.serper.dev` using stdlib HTTP.
- Optional install extra `websift[mcp]` for the MCP server runtime (FastMCP). Library, CLI `search`/`fetch`, and providers no longer require `mcp` at install time.
- Empty marker extra `serper` (adapters ship in the base package).

### Changed

- Base package dependencies are library-only (`ddgs`, `beautifulsoup4`, `pypdf`). Install `pip install 'websift[mcp]'` (or `websift[dev]`) for MCP serve/auth tests.
- Docker image installs the wheel with the `mcp` extra so `websift serve` works out of the box.
- Importing `websift.server` / `websift.auth` no longer requires `mcp`; `create_server()` and bearer auth helpers import FastMCP lazily and raise a clear install hint if missing.
- CLI `websift serve` surfaces the missing-MCP install hint as a configuration-style exit instead of a traceback.

## [1.1.0] - 2026-07-23

### Added

- Async client helpers: `WebSearchClient.asearch` / `afetch` (and `asearch_structured` / `afetch_structured`) via `asyncio.to_thread`.
- CLI `--json` for `websift search` and `websift fetch` — structured JSON for scripting (`ok`, results/content, `error`). Exit code `1` when `ok` is false.
- `SearchResult` / `SearchResponse` / `FetchResult.to_dict()` for stable JSON payloads.

## [1.0.1] - 2026-07-23

### Added

- `websift/py.typed` marker so type checkers treat the package as typed.
- Opt-in **in-memory TTL/LRU cache** for successful `search` / `fetch` results (`CACHE_ENABLED`, TTLs, size caps). Off by default.
- DDGS provider uses `SEARCH_RETRY_MAX` / `SEARCH_RETRY_BACKOFF_SECONDS` (same knobs as HTTP providers).

### Improved

- Clearer public DDGS errors for timeout, rate-limit/block, and connectivity failures.
- Docs: migration note (`web_search` → `websift`), library-first install blurb, cache/retry env vars.

## [1.0.0] - 2026-07-23

First stable major release. Breaking changes from the 0.3.x line are intentional and documented below.

### Changed

- **Import path** renamed from `web_search` → `websift` (PyPI, CLI, Docker, and Python import share one name).
- Console entry is a real CLI (`websift.cli:main`) with `--help`, `--version`, and subcommands `serve` / `search` / `fetch`. Bare `websift` still starts the MCP server (equivalent to `websift serve`).
- `WebSearchClient` accepts richer constructor kwargs (`search_timeout`, `fetch_timeout`, `provider` name, `api_key`, `base_url`, `fallback_providers`, extraction flags, …) plus `settings=AppSettings(...)` / `AppSettings.from_env()`.
- Public exports: `from websift import WebSearchClient, AppSettings, __version__`.
- Default fetch/output limits: 4 MB page body, 128k chars (see `websift/config.py`).
- Logger name and FastMCP server name use `websift`.
- Docs (EN + VI) document CLI flags, library customization, and unified package layout.

### Compatibility notes

| Item | Behavior in 1.0.0 |
| ---- | ----------------- |
| `from web_search import …` | **Removed** — use `from websift import …` |
| PyPI / CLI `websift` | Unchanged package/CLI names |
| MCP tools `web_search` / `web_fetch` | Same names and `query` / `url` schemas |
| Bare `websift` (no args) | Starts MCP server (`serve`) |
| `websift --help` / `--version` | Supported |
| `websift search` / `websift fetch` | One-shot CLI (no MCP) |

## [0.3.1] - 2026-07-22

Provider-owned fetch. Public Python/MCP tool names and string APIs stay compatible.

### Changed

- Fetch is owned by providers via `BaseProvider.fetch` (generic SSRF-safe default). Tavily/Exa override with exact-URL extract/contents when keyed; URL-level failures fall back to generic. Optional `PROVIDER_NATIVE_FETCH=false` forces generic fetch.
- `WebSearchClient.fetch_structured` delegates to the primary provider only; search fallback chains do not run extract.

### Compatibility notes

| Item                                       | Behavior in 0.3.1                                              |
| ------------------------------------------ | -------------------------------------------------------------- |
| `from websift import WebSearchClient` | Unchanged                                                      |
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
| `from websift import WebSearchClient` | Unchanged                                                            |
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
- Packaging: single version source (`websift.__version__`), CI matrix Python 3.10–3.13, offline pytest + coverage gate, publish only after quality jobs.

### Fixed

- Oversized downloads report overflow clearly instead of silent partial reads.
- Provider/network failures return sanitized messages (no raw secret-bearing exceptions to MCP).

### Compatibility notes

| Item                                                                  | Behavior in 0.2.0                                         |
| --------------------------------------------------------------------- | --------------------------------------------------------- |
| `from websift import WebSearchClient`                            | Unchanged                                                 |
| PyPI / CLI`websift`                                                 | Unchanged names                                           |
| `WebSearchClient(max_results=..., timeout=..., max_page_chars=...)` | Supported;`timeout` still maps to both search and fetch |
| MCP tools`web_search` / `web_fetch`                               | Same names and`query` / `url` schemas                 |
| `MCP_HOST` default                                                  | **Breaking default**: `0.0.0.0` → `127.0.0.1`  |
| `SEARCH_TIMEOUT`                                                    | Still read as alias for timeouts                          |

## [0.1.0] - 2026-07-20

Initial alpha: DDGS search, urllib fetch, basic SSRF, MCP FastMCP server.
