# websift

A lightweight **Python library** and **free, self-hosted MCP server** for real-time web access — DuckDuckGo search + page fetching (HTML → Markdown, PDF → text) — with SSRF protection and DNS pinning. **No API key required** for the default provider.

```python
from websift import WebSearchClient

print(WebSearchClient().search("python asyncio"))
```

Prefer the library when you only need search/fetch in process; run `websift serve` when you want MCP tools for AI clients.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/badge/PyPI-websift-orange.svg)](https://pypi.org/project/websift/)
[![MCP](https://img.shields.io/badge/MCP-streamable--http-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Table of Contents

- [What It Does](#what-it-does)
- [Why Use This](#why-use-this)
- [Comparison with Alternatives](#comparison-with-alternatives)
- [Architecture](#architecture)
- [Installation](#installation)
  - [Option 1: PyPI (Recommended)](#option-1-pypi-recommended)
  - [Option 2: Docker Compose](#option-2-docker-compose)
  - [Option 3: Docker (Manual)](#option-3-docker-manual)
  - [Option 4: Local Python (No Docker)](#option-4-local-python-no-docker)
- [Usage](#usage)
  - [CLI](#cli)
  - [As a Python Library (Direct Import)](#as-a-python-library-direct-import)
  - [As an MCP Server (For AI Clients)](#as-an-mcp-server-for-ai-clients)
- [Tools](#tools)
- [Configuration](#configuration)
- [Connecting to AI Clients](#connecting-to-ai-clients)
  - [VS Code (GitHub Copilot)](#1-vs-code-github-copilot)
  - [Claude Desktop](#2-claude-desktop)
  - [Claude Code](#3-claude-code)
  - [Copilot CLI](#4-copilot-cli)
  - [Cursor](#5-cursor)
  - [Windsurf (Codeium)](#6-windsurf-codeium)
  - [JetBrains IDEs](#7-jetbrains-ides)
  - [Any MCP Client (Generic)](#8-any-mcp-client-generic)
- [Use Cases](#use-cases)
- [Security](#security)
- [Development](#development)
- [FAQ](#faq)

---

## What It Does

This MCP server exposes two tools to any AI agent or LLM client:

| Tool           | Input              | Output                                                                 |
| -------------- | ------------------ | ---------------------------------------------------------------------- |
| `web_search` | `query` (string) | Title, URL, and snippet for each DuckDuckGo result                     |
| `web_fetch`  | `url` (string)   | Readable text content from any webpage (HTML → Markdown, PDF → text) |

That's it — simple, focused, and reliable.

---

## Why Use This

### Core Strengths

- **🆓 Completely Free (default)** — Default **DDGS** provider needs no API key or subscription. Upstream DuckDuckGo and target sites may still rate-limit or block clients.
- **🪶 Lightweight** — Single Python process, few base dependencies (MCP optional), runs in a tiny Docker container (`python:3.12-slim` ≈ 150 MB).
- **🔒 Secure by Default** — SSRF protection (global-only IP policy, multi-answer DNS validation, no URL userinfo), DNS pinning + SNI, redirect re-validation, body/decompress limits, and content-type checks.
- **🌐 Universal MCP Compatibility** — Works with any MCP client (VS Code, Claude, Cursor, Windsurf, JetBrains, custom agents, etc.).
- **📄 Smart Content Extraction** — HTML → Markdown via BeautifulSoup (main-content selection), PDF → text via **pypdf only**, binary detection, charset order BOM → HTTP → meta → UTF-8.
- **🐙 GitHub README Shortcut** — Fetching a `github.com/owner/repo` URL uses the GitHub API for the raw README (non-credential headers only).
- **🏠 Self-Hosted** — You run the process; still makes **outbound** requests to the search provider and fetched URLs.

### Ideal For

- **🐍 Python Scripts & Apps** — Import `WebSearchClient` directly in your code. No server, no Docker, no MCP overhead.
- **AI Agents & Agentic Workflows** — Give any autonomous agent the ability to search the web and read pages on demand.
- **Development Assistants** — Let Copilot, Claude, or Cursor look up documentation, error messages, or package info in real time.
- **Research & Analysis** — Fetch and summarize articles, papers, or documentation pages.
- **Cost-Sensitive Deployments** — Replace paid web-search APIs (Tavily, Firecrawl, Exa, etc.) with a free self-hosted alternative.
- **Air-Gapped / Private Networks** — Run entirely offline (search requires internet, but fetch can work with internal URLs if you adjust security rules).

---

## Comparison with Alternatives

| Feature                    | **websift**      | Tavily MCP                  | Firecrawl MCP         | Exa MCP               | Brave Search MCP            |
| -------------------------- | ---------------------- | --------------------------- | --------------------- | --------------------- | --------------------------- |
| **Price**            | ✅ Free                | 💰 Paid (free tier limited) | 💰 Paid               | 💰 Paid               | 💰 Paid (free tier limited) |
| **API Key Required** | ✅ No                  | ❌ Yes                      | ❌ Yes                | ❌ Yes                | ❌ Yes                      |
| **Self-Hosted**      | ✅ Yes                 | ❌ No                       | ⚠️ Partial          | ❌ No                 | ❌ No                       |
| **Web Search**       | ✅ DuckDuckGo          | ✅ Proprietary              | ❌ (scrape only)      | ✅ Proprietary        | ✅ Brave                    |
| **Web Fetch**        | ✅ HTML + PDF          | ✅ Yes                      | ✅ Yes (deep)         | ✅ Yes                | ❌ No                       |
| **SSRF Protection**  | ✅ Built-in            | ⚠️ Managed                | ⚠️ Managed          | ⚠️ Managed          | ⚠️ Managed                |
| **Container Size**   | ~150 MB                | N/A (SaaS)                  | ~500 MB+              | N/A (SaaS)            | N/A (SaaS)                  |
| **Dependencies**     | 3 base (+ optional MCP) | N/A                         | Many                  | N/A                   | N/A                         |
| **Rate Limits**      | Upstream DDGS / sites  | Provider limits             | Provider limits       | Provider limits       | Provider limits             |
| **Privacy**          | Self-hosted + outbound | ⚠️ Data to provider       | ⚠️ Data to provider | ⚠️ Data to provider | ⚠️ Data to provider       |

### When to Choose What

| Scenario                                                               | Recommended          |
| ---------------------------------------------------------------------- | -------------------- |
| You want**free, no-signup** web access for AI                    | **websift** ✅ |
| You need**deep scraping** (JS-rendered pages, sitemaps)          | Firecrawl            |
| You need**semantic search** (AI-powered relevance)               | Exa                  |
| You want**agentic-optimized** search (Tavily's `extract` mode) | Tavily               |
| You want**self-hosted** control (still outbound search/fetch)    | **websift** ✅ |
| You're building a**custom AI agent** with minimal infra          | **websift** ✅ |

---

## Architecture

```
┌─────────────┐     MCP Protocol      ┌──────────────────┐
│  AI Client  │ ◄── (streamable-HTTP) ┤   MCP Server     │
│  (Copilot,  │                       │   (FastMCP)      │
│   Claude,   │                       └─────────┬────────┘
│   Cursor…)  │                                 │
└─────────────┘                    ┌────────────┴─────────┐
                                   │  WebSearchClient     │
┌────────────┐                     │  + WorkLimits        │
│  search()  │──► SearchProvider   │                      │
│            │    (default: DDGS)  │                      │
│  fetch()   │──► urllib + SSRF    │                      │
│            │    ├── html.py      │                      │
│            │    ├── http.py      │                      │
│            │    ├── security.py  │                      │
│            │    └── content.py   │                      │
└────────────┘                     └──────────────────────┘
```

Outbound data flow: **search** → configured provider (default DuckDuckGo via `ddgs`); **fetch** → primary provider (`BaseProvider.fetch`, generic SSRF-safe by default). With `SEARCH_PROVIDER=tavily|exa` and `PROVIDER_NATIVE_FETCH=true` (default), `web_fetch` may call Tavily `/extract` or Exa `/contents` (credits apply) before falling back to generic fetch. Provider API secrets never ride the target page-fetch path; native extract sends only the URL as JSON to the provider origin.

### Module Structure

```
websift/
├── __init__.py       # WebSearchClient, AppSettings, __version__
├── __main__.py       # python -m websift
├── cli.py            # argparse CLI (serve / search / fetch)
├── settings.py       # AppSettings.from_env() — no env read on import
├── concurrency.py    # WorkLimits (search/fetch/PDF bounds)
├── models.py         # SearchResponse / FetchResult internals
├── config.py         # size limits, user-agents, MIME types
├── security.py       # SSRF: global-only IPs, multi-answer DNS, no userinfo
├── content.py        # content-type detection (PDF, binary, HTML heuristics)
├── http.py           # page fetch: redirects, DNS pin + SNI, body/decompress caps
├── html.py           # HTML → Markdown, main content, truncation
├── client.py         # public search/fetch façade
├── provider_http.py  # credentialed provider transport (isolated from page fetch)
├── providers/        # SearchProvider contract, registry, DDGS + others
└── server.py         # create_server / ServerApp
server.py             # thin entry → websift.cli:main
```

---

## Installation

### Option 1: PyPI (Recommended)

```bash
pip install websift
```

That's it for the **Python library** and CLI `search` / `fetch`. For the **MCP server** (`websift serve`):

```bash
pip install 'websift[mcp]'
```

### Option 2: Docker Compose

```bash
# Clone and start (no .env file required)
git clone <repo-url>
cd websift
docker compose up -d --build
```

The MCP server will be available at `http://localhost:8787/mcp`.

- Runs as non-root (`uid 10001`), entrypoint `websift` from the installed wheel.
- Inject secrets at runtime only, e.g. `MCP_BEARER_TOKEN=... BRAVE_API_KEY=... docker compose up -d` or `docker compose --env-file .env up -d`.
- Image default bind is `0.0.0.0` **inside** the container network so published ports work; protect with host firewall, reverse proxy, and/or `MCP_AUTH_MODE=bearer`.

Optional resource limits (compose / orchestrator): ~512 MB RAM and 1 CPU are enough for light use.

### Option 3: Docker (Manual)

```bash
docker build -t websift .
docker run -d --name websift -p 8787:8787 \
  -e MCP_AUTH_MODE=none \
  websift
# With bearer auth:
# docker run -d --name websift -p 8787:8787 \
#   -e MCP_AUTH_MODE=bearer -e MCP_BEARER_TOKEN='…' websift
```

### Option 4: Local Python (No Docker)

```bash
# Recommended: install the package (editable for development; includes MCP)
pip install -e ".[dev]"  # includes MCP for server tests

# Or library-only runtime deps (mirrors base pyproject.toml)
pip install -r requirements.txt
pip install -e .

# MCP server needs the optional extra
pip install -e ".[mcp]"

# Run the server (console entry or module)
websift serve
# websift                 # same as serve when no command is given
# python -m websift serve
# python server.py serve
```

---

## Usage

### CLI

After `pip install websift`, the `websift` command supports help, version, and subcommands:

```bash
websift --help
websift --version

# Start MCP server (default when no command is given)
websift
websift serve
websift serve --host 0.0.0.0 --port 9000 --transport streamable-http
websift serve --auth-mode bearer --bearer-token 'a-long-random-secret'
websift serve --provider ddgs --max-results 8 --log-level DEBUG

# One-shot library-style commands (no MCP server)
websift search "Python 3.12 features"
websift search "asyncio tutorial" -n 10 --provider ddgs
websift search "python" --json          # structured JSON for scripts
websift fetch https://docs.python.org/3/
websift fetch https://example.com/doc.pdf --max-chars 20000
websift fetch https://example.com --json
```

| Command                         | Purpose                        |
| ------------------------------- | ------------------------------ |
| `websift` / `websift serve` | Run the MCP server             |
| `websift search QUERY`        | Print search results to stdout |
| `websift search QUERY --json` | JSON: `ok` / `results` / `error` (exit `1` if not ok) |
| `websift fetch URL`           | Print page/PDF text to stdout  |
| `websift fetch URL --json`    | JSON: `ok` / `content` / `error` (exit `1` if not ok) |
| `websift --version` / `-V`  | Print package version          |
| `websift --help` / `-h`     | Show help                      |

CLI flags override the corresponding environment variables for that process. Full env matrix is under [Configuration](#configuration).

### As a Python Library (Direct Import)

Use `WebSearchClient` directly in your Python code — **no server needed**:

```python
from websift import WebSearchClient

client = WebSearchClient()

# Search the web (DuckDuckGo by default)
results = client.search("Python 3.12 features")
print(results)

# Fetch a web page (HTML → Markdown, PDF → text)
content = client.fetch("https://docs.python.org/3/")
print(content)

# Async (offloads sync search/fetch to a worker thread)
# results = await client.asearch("Python 3.12 features")
# content = await client.afetch("https://docs.python.org/3/")
```

#### Customizing `WebSearchClient`

Pass constructor kwargs — no need to edit env vars for library use:

```python
from websift import WebSearchClient, AppSettings
from websift.settings import ProviderSettings, ExtractionSettings, FetchSettings

# Simple tuning
client = WebSearchClient(
    max_results=10,
    timeout=20,              # shared search+fetch timeout (legacy)
    max_page_chars=50_000,
)

# Separate timeouts + provider name + extraction flags
client = WebSearchClient(
    max_results=8,
    search_timeout=15,
    fetch_timeout=45,
    max_page_chars=64_000,
    provider="ddgs",           # or "brave" / "tavily" / "exa" / "searxng" / "serper"
    include_links=True,
    include_images=False,
    output_format="markdown",  # or "text"
    native_fetch=True,         # Tavily/Exa paid extract when keyed
)

# Keyed provider (API key stays in your process — never accepted via MCP tools)
client = WebSearchClient(
    provider="brave",
    api_key="BSA...",
    # base_url="https://api.search.brave.com",  # optional override
    fallback_providers=["ddgs"],
    max_results=5,
)

# Full settings tree (also: AppSettings.from_env())
settings = AppSettings(
    provider=ProviderSettings(name="ddgs", max_results=10, timeout_seconds=20),
    fetch=FetchSettings(timeout_seconds=45),
    extraction=ExtractionSettings(max_page_chars=50_000, include_links=True),
)
client = WebSearchClient(settings=settings)

# Or load env, then use as-is
client = WebSearchClient(settings=AppSettings.from_env())
```

| Kwarg                                         | Type                          | Description                                                                     |
| --------------------------------------------- | ----------------------------- | ------------------------------------------------------------------------------- |
| `max_results`                               | `int`                       | Max search hits (default`5`)                                                  |
| `timeout`                                   | `int`                       | Shared search+fetch timeout seconds when separate timeouts omit (default`30`) |
| `search_timeout`                            | `float`                     | Search-only timeout                                                             |
| `fetch_timeout`                             | `float`                     | Fetch-only timeout                                                              |
| `max_page_chars`                            | `int`                       | Max characters returned from fetch                                              |
| `provider`                                  | `str` or `SearchProvider` | Provider name (`ddgs`, `brave`, …) or instance                             |
| `api_key` / `base_url`                    | `str`                       | Credentials/endpoint for keyed or self-hosted providers                         |
| `fallback_providers`                        | sequence of`str`            | Opt-in fallback chain after primary                                             |
| `safe_search` / `region` / `time_range` | `str`                       | Optional search filters                                                         |
| `include_links` / `include_images`        | `bool`                      | HTML extraction options                                                         |
| `output_format`                             | `str`                       | `markdown` or `text`                                                        |
| `native_fetch`                              | `bool`                      | Allow Tavily/Exa native extract for fetch                                       |
| `settings`                                  | `AppSettings`               | Full config tree (advanced kwargs still overlay when set)                       |

**Perfect for:**

- Custom scripts & automation
- Embedding in your own applications
- Data pipelines & ETL workflows
- Testing & prototyping

### As an MCP Server (For AI Clients)

Run the server to expose tools to any MCP-compatible AI client:

```bash
# Start the server (default: 127.0.0.1:8787, streamable-http)
websift serve

# Custom bind / transport via CLI (overrides env for this process)
websift serve --host 0.0.0.0 --port 9000 --transport sse

# Or via environment variables
MCP_PORT=9000 MCP_TRANSPORT=sse websift serve
```

Or via Python:

```python
from websift.server import create_server
from websift.settings import AppSettings

create_server(AppSettings.from_env()).run()
# or: from websift.cli import main; main(["serve"])
```

**Perfect for:**

- VS Code (GitHub Copilot)
- Claude Desktop / Claude Code
- Cursor, Windsurf, JetBrains IDEs
- Any MCP-compatible agent

---

## Tools

### `web_search(query: str) -> str`

Searches DuckDuckGo and returns formatted results with title, URL, and snippet.

**Example:**

```
Agent: web_search("latest Python 3.12 features")
Server:
Title: What's New in Python 3.12
URL: https://docs.python.org/3/whatsnew/3.12.html
Snippet: Python 3.12 introduces several performance improvements...

---

Title: Python 3.12 Release Notes
URL: https://www.python.org/downloads/release/python-3120/
Snippet: The Python 3.12 release includes bug fixes and...
```

### `web_fetch(url: str) -> str`

Fetches a URL and returns readable text content. Handles:

- **HTML pages** → Markdown (BeautifulSoup block-flow + main-content selection)
- **PDF files** → text extracted via **pypdf only**
- **Plain text / JSON / XML** → returned as-is
- **GitHub repos** → README via GitHub API (non-credential headers)
- **Binary files** → detected and blocked (images, executables, archives)

**Example:**

```
Agent: web_fetch("https://github.com/python/cpython")
Server:
README of https://github.com/python/cpython (via GitHub API):

# Python
The Python programming language...
```

---

## Configuration

### Environment Variables

| Variable                      | Default             | Description                                                                     |
| ----------------------------- | ------------------- | ------------------------------------------------------------------------------- |
| `MCP_HOST`                  | `127.0.0.1`       | Bind address (use`0.0.0.0` only when intentionally exposing)                  |
| `MCP_PORT`                  | `8787`            | Listen port                                                                     |
| `MCP_TRANSPORT`             | `streamable-http` | Transport:`streamable-http`, `sse`, or `stdio`                            |
| `MCP_AUTH_MODE`             | `none`            | `none` or `bearer` (HTTP/SSE only)                                          |
| `MCP_BEARER_TOKEN`          | (empty)             | Shared secret when`MCP_AUTH_MODE=bearer`                                      |
| `SEARCH_PROVIDER`           | `ddgs`            | Server-wide search provider (**allowlisted**; not settable per tool call) |
| `SEARCH_MAX_RESULTS`        | `5`               | Max search results returned                                                     |
| `SEARCH_TIMEOUT_SECONDS`    | `30`              | Search timeout (seconds)                                                        |
| `PROVIDER_NATIVE_FETCH`     | `true`            | Tavily/Exa may use paid extract/contents for`web_fetch`                       |
| `FETCH_TIMEOUT_SECONDS`     | `30`              | Page fetch timeout (seconds)                                                    |
| `SEARCH_TIMEOUT`            | (alias)             | **Deprecated**: if set and specific timeouts omit, maps to both           |
| `SEARCH_FALLBACK_PROVIDERS` | (empty)             | Comma-separated allowlisted fallbacks after primary (no config/auth fallback)   |
| `SEARCH_RETRY_MAX`          | `1`               | Extra retries after first attempt (DDGS + HTTP providers)                       |
| `SEARCH_RETRY_BACKOFF_SECONDS` | `0.5`          | Base backoff (seconds); doubles each attempt, capped                              |
| `PAGE_MAX_CHARS`            | `128000`          | Max characters returned from fetch                                              |
| `SEARCH_MAX_CONCURRENCY`    | `8`               | Max concurrent search operations                                                |
| `FETCH_MAX_CONCURRENCY`     | `16`              | Max concurrent page fetches                                                     |
| `PDF_MAX_CONCURRENCY`       | `2`               | Max concurrent PDF parses                                                       |
| `CACHE_ENABLED`             | `false`           | Opt-in in-memory TTL/LRU cache for successful search/fetch                      |
| `SEARCH_CACHE_TTL_SECONDS`  | `300`             | Search cache TTL when enabled                                                   |
| `FETCH_CACHE_TTL_SECONDS`   | `600`             | Fetch cache TTL when enabled                                                    |
| `CACHE_MAX_ENTRIES`         | `256`             | Max cache entries                                                               |
| `CACHE_MAX_BYTES`           | `33554432`        | Approx max cache payload bytes                                                  |

### Search providers

Server-wide only (`SEARCH_PROVIDER`). MCP tools never accept provider name, base URL, or API keys.

| Provider                 | Extra                                              | Credentials / endpoint                                        | Notes                                                                             |
| ------------------------ | -------------------------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| **ddgs** (default) | base install                                       | none                                                          | DuckDuckGo via`ddgs` package                                                    |
| **searxng**        | `websift[searxng]` (marker; no extra deps today) | `SEARXNG_BASE_URL` (required), optional `SEARXNG_API_KEY` | Self-hosted; set`PROVIDER_ALLOW_HTTP=true` only for local `http://` instances |
| **brave**          | `websift[brave]`                                 | `BRAVE_API_KEY` (required), optional `BRAVE_BASE_URL`     | Official Web Search API                                                           |
| **tavily**         | `websift[tavily]`                                | `TAVILY_API_KEY` (required), optional `TAVILY_BASE_URL`   |                                                                                   |
| **exa**            | `websift[exa]`                                   | `EXA_API_KEY` (required), optional `EXA_BASE_URL`         |                                                                                   |
| **serper**        | `websift[serper]` (marker; no extra deps today) | `SERPER_API_KEY` (required), optional `SERPER_BASE_URL` | Google SERP via Serper API                                                      |

Convenience: `pip install 'websift[providers]'` (all keyed/self-hosted HTTP providers — currently no extra wheels beyond the base package; adapters use stdlib HTTP).

Optional filters (provider-dependent): `SEARCH_SAFE_SEARCH`, `SEARCH_REGION`, `SEARCH_TIME_RANGE`. Unsupported filters fail closed unless `SEARCH_ALLOW_UNSUPPORTED_FILTERS=true`.

Fallback chain (opt-in):

```bash
export SEARCH_PROVIDER=brave
export BRAVE_API_KEY=...
export SEARCH_FALLBACK_PROVIDERS=ddgs
# Does not fall back on config/auth errors (missing key, etc.)
```

### Internal Limits

| Setting          | Value   | Description               |
| ---------------- | ------- | ------------------------- |
| Max page size    | 4 MB    | Normal page fetch limit   |
| Max PDF size     | 20 MB   | PDF fetch limit           |
| Max output chars | 128,000 | Characters sent to LLM    |
| Max redirects    | 5       | HTTP redirect chain limit |

---

## Connecting to AI Clients

### 1. VS Code (GitHub Copilot)

> 📖 **Official docs**: [Add and manage MCP servers in VS Code](https://code.visualstudio.com/docs/agent-customization/mcp-servers) | [MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)

#### Via Extensions View (Easiest)

1. Open Extensions view (`Ctrl+Shift+X`)
2. Search `@mcp` in the search field
3. Install any MCP server from the gallery

#### Via `mcp.json` (Custom Server)

Create `.vscode/mcp.json` in your workspace:

```json
{
  "mcpServers": {
    "web-search": {
      "type": "http",
      "url": "http://localhost:8787/mcp"
    }
  }
}
```

Or for global (user-level) configuration, run `MCP: Open User Configuration` from the Command Palette and add the same entry.

#### Verify

Open Chat (`Ctrl+Cmd+I` / `Ctrl+Ctrl+I`) and ask: *"Search for the latest Python release notes"*

### 2. Claude Desktop

> 📖 **Official docs**: [Getting Started with Local MCP Servers on Claude Desktop](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop) | [Desktop Extensions](https://www.anthropic.com/engineering/desktop-extensions)

#### Via Settings UI

1. Open Claude Desktop → Settings → Extensions
2. Click "Advanced settings" → "Install Extension…"
3. Or manually add via the configuration file

#### Via Configuration File

Edit `~/.config/claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "web-search": {
      "url": "http://localhost:8787/mcp"
    }
  }
}
```

Restart Claude Desktop after editing.

### 3. Claude Code

> 📖 **Official docs**: [Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp)

```bash
# Add the MCP server (HTTP transport)
claude mcp add --transport http web-search http://localhost:8787/mcp

# Verify it's connected
claude mcp list

# Use it in conversation
claude "Search for the latest Rust release and summarize the key changes"
```

**Scopes:**

```bash
# Project scope (default, stored in .mcp.json)
claude mcp add --transport http web-search http://localhost:8787/mcp

# User scope (available across all projects)
claude mcp add --transport http web-search --scope user http://localhost:8787/mcp
```

### 4. Copilot CLI

> 📖 **Official docs**: [Adding MCP servers for GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)

#### Interactive Mode

```
/mcp add
# Server Name: web-search
# Server Type: HTTP
# URL: http://localhost:8787/mcp
# Press Ctrl+S to save
```

#### Command Line

```bash
copilot mcp add web-search --transport http --url http://localhost:8787/mcp
```

#### Config File

Edit `~/.github/copilot/mcp-config.json`:

```json
{
  "mcpServers": {
    "web-search": {
      "type": "http",
      "url": "http://localhost:8787/mcp"
    }
  }
}
```

### 5. Cursor

> 📖 **Official docs**: [Model Context Protocol (MCP) | Cursor Docs](https://cursor.com/docs/mcp)

Create `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project):

```json
{
  "mcpServers": {
    "web-search": {
      "type": "http",
      "url": "http://localhost:8787/mcp"
    }
  }
}
```

Restart Cursor, then use Chat or Agent mode to invoke the tools.

### 6. Windsurf (Codeium)

> 📖 **Official docs**: [Cascade MCP Integration](https://docs.windsurf.com/plugins/cascade/mcp)

Create `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "web-search": {
      "type": "http",
      "url": "http://localhost:8787/mcp"
    }
  }
}
```

Alternatively, use the built-in UI: **Settings → Cascade → MCP Servers**.

### 7. JetBrains IDEs

> 📖 **Official docs**: [MCP Server | IntelliJ IDEA Documentation](https://www.jetbrains.com/help/idea/mcp-server.html)

1. Install the "MCP Client" plugin from the JetBrains Marketplace
2. Go to **Settings → Tools → MCP**
3. Add a new server:
   - Name: `web-search`
   - Type: `HTTP`
   - URL: `http://localhost:8787/mcp`
4. Apply and restart

### 8. Any MCP Client (Generic)

For any MCP-compatible client, the server is accessible at:

- **Streamable HTTP** (recommended): `http://localhost:8787/mcp`
- **SSE**: `http://localhost:8787/mcp/sse` (set `MCP_TRANSPORT=sse`)
- **STDIO**: Run `websift serve --transport stdio` (or `MCP_TRANSPORT=stdio websift serve`)

Generic HTTP configuration:

```json
{
  "mcpServers": {
    "web-search": {
      "type": "http",
      "url": "http://localhost:8787/mcp"
    }
  }
}
```

---

## Use Cases

### AI Agent Web Research

```
User: "Find the latest benchmarks for LLM inference optimization"
Agent: web_search("LLM inference optimization benchmarks 2025")
Agent: web_fetch("https://example.com/benchmark-article")
Agent: [Summarizes findings from fetched content]
```

### Documentation Lookup

```
User: "How do I configure CORS in FastAPI?"
Agent: web_search("FastAPI CORS configuration")
Agent: web_fetch("https://fastapi.tiangolo.com/tutorial/cors/")
Agent: [Provides code example from documentation]
```

### Error Debugging

```
User: "I'm getting 'ModuleNotFoundError: no module named '_sqlite3'"
Agent: web_search("ModuleNotFoundError _sqlite3 Python Docker")
Agent: [Finds solution: install python3-dev packages]
```

### Competitive Analysis

```
User: "What are the latest features in React 19?"
Agent: web_search("React 19 new features")
Agent: web_fetch("https://react.dev/blog/2024")
Agent: [Summarizes new features]
```

### Agentic AI Workflows

This server is particularly well-suited for agentic AI because:

- **Deterministic tools** — `web_search` and `web_fetch` have clear, predictable inputs and outputs.
- **No authentication overhead** — agents don't need to manage API keys.
- **Self-hosted** — one process/container; still needs outbound HTTPS for search and fetches.
- **SSRF-safe** — global-only DNS policy reduces risk of internal network exposure from agent-supplied URLs.
- **Markdown output** — structured text that LLMs can process efficiently.

---

## Security

### Built-in Protections

| Protection                    | How It Works                                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------------------------------- |
| **SSRF Prevention**     | **Every** DNS answer must be a global unicast IP; private/loopback/link-local/special-use rejected |
| **No URL userinfo**     | Credentials in the authority (`user:pass@host`) are rejected                                           |
| **DNS Pinning + SNI**   | Connect to a validated pinned IP; TLS SNI/hostname still match the requested host                        |
| **Redirect re-check**   | Each redirect re-runs URL + multi-answer DNS validation (max 5 hops)                                     |
| **Binary Detection**    | Images, executables, archives, and other binary content are blocked                                      |
| **Size Limits**         | Body/decompress caps; 4 MB normal pages, 20 MB PDFs, 128,000 chars default output                        |
| **Charset order**       | BOM → HTTP`Content-Type` → HTML meta → UTF-8                                                        |
| **Credential boundary** | Provider secrets stay in provider HTTP; page fetch never inherits them                                   |

### Network Considerations

- Binds to `127.0.0.1` by default. Set `MCP_HOST=0.0.0.0` only when intentionally exposing (e.g. Docker); a `UserWarning` is emitted for non-loopback binds.
- **Optional bearer auth** for remote HTTP/SSE: set `MCP_AUTH_MODE=bearer` and `MCP_BEARER_TOKEN`. Clients send `Authorization: Bearer <token>`. STDIO does not use the token. Prefer loopback + local clients, or a reverse proxy, for production exposure.
- Search and fetch always generate **outbound** traffic (provider + target sites). This is not an air-gapped offline search engine.
- Docker Compose isolates the process in a container network; the image may still bind `0.0.0.0` inside the container for port publishing.

---

## Development

### Project Structure

```
websift/
├── pyproject.toml          # Package metadata (dynamic version), deps, console script
├── CHANGELOG.md            # Keep a Changelog
├── docker-compose.yml      # Docker Compose setup
├── Dockerfile              # Python 3.12-slim container
├── requirements.txt        # Runtime deps mirror (prefer pyproject.toml)
├── server.py               # Thin entry → websift.cli:main
├── .env.example            # Environment variable template
├── .github/workflows/      # Build/test matrix + PyPI publish gate
├── README.md               # This file
├── docs/
│   └── README.vi.md        # Vietnamese documentation
├── tests/                  # Offline pytest suite (markers: live, provider)
└── websift/
    ├── __init__.py         # WebSearchClient, AppSettings, __version__
    ├── __main__.py         # python -m websift
    ├── cli.py              # argparse CLI
    ├── settings.py         # Typed AppSettings
    ├── auth.py             # Bearer token + body limit guards
    ├── concurrency.py      # WorkLimits
    ├── models.py           # Structured internals
    ├── config.py           # Constants
    ├── security.py         # SSRF / DNS
    ├── content.py          # Content-type detection
    ├── http.py             # Page fetch
    ├── html.py             # HTML → Markdown
    ├── client.py           # Public façade
    ├── provider_http.py    # Provider credential transport
    ├── providers/          # DDGS + registry
    └── server.py           # create_server / ServerApp
```

### Naming

| Surface                      | Name                                                    |
| ---------------------------- | ------------------------------------------------------- |
| PyPI / CLI / Docker / import | `websift`                                             |
| MCP tools (stable)           | `web_search`, `web_fetch`                           |
| Version source               | `websift.__version__` (dynamic in `pyproject.toml`) |

### Migration from `web_search` (pre-1.0)

The import package was renamed in **1.0.0**:

```python
# Before
from web_search import WebSearchClient

# After
from websift import WebSearchClient, AppSettings
```

- Install/CLI/Docker remain `websift`.
- MCP tool names stay `web_search` / `web_fetch` (schemas unchanged).
- Prefer `WebSearchClient(...)` kwargs or `AppSettings` over editing env when embedding as a library.

### Running Locally

```bash
# Install from PyPI
pip install websift

# Or editable + dev tools
pip install -e ".[dev]"

# CLI help / version
websift --help
websift --version

# Run as MCP server
websift serve

# Custom settings via CLI flags (or env)
websift serve --port 9000 --transport sse

# One-shot search / fetch
websift search "test"
websift fetch https://example.com

# Library (no server)
python -c "from websift import WebSearchClient; print(WebSearchClient().search('test'))"
```

### Lint, test, build

```bash
# Lint
ruff check websift tests
ruff format --check websift tests

# Offline tests + coverage gate (≥85%)
python -m pytest --cov=websift --cov-report=term-missing --cov-fail-under=85 -m "not live and not provider"

# Package
python -m build
twine check dist/*
```

### Running with Docker

```bash
# Build and start (no .env required)
docker compose up -d --build

# Optional secrets via env file or shell
# docker compose --env-file .env up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

Image runs as non-root (`websift` uid 10001), entrypoint `websift`, TCP healthcheck on `MCP_PORT`.

---

## FAQ

### Q: Does this require an API key?

**Not for the default DDGS provider.** DuckDuckGo search needs no key. Optional providers **Brave / Tavily / Exa / Serper** need server env keys (`BRAVE_API_KEY`, `SERPER_API_KEY`, …); **SearXNG** needs `SEARXNG_BASE_URL`. Keys are never accepted via MCP tool arguments — see [Search providers](#search-providers).

### Q: Is this unlimited / no rate limits?

**No.** Websift does not sell a quota, but DuckDuckGo, other providers, and target sites can throttle, CAPTCHA, or block clients. Concurrent MCP calls are also bounded by `SEARCH_MAX_CONCURRENCY` / `FETCH_MAX_CONCURRENCY` / `PDF_MAX_CONCURRENCY`.

### Q: Can I use this behind a firewall?

Yes, if outbound HTTPS to the search provider and target websites is allowed. Inbound access is only needed for the MCP endpoint when using HTTP/SSE (default loopback port 8787).

### Q: How does this compare to Tavily or Firecrawl?

This is simpler and free, but doesn't offer JS rendering, deep scraping, or semantic search. For basic web search + page fetching, it's a solid free alternative. See the [Comparison table](#comparison-with-alternatives) for details.

### Q: Can I add authentication?

Yes — for **streamable-http / SSE**:

```bash
export MCP_AUTH_MODE=bearer
export MCP_BEARER_TOKEN='a-long-random-secret'
```

Clients must send `Authorization: Bearer <token>`. Missing/invalid tokens get **401** without echoing the secret. STDIO ignores bearer (process-local trust). You can still put a reverse proxy in front (nginx basic auth, mTLS, etc.) and leave `MCP_AUTH_MODE=none`.

Optional body cap: `MCP_MAX_REQUEST_BODY_BYTES=1048576`.

### Q: What transport protocols are supported?

- **streamable-http** (recommended, default) — modern MCP standard
- **sse** — legacy Server-Sent Events (still supported)
- **stdio** — for local process communication

### Q: Why is the output limited to 128,000 characters?

This keeps responses within typical LLM context windows while providing substantial content. You can lower or raise it via `PAGE_MAX_CHARS`, `WebSearchClient(max_page_chars=...)`, or `MAX_PAGE_CHARS` in `websift/config.py`.

### Q: Can I use this for internal/private websites?

By default, SSRF protection blocks private IP ranges. To allow internal sites, modify `websift/security.py` to whitelist specific domains or IP ranges.

### Q: Can I use this as a Python library (without MCP)?

**Yes!** Just `pip install websift` (no MCP extra) and import directly:

```python
from websift import WebSearchClient

client = WebSearchClient(max_results=10, search_timeout=20, fetch_timeout=45)
client.search("your query")
client.fetch("https://example.com")
```

No server, no Docker, no MCP overhead — just pure Python.

### Q: Can I publish my own version to PyPI?

Yes. After making changes:

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# Test upload (TestPyPI)
twine upload --repository testpypi dist/*

# Real upload (PyPI)
twine upload dist/*
```

---

## License

MIT — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [DuckDuckGo Search (ddgs)](https://github.com/deedy5/ddgs) — search backend
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) — HTML parsing
- [pypdf](https://pypdf.readthedocs.io/) — PDF text extraction
- [FastMCP](https://github.com/modelcontextprotocol/python-sdk) — MCP server framework
- [Model Context Protocol](https://modelcontextprotocol.io/) — open protocol for AI tool integration
- [VS Code MCP Documentation](https://code.visualstudio.com/docs/agent-customization/mcp-servers) — official VS Code MCP guide
- [Claude Code MCP Documentation](https://code.claude.com/docs/en/mcp) — official Claude Code MCP guide
- [Cursor MCP Documentation](https://cursor.com/docs/mcp) — official Cursor MCP guide
- [Windsurf MCP Documentation](https://docs.windsurf.com/plugins/cascade/mcp) — official Windsurf MCP guide
- [Copilot CLI MCP Documentation](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers) — official GitHub Copilot CLI MCP guide
- [Claude Desktop MCP Documentation](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop) — official Claude Desktop MCP guide
- [JetBrains MCP Documentation](https://www.jetbrains.com/help/idea/mcp-server.html) — official JetBrains MCP guide
