# WebSift v2.0 — Hướng dẫn chi tiết

Tài liệu này giải thích **từng bước từng chút** cách cài đặt, cấu hình và chạy WebSift với đầy đủ tính năng: tìm kiếm, fetch trang web, render JavaScript qua browser, và kết nối với MCP client.

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc tổng thể](#kiến-trúc-tổng-thể)
- [Cài đặt nhanh](#cài-đặt-nhanh)
- [Browser Service — Chi tiết từng bước](#browser-service---chi-tiết-từng-bước)
- [Kết hợp Python + Docker + MCP](#kết-hợp-python--docker--mcp)
- [Fetch Backend Modes](#fetch-backend-modes)
- [Cấu hình chi tiết](#cấu-hình-chi-tiết)
- [Providers](#providers)
- [Bảo mật](#bảo-mật)
- [Kết nối MCP với AI Client](#kết-nối-mcp-với-ai-client)
- [Docker Compose Deployment](#docker-compose-deployment)
- [FAQ](#faq)

---

## Tổng quan

<details>
<summary>Click để mở — WebSift là gì và làm được gì?</summary>

### WebSift là gì?

WebSift là **thư viện Python** nhẹ và **MCP server miễn phí, tự host**, cung cấp khả năng truy cập web thời gian thực cho AI agents:

| Tính năng              | Mô tả                                                                         |
| ------------------------ | ------------------------------------------------------------------------------- |
| **Tìm kiếm web** | DuckDuckGo (miễn phí), Brave, Tavily, Exa, Serper, SearXNG                    |
| **Lấy nội dung** | HTML → Markdown, PDF → text                                                   |
| **Render JS**      | Browser service (Camoufox) cho SPA/trang JS-heavy —**bắt buộc Docker** |
| **Bảo mật**      | SSRF protection, DNS pinning, credential isolation                              |
| **MCP**            | Tương thích mọi MCP client (VS Code, Claude, Cursor, Windsurf, JetBrains)   |

### Điểm khác biệt v2.0

| v1.x                           | v2.0                                               |
| ------------------------------ | -------------------------------------------------- |
| Chỉ HTTP fetch                | HTTP + Browser (tùy chọn)                        |
| Provider.fetch() làm tất cả | `FetchOrchestrator` — native → HTTP → browser |
| Không có challenge detection | Detector challenge/JS-shell tự động escalate    |
| Browser không có             | Browser service tách riêng qua Docker            |

</details>

---

## Kiến trúc tổng thể

<details>
<summary>Click để mở — Sơ đồ kiến trúc</summary>

```
┌──────────────┐  MCP Protocol  ┌─────────────────────┐
│  AI Client   │ ◄────────────── │    MCP Server       │
│  (Copilot,   │  streamable-HTTP│    (FastMCP)        │
│   Claude,    │                └──────────┬───────────┘
│   Cursor…)   │                           │
└──────────────┐    ┌──────────────────────┴─────────────┐
               │    │       WebSearchClient               │
               │    │       + WorkLimits                  │
               │    └─────────────────┬───────────────────┘
               │                      │
┌──────────────┼──────────────────────┼───────────────────┐
│              │  search()            │  fetch()          │
│              │                      │                   │
│              ▼                      ▼                   │
│    ┌──────────────┐    ┌──────────────────────┐        │
│    │ SearchProvider│    │ FetchOrchestrator    │        │
│    │ (DDGS/Brave) │    │                      │        │
│    └──────────────┘    │ 1. Native provider   │        │
│                        │    (Tavily/Exa)      │        │
│                        │        │             │        │
│                        │ 2. HttpFetchBackend  │        │
│                        │    (SSRF-safe)       │        │
│                        │        │             │        │
│                        │ 3. Detector          │        │
│                        │    (challenge/JS)    │        │
│                        │        │             │        │
│                        │ 4. RemoteBrowser     │        │
│                        │    (Camoufox Docker) │        │
│                        └───────────┬──────────┘        │
└────────────────────────────────────┼────────────────────┘
                                     │  HTTP protocol
                                     ▼
                          ┌──────────────────────┐
                          │   Browser Service    │
                          │   (Docker container) │
                          │   Camoufox + FW      │
                          └──────────────────────┘
```

### Ba thành phần chính

| Thành phần                                      | Chạy ở đâu                  | Bắt buộc?                |
| ------------------------------------------------- | ------------------------------- | -------------------------- |
| **WebSift core** (ddgs + bs4 + pypdf)       | Python process                  | Có                        |
| **MCP server** (FastMCP)                    | Python process (extra`[mcp]`) | Tùy chọn                 |
| **Browser service** (Camoufox + Playwright) | Docker container                | Chỉ cần cho JS rendering |

### Quy tắc vàng

> **`pip install 'websift[browser]'` ≠ browser chạy được!**
>
> Extra `[browser]` chỉ cài **httpx** (client nhẹ). Browser runtime **bắt buộc chạy trong Docker**.
> WebSift connect tới browser qua HTTP, không phải gọi trực tiếp Camoufox.

</details>

<details>
<summary>Click để mở — Cấu trúc module</summary>

```
websift/
├── __init__.py         # WebSearchClient, AppSettings, __version__
├── __main__.py         # python -m websift
├── cli.py              # argparse CLI (serve / search / fetch)
├── settings.py         # Typed AppSettings — không đọc env khi import
├── auth.py             # Bearer token + body limit
├── concurrency.py      # WorkLimits (search/fetch/PDF)
├── models.py           # SearchResponse / FetchResult
├── config.py           # Giới hạn kích thước, user-agent, MIME
├── security.py         # SSRF: global-only IP, multi-answer DNS
├── content.py          # Phát hiện nội dung (PDF, nhị phân, HTML)
├── http.py             # Page fetch: redirect, DNS pin + SNI
├── html.py             # HTML → Markdown, main content
├── client.py           # Public search/fetch façade
├── provider_http.py    # Provider credential transport
├── doctor.py           # websift doctor
├── cache.py            # TTL/LRU cache
├── providers/          # DDGS + registry + adapter
│   ├── base.py         # SearchProvider contract
│   ├── ddgs.py         # DuckDuckGo
│   ├── brave.py        # Brave Search
│   ├── tavily.py       # Tavily
│   ├── exa.py          # Exa
│   ├── searxng.py      # SearXNG
│   ├── serper.py       # Serper
│   ├── fallback.py     # FallbackSearchProvider chain
│   └── registry.py     # Provider factory
├── fetching/           # Fetch orchestration (internal)
│   ├── backend.py      # FetchBackend protocol
│   ├── http.py         # HttpFetchBackend (SSRF-safe HTTP)
│   ├── detector.py     # Challenge/JS-shell detection
│   ├── orchestrator.py # FetchOrchestrator (native → HTTP → browser)
│   └── browser_client.py # RemoteBrowserBackend (httpx client)
└── server.py           # create_server / ServerApp

services/browser/       # Browser service tách riêng
├── browser_service/    # FastAPI app + Camoufox runtime
│   ├── main.py         # Entry point
│   ├── app.py          # FastAPI routes (/healthz, /v1/render)
│   ├── config.py       # Settings
│   ├── runtime.py      # Camoufox browser lifecycle
│   ├── proxy.py        # Egress forward proxy
│   └── policy.py       # URL/redirect/port policy
├── Dockerfile
├── pyproject.toml
└── tests/
```

</details>

---

## Cài đặt nhanh

<details>
<summary>Click để mở — Bắt đầu trong 2 phút</summary>

### Bước 1: Cài Python

```bash
python --version  # cần Python >= 3.10
```

### Bước 2: Cài WebSift

```bash
pip install websift
```

### Bước 3: Dùng thử

```bash
# Tìm kiếm
websift search "Python 3.12 features"

# Lấy nội dung trang
websift fetch https://example.com

# Python library
python -c "from websift import WebSearchClient; print(WebSearchClient().search('test'))"
```

### Bước 4: Chạy MCP server

```bash
pip install 'websift[mcp]'
websift serve
# Server chạy tại http://127.0.0.1:8787/mcp
```

### Với Docker Compose (toàn bộ + browser)

```bash
git clone <repo-url>
cd web-search-built-in
docker compose --profile browser up -d --build
# MCP server tại http://localhost:8787/mcp
# Browser service tại internal (không expose host)
```

### Kiểm tra

```bash
websift --version    # 2.0.0
websift doctor       # kiểm tra cài đặt
```

</details>

---

## Browser Service — Chi tiết từng bước

<details>
<summary>Click để mở — Browser service là gì?</summary>

### Vấn đề WebSift v1.x gặp phải

WebSift v1.x dùng `urllib` để fetch trang web. Cách này hoạt động tốt với HTML tĩnh và PDF, nhưng **không thể đọc được**:

- Trang web dùng React/Vue/Angular (SPA)
- Trang yêu cầu JavaScript để render nội dung
- Trang challenge của Cloudflare/DataDome (HTTP 200 nhưng chỉ có challenge shell)

### Giải pháp v2.0: Browser Service

WebSift v2.0 thêm một **service Docker container riêng** chạy Camoufox (Firefox fork) để render JavaScript. WebSift connect tới service này qua HTTP protocol.

### Tại sao phải tách riêng?

| Lý do                 | Giải thích                                                                                                                 |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Nhẹ**         | Base package chỉ 3 phụ thuộc (ddgs, bs4, pypdf). Không ai muốn`pip install` kéo theo Camoufox + Playwright + Firefox |
| **An toàn**     | Browser chạy trong container cô lập, non-root, resource limits                                                            |
| **Linh hoạt**   | Có thể scale browser service độc lập với MCP server                                                                    |
| **Dễ maintain** | Browser dependencies không conflict với WebSift                                                                            |

### Thành phần Browser Service

```
┌──────────────────────────────────────────┐
│         Browser Service Container        │
│                                          │
│  ┌─────────────┐   ┌──────────────────┐  │
│  │  FastAPI     │──│  Camoufox        │  │
│  │  (port 8790) │  │  (Playwright +  │  │
│  │              │  │   Firefox)       │  │
│  └──────┬───────┘  └──────────────────┘  │
│         │                                │
│  ┌──────▼───────┐                        │
│  │  Egress      │──► Internet            │
│  │  Proxy       │   (SSRF-safe)          │
│  │  (SSRF-safe) │                        │
│  └──────────────┘                        │
│                                          │
│  ┌──────────────────────────────────┐    │
│  │  Route Interceptor               │    │
│  │  (chặn subresource private IP)   │    │
│  └──────────────────────────────────┘    │
└──────────────────────────────────────────┘
```

### Protocol giữa WebSift và Browser Service

| Endpoint       | Method | Mô tả          |
| -------------- | ------ | ---------------- |
| `/healthz`   | GET    | Health check     |
| `/livez`     | GET    | Liveness check   |
| `/v1/render` | POST   | Render trang web |

Request `/v1/render`:

```json
{
  "protocol_version": "1",
  "url": "https://example.com",
  "render": {
    "timeout_seconds": 45,
    "post_load_wait_ms": 500,
    "max_html_bytes": 5000000
  },
  "policy": {
    "allow_http": true,
    "allowed_ports": [80, 443],
    "allowed_domains": [],
    "denied_domains": []
  }
}
```

Response `/v1/render` (thành công):

```json
{
  "protocol_version": "1",
  "ok": true,
  "result": {
    "html": "<!DOCTYPE html>...",
    "final_url": "https://example.com/",
    "content_type": "text/html",
    "status_code": 200,
    "bytes_read": 1234,
    "redirect_count": 0,
    "truncated": false
  }
}
```

Headers bắt buộc:

- `X-Websift-Browser-Protocol: 1` — protocol version
- `Authorization: Bearer <token>` — xác thực (bắt buộc khi expose ngoài loopback)

</details>

<details>
<summary>Click để mở — Bước 1: Cài đặt browser service</summary>

### Yêu cầu hệ thống

| Resource | Tối thiểu | Khuyến nghị |
| -------- | ----------- | ------------- |
| RAM      | 512 MB      | 1 GB          |
| CPU      | 1 core      | 2 cores       |
| Disk     | 500 MB      | 1 GB          |

### Phương pháp 1: Docker Compose (khuyến nghị)

```bash
# 1. Clone repo
git clone <repo-url>
cd web-search-built-in

# 2. Build và chạy browser service
docker compose --profile browser up -d --build

# 3. Kiểm tra
docker compose ps
# Thấy 2 container: websift + browser
```

### Phương pháp 2: Docker standalone

```bash
# 1. Build image
cd services/browser
docker build -t websift-browser .

# 2. Chạy container
docker run -d --name websift-browser \
  -p 8790:8790 \
  -e BROWSER_HOST=0.0.0.0 \
  -e BROWSER_PORT=8790 \
  -e BROWSER_TOKEN=your-secret-token \
  -e BROWSER_ALLOWED_PORTS=80,443 \
  -e BROWSER_ALLOW_HTTP=true \
  --shm-size=1g \
  websift-browser

# 3. Kiểm tra
curl http://localhost:8790/healthz
# {"status":"ready"}
```

### Phương pháp 3: Docker Compose chỉ browser (không có MCP)

Nếu bạn chỉ cần browser service và chạy WebSift Python riêng:

```bash
# Trong thư mục root của repo
docker compose --profile browser up -d --build browser
```

</details>

<details>
<summary>Click để mở — Bước 2: Cài đặt WebSift Python client</summary>

### Cài đặt WebSift với browser support

```bash
# Chỉ cần HTTP client (httpx) — KHÔNG cài browser runtime
pip install 'websift[browser]'

# Hoặc cài cả MCP + browser
pip install 'websift[mcp-browser]'

# Hoặc cài base rồi thêm
pip install websift
pip install httpx
```

### Cấu hình connect tới browser

WebSift Python client cần biết browser service ở đâu:

```bash
# Nếu browser chạy trong Docker Compose (mặc định):
export BROWSER_ENDPOINT=http://127.0.0.1:8790
export BROWSER_TOKEN=websift-dev-token
export BROWSER_ALLOW_INSECURE_ENDPOINT=true

# Nếu browser chạy trên server khác:
export BROWSER_ENDPOINT=https://browser.internal
export BROWSER_TOKEN=your-secret-token
# KHÔNG cần BROWSER_ALLOW_INSECURE_ENDPOINT với HTTPS
```

### Kiểm tra kết nối

```python
from websift import WebSearchClient

client = WebSearchClient(fetch_backend="browser")
content = client.fetch("https://example.com")
print(content)
```

</details>

<details>
<summary>Click để mở — Bước 3: Kết hợp MCP + Browser</summary>

### Scenario 1: MCP server trong Docker Compose

Khi dùng Docker Compose, MCP server (`websift`) và browser service (`browser`) chạy trong cùng network Docker:

```yaml
# docker-compose.yml (đã có sẵn)
services:
  websift:
    environment:
      BROWSER_ENDPOINT: ${BROWSER_ENDPOINT:-http://browser:8790}
      BROWSER_TOKEN: ${BROWSER_TOKEN:-websift-dev-token}
      BROWSER_ALLOW_INSECURE_ENDPOINT: ${BROWSER_ALLOW_INSECURE_ENDPOINT:-true}

  browser:
    profiles: ["browser"]
    environment:
      BROWSER_HOST: "0.0.0.0"
      BROWSER_PORT: "8790"
      BROWSER_TOKEN: ${BROWSER_TOKEN:-websift-dev-token}
      BROWSER_ALLOWED_PORTS: ${BROWSER_ALLOWED_PORTS:-80,443}
      BROWSER_ALLOW_HTTP: ${BROWSER_ALLOW_HTTP:-true}
```

Chạy:

```bash
docker compose --profile browser up -d --build
```

MCP server (`http://localhost:8787/mcp`) tự động có thể dùng browser:

- `web_fetch` trong MCP dùng `auto` mode
- HTTP fetch chạy trước
- Nếu detector phát hiện challenge/JS-shell → escalate browser

### Scenario 2: MCP server trên host Python

```bash
# 1. Chạy browser trong Docker
docker compose --profile browser up -d --build browser

# 2. Cấu hình env trên host
export BROWSER_ENDPOINT=http://127.0.0.1:8790
export BROWSER_TOKEN=websift-dev-token
export BROWSER_ALLOW_INSECURE_ENDPOINT=true

# 3. Chạy MCP server
pip install 'websift[mcp-browser]'
websift serve
```

### Scenario 3: Python library trực tiếp

```python
from websift import WebSearchClient, AppSettings
from websift.settings import BrowserSettings, FetchSettings

settings = AppSettings(
    fetch=FetchSettings(backend="auto", timeout_seconds=45),
    browser=BrowserSettings(
        endpoint="http://127.0.0.1:8790",
        bearer_token="websift-dev-token",
        allow_insecure_endpoint=True,
        timeout_seconds=60,
        max_html_bytes=5_000_000,
    ),
)
client = WebSearchClient(settings=settings)

# Fetch sẽ dùng auto: HTTP trước, browser khi cần
content = client.fetch("https://example.com")
print(content)

# Đóng connection pool khi xong
client.close()
```

### Flow kết nối từ đầu đến cuối

```
Bước 1: pip install 'websift[mcp-browser]'
         → Cài WebSift + FastMCP + httpx

Bước 2: docker compose --profile browser up -d --build
         → Chạy browser service trong Docker

Bước 3: export BROWSER_ENDPOINT=http://127.0.0.1:8790
         export BROWSER_TOKEN=websift-dev-token
         export BROWSER_ALLOW_INSECURE_ENDPOINT=true

Bước 4: websift serve
         → MCP server chạy tại http://127.0.0.1:8787/mcp
         → web_fetch có thể escalate browser khi cần

Bước 5: CLI / AI client gọi web_fetch("https://example.com")
         → MCP server → WebSearchClient → FetchOrchestrator
         → HTTP fetch → nếu challenge → Browser Service
         → Trả về Markdown
```

</details>

<details>
<summary>Click để mở — Browser service env variables</summary>

| Variable                        | Default       | Mô tả                                            |
| ------------------------------- | ------------- | -------------------------------------------------- |
| `BROWSER_HOST`                | `127.0.0.1` | Bind address                                       |
| `BROWSER_PORT`                | `8790`      | Listen port                                        |
| `BROWSER_TOKEN`               | (empty)       | Bearer token (bắt buộc khi host không loopback) |
| `BROWSER_CONCURRENCY`         | `2`         | Số request render đồng thời                    |
| `BROWSER_ALLOWED_PORTS`       | `80,443`    | Ports browser được phép kết nối              |
| `BROWSER_ALLOW_HTTP`          | `true`      | Cho phép HTTP (không chỉ HTTPS)                 |
| `BROWSER_ALLOWED_DOMAINS`     | (empty)       | Domain allowlist (rỗng = mọi domain)             |
| `BROWSER_DENIED_DOMAINS`      | (empty)       | Domain denylist                                    |
| `BROWSER_MAX_TIMEOUT_SECONDS` | `45`        | Timeout tối đa mỗi request                      |
| `BROWSER_MAX_HTML_BYTES`      | `5000000`   | Max HTML bytes trả về                            |

</details>

<details>
<summary>Click để mở — Debug browser service</summary>

```bash
# Xem log browser
docker compose logs -f browser

# Kiểm tra health
curl http://localhost:8790/healthz

# Kiểm tra browser service trong container
docker exec web-search-built-in-browser-1 python -c "
from camoufox.async_api import AsyncCamoufox
import asyncio
async def test():
    m = AsyncCamoufox(headless=True)
    b = await m.__aenter__()
    c = await b.new_context()
    p = await c.new_page()
    await p.goto('https://example.com')
    print(await p.title())
    await p.close()
    await c.close()
    await m.__aexit__(None, None, None)
asyncio.run(test())
"
```

</details>

---

## Kết hợp Python + Docker + MCP

<details>
<summary>Click để mở — Setup đầy đủ từ con số 0</summary>

Đây là hướng dẫn **toàn bộ** từ khi chưa có gì, đến khi có MCP + Browser chạy hoàn chỉnh.

### Phần 1: Chuẩn bị hệ thống

```bash
# 1. Kiểm tra Python (cần >= 3.10)
python --version

# 2. Kiểm tra Docker (cần Docker + Docker Compose)
docker --version
docker compose version

# 3. Kiểm tra Docker chạy được
docker run --rm hello-world
```

### Phần 2: Clone repo

```bash
git clone <repo-url>
cd web-search-built-in
```

### Phần 3: Cài đặt Python virtualenv

```bash
# Tạo virtualenv
python -m venv .venv

# Activate
source .venv/bin/activate

# Cài WebSift + MCP + browser client
pip install 'websift[mcp-browser]'
```

### Phần 4: Chạy Browser Service (Docker)

```bash
# Build và chạy browser service
docker compose --profile browser up -d --build

# Kiểm tra cả 2 service chạy
docker compose ps
# websift   → MCP server tại http://localhost:8787/mcp
# browser   → Browser service internal
```

### Phần 5: Cấu hình env cho host Python

Nếu bạn dùng WebSift Python trên host (không trong Docker):

```bash
# Thêm vào ~/.bashrc hoặc ~/.zshrc để tự động load:
export BROWSER_ENDPOINT=http://127.0.0.1:8790
export BROWSER_TOKEN=websift-dev-token
export BROWSER_ALLOW_INSECURE_ENDPOINT=true
```

### Phần 6: Kiểm tra toàn bộ

```bash
# 1. Kiểm tra version
websift --version  # 2.0.0

# 2. Kiểm tra cài đặt
websift doctor

# 3. Test tìm kiếm
websift search "Python 3.12"

# 4. Test fetch HTTP
websift fetch https://example.com

# 5. Test fetch browser
websift fetch --backend browser https://example.com

# 6. Test MCP
curl -s http://localhost:8787/healthz

# 7. Test Python library
python -c "
from websift import WebSearchClient
client = WebSearchClient(fetch_backend='auto')
print(client.fetch('https://example.com'))
"
```

### Phần 7: Thêm MCP vào AI Client

Sau khi MCP server chạy tại `http://localhost:8787/mcp`, thêm vào:

**VS Code:** Tạo `.vscode/mcp.json`:

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

**Claude Code:**

```bash
claude mcp add --transport http web-search http://localhost:8787/mcp
```

**Cursor:** Tạo `~/.cursor/mcp.json`:

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

</details>

<details>
<summary>Click để mở — Ma trận cài đặt</summary>

| Use Case                    | pip install              | Docker?       | BROWSER_ENDPOINT?        |
| --------------------------- | ------------------------ | ------------- | ------------------------ |
| Chỉ Python library         | `websift`              | Không        | Không                   |
| Python + MCP                | `websift[mcp]`         | Không        | Không                   |
| Python + MCP + Browser      | `websift[mcp-browser]` | **Có** | **Có**            |
| Chỉ Docker (MCP + Browser) | Không cần              | **Có** | Tự động trong Compose |
| CLI + Browser               | `websift[browser]`     | **Có** | **Có**            |

</details>

</details>

---

## Fetch Backend Modes

<details>
<summary>Click để mở — 3 chế độ fetch</summary>

### Chế độ

| Chế độ              | Luồng hoạt động                            | Browser?                                |
| ---------------------- | ---------------------------------------------- | --------------------------------------- |
| `auto` (mặc định) | native provider → HTTP → browser (nếu cần) | Chỉ khi phát hiện challenge/JS-shell |
| `http`               | HTTP fetch only                                | Không bao giờ                         |
| `browser`            | Browser render trực tiếp                     | Luôn                                   |

### Diagram luồng `auto` mode

```
fetch("https://example.com")
    │
    ▼
┌──────────────────┐
│ Native Provider  │ ← Tavily/Exa native extract (nếu có key)
└────────┬─────────┘
         │ success: trả về
         │ fail transient: tiếp tục
         ▼
┌──────────────────┐
│ HTTP Backend     │ ← urllib SSRF-safe fetch
└────────┬─────────┘
         │ success bình thường: trả về
         │ có bằng chứng challenge → tiếp tục
         ▼
┌──────────────────┐
│ Detector         │ ← Kiểm tra raw HTML
│ (challenge/JS)   │   + HTTP status
└────────┬─────────┘
         │ có bằng chứng challenge → tiếp tục
         │ không có: trả về HTTP result
         ▼
┌──────────────────┐
│ Browser Backend  │ ← Camoufox render
└──────────────────┘
```

### Khi nào detector escalate browser?

| Điều kiện                                            | Escalate?     |
| ------------------------------------------------------- | ------------- |
| HTTP 200 + challenge marker (`cf-chl-`, `__cf_chl`) | **Có** |
| HTTP 403 + challenge marker                             | **Có** |
| HTTP 200 + JS shell (không có content)                | **Có** |
| HTTP 200 bình thường                                 | Không        |
| HTTP 401/404/407/429                                    | Không        |
| HTTP timeout/network                                    | Không        |
| PDF/binary                                              | Không        |

### Cấu hình backend

```python
# Qua constructor
client = WebSearchClient(fetch_backend="auto")   # mặc định
client = WebSearchClient(fetch_backend="http")   # chỉ HTTP
client = WebSearchClient(fetch_backend="browser") # luôn browser

# Qua env
export FETCH_BACKEND=auto  # hoặc http, browser

# Qua CLI
websift fetch https://example.com --backend http
websift fetch https://example.com --backend browser
```

</details>

---

## Cấu hình chi tiết

<details>
<summary>Click để mở — Environment variables đầy đủ</summary>

### MCP Server

| Variable             | Default             | Mô tả                                 |
| -------------------- | ------------------- | --------------------------------------- |
| `MCP_HOST`         | `127.0.0.1`       | Bind address                            |
| `MCP_PORT`         | `8787`            | Listen port                             |
| `MCP_TRANSPORT`    | `streamable-http` | `streamable-http`, `sse`, `stdio` |
| `MCP_AUTH_MODE`    | `none`            | `none` hoặc `bearer`               |
| `MCP_BEARER_TOKEN` | (empty)             | Shared secret khi`bearer`             |

### Search

| Variable                      | Default  | Mô tả                |
| ----------------------------- | -------- | ---------------------- |
| `SEARCH_PROVIDER`           | `ddgs` | Provider name          |
| `SEARCH_MAX_RESULTS`        | `5`    | Max kết quả          |
| `SEARCH_TIMEOUT_SECONDS`    | `30`   | Timeout search (giây) |
| `SEARCH_FALLBACK_PROVIDERS` | (empty)  | Fallback chain         |

### Fetch

| Variable                  | Default    | Mô tả                         |
| ------------------------- | ---------- | ------------------------------- |
| `FETCH_BACKEND`         | `auto`   | `auto`, `http`, `browser` |
| `FETCH_TIMEOUT_SECONDS` | `30`     | Timeout fetch (giây)           |
| `PAGE_MAX_CHARS`        | `128000` | Max ký tự output              |

### Browser (WebSift client)

| Variable                            | Default     | Mô tả                     |
| ----------------------------------- | ----------- | --------------------------- |
| `BROWSER_ENDPOINT`                | (empty)     | Browser service URL         |
| `BROWSER_TOKEN`                   | (empty)     | Bearer token auth           |
| `BROWSER_ALLOW_INSECURE_ENDPOINT` | `false`   | Cho phép HTTP endpoint     |
| `BROWSER_TIMEOUT_SECONDS`         | `45`      | Timeout render              |
| `BROWSER_POST_LOAD_WAIT_MS`       | `500`     | Chờ thêm sau network idle |
| `BROWSER_MAX_HTML_BYTES`          | `5000000` | Max HTML bytes              |
| `BROWSER_MAX_CONCURRENCY`         | `4`       | Max concurrent requests     |

### Browser (service)

| Variable                  | Default       | Mô tả                                            |
| ------------------------- | ------------- | -------------------------------------------------- |
| `BROWSER_HOST`          | `127.0.0.1` | Bind address                                       |
| `BROWSER_PORT`          | `8790`      | Listen port                                        |
| `BROWSER_TOKEN`         | (empty)       | Bearer token (bắt buộc khi host không loopback) |
| `BROWSER_CONCURRENCY`   | `2`         | Concurrent render slots                            |
| `BROWSER_ALLOWED_PORTS` | `80,443`    | Ports được phép                                |
| `BROWSER_ALLOW_HTTP`    | `true`      | Cho phép HTTP                                     |

### Cache

| Variable                     | Default    | Mô tả                   |
| ---------------------------- | ---------- | ------------------------- |
| `CACHE_ENABLED`            | `false`  | Bật cache                |
| `CACHE_BACKEND`            | `memory` | `memory` hoặc `disk` |
| `CACHE_DIR`                | (empty)    | Disk cache directory      |
| `SEARCH_CACHE_TTL_SECONDS` | `300`    | Search TTL                |
| `FETCH_CACHE_TTL_SECONDS`  | `600`    | Fetch TTL                 |

</details>

---

## Providers

<details>
<summary>Click để mở — Provider matrix</summary>

| Provider                     | Extra | Credentials          | Native Fetch  | Ghi chú               |
| ---------------------------- | ----- | -------------------- | ------------- | ---------------------- |
| **ddgs** (mặc định) | base  | Không               | Không        | DuckDuckGo miễn phí  |
| **searxng**            | base  | `SEARXNG_BASE_URL` | Không        | Self-hosted            |
| **brave**              | base  | `BRAVE_API_KEY`    | Không        | Brave Search API       |
| **tavily**             | base  | `TAVILY_API_KEY`   | **Có** | `/extract` endpoint  |
| **exa**                | base  | `EXA_API_KEY`      | **Có** | `/contents` endpoint |
| **serper**             | base  | `SERPER_API_KEY`   | Không        | Google SERP            |

Cấu hình Brave:

```bash
export SEARCH_PROVIDER=brave
export BRAVE_API_KEY=your-key
```

Cấu hình Tavily (với native extract):

```bash
export SEARCH_PROVIDER=tavily
export TAVILY_API_KEY=your-key
# PROVIDER_NATIVE_FETCH=true (mặc định)
```

Fallback chain:

```bash
export SEARCH_PROVIDER=brave
export BRAVE_API_KEY=...
export SEARCH_FALLBACK_PROVIDERS=ddgs
```

</details>

---

## Bảo mật

<details>
<summary>Click để mở — SSRF protection</summary>

| Bảo vệ                       | Cách hoạt động                                                               |
| ------------------------------ | -------------------------------------------------------------------------------- |
| **Global-only IP**       | Mọi DNS answer phải là global unicast; private/loopback/link-local bị reject |
| **No URL userinfo**      | `user:pass@host` bị chặn                                                     |
| **DNS Pinning + SNI**    | Pin IP đã validate; TLS SNI khớp host                                         |
| **Redirect re-check**    | Mỗi redirect chạy lại DNS validation (max 5 hops)                             |
| **Binary Detection**     | Hình ảnh, executable, archive bị chặn                                        |
| **Size Limits**          | 4 MB page, 20 MB PDF, 128k chars output                                          |
| **Credential Isolation** | Provider key không kế thừa sang page fetch                                    |

### Browser SSRF

Browser service có egress proxy SSRF-safe:

- Validate tất cả DNS answers
- Pin IP cho connection
- Block private/link-local/metadata destinations
- Route interception cho mọi subresource (iframe, script, XHR, WebSocket)
- Context cô lập: mỗi request = context + page mới, không chia cookie

</details>

---

## Kết nối MCP với AI Client

<details>
<summary>Click để mở — VS Code (GitHub Copilot)</summary>

### Tạo `.vscode/mcp.json`

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

### Hoặc user-level

1. Command Palette → `MCP: Open User Configuration`
2. Thêm entry tương tự

### Kiểm tra

Mở Chat (`Ctrl+Cmd+I`) và hỏi: *"Tìm kiếm thông tin Python mới nhất"*

</details>

<details>
<summary>Click để mở — Claude Code</summary>

```bash
# Thêm MCP server
claude mcp add --transport http web-search http://localhost:8787/mcp

# Kiểm tra
claude mcp list

# Sử dụng
claude "Tìm kiếm và tóm tắt thông tin Python 3.12"
```

### Scope

```bash
# Project scope (mặc định)
claude mcp add --transport http web-search http://localhost:8787/mcp

# User scope (toàn cục)
claude mcp add --transport http web-search --scope user http://localhost:8787/mcp
```

</details>

<details>
<summary>Click để mở — Cursor</summary>

Tạo `~/.cursor/mcp.json`:

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

</details>

<details>
<summary>Click để mở — Claude Desktop</summary>

Edit `~/.config/claude/claude_desktop_config.json` (Linux):

```json
{
  "mcpServers": {
    "web-search": {
      "url": "http://localhost:8787/mcp"
    }
  }
}
```

</details>

<details>
<summary>Click để mở — Windsurf (Codeium)</summary>

Tạo `~/.codeium/windsurf/mcp_config.json`:

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

</details>

<details>
<summary>Click để mở — JetBrains IDEs</summary>

1. Cài plugin "MCP Client" từ JetBrains Marketplace
2. **Settings → Tools → MCP**
3. Thêm server: Name `web-search`, Type `HTTP`, URL `http://localhost:8787/mcp`
4. Apply và restart

</details>

---

## Docker Compose Deployment

<details>
<summary>Click để mở — Docker Compose cơ bản</summary>

```bash
# Chạy MCP server (không browser)
docker compose up -d --build

# Kiểm tra
curl http://localhost:8787/healthz
```

</details>

<details>
<summary>Click để mở — Docker Compose + Browser</summary>

```bash
# Chạy cả MCP + Browser
docker compose --profile browser up -d --build

# Kiểm tra
docker compose ps
# websift   → MCP server tại http://localhost:8787/mcp
# browser   → Browser service

# Test browser
curl http://localhost:8790/healthz
```

</details>

<details>
<summary>Click để mở — Production deployment</summary>

```bash
# Với bearer auth
MCP_AUTH_MODE=bearer \
MCP_BEARER_TOKEN='your-secret' \
docker compose --profile browser up -d --build
```

### Checklist

- [ ] Dùng bearer auth (`MCP_AUTH_MODE=bearer`)
- [ ] Bind loopback hoặc qua reverse proxy
- [ ] Resource limits (memory, CPU, PID)
- [ ] Firewall rules cho published ports
- [ ] Monitoring và log rotation

</details>

---

## FAQ

<details>
<summary>Click để mở — Cần API key không?</summary>

**Không với DDGS mặc định.** Provider Brave/Tavily/Exa/Serper cần key qua env server. Key không bao giờ nhận qua MCP tool arguments.

</details>

<details>
<summary>Click để mở — `pip install` có chạy được browser không?</summary>

**Không.** `pip install 'websift[browser]'` chỉ cài httpx client nhẹ. Browser runtime (Camoufox + Playwright + Firefox) **chạy trong Docker container**. WebSift connect tới browser qua HTTP.

```
pip install 'websift[browser]'  →  chỉ cài httpx
├── KHÔNG cài Camoufox
├── KHÔNG cài Playwright
├── KHÔNG cài Firefox binary
└── KHÔNG spawn browser process

→ Cần Docker cho browser runtime
→ WebSift connect tới browser qua HTTP protocol
```

</details>

<details>
<summary>Click để mở — Browser backend giải CAPTCHA không?</summary>

**Không.** Browser render JavaScript và có thể cải thiện kết quả cho một số trang challenge, nhưng:

- Không giải CAPTCHA
- Không đảm bảo vượt Cloudflare/DataDome/anti-bot
- Best effort only

</details>

<details>
<summary>Click để mở — Có thể dùng như thư viện Python không?</summary>

**Có!**

```python
from websift import WebSearchClient

client = WebSearchClient()
client.search("từ khóa")
client.fetch("https://example.com")
```

Không cần server, không cần Docker, không cần MCP.

</details>

<details>
<summary>Click để mở — Debug và troubleshooting</summary>

### Doctor

```bash
websift doctor
```

### Debug log

```bash
websift serve --log-level DEBUG
```

### Common issues

| Issue                         | Giải pháp                                                 |
| ----------------------------- | ----------------------------------------------------------- |
| `ImportError: mcp`          | `pip install 'websift[mcp]'`                              |
| `ImportError: httpx`        | `pip install 'websift[browser]'`                          |
| Browser connection failed     | Kiểm tra`BROWSER_ENDPOINT` và browser service           |
| `BROWSER_TOKEN is required` | Set`export BROWSER_TOKEN=your-token`                      |
| Rate limited                  | Tăng`SEARCH_RETRY_BACKOFF_SECONDS`                       |
| Timeout                       | Tăng`SEARCH_TIMEOUT_SECONDS` / `FETCH_TIMEOUT_SECONDS` |

</details>

---

## Tài nguyên

- [README tiếng Anh](../README.md)
- [README tiếng Việt](./README.vi.md)
- [CHANGELOG](../CHANGELOG.md)
- [LICENSE](../LICENSE)
- [Browser service](../services/browser/)
- [Tests](../tests/)
