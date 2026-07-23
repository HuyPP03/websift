# websift — Tài liệu tiếng Việt

Thư viện Python nhẹ và MCP server miễn phí, tự host cho truy cập web thời gian thực — tìm kiếm DuckDuckGo + lấy nội dung trang (HTML → Markdown, PDF → text) — với bảo vệ SSRF và DNS pinning. **Không cần API key** cho provider mặc định.

```python
from websift import WebSearchClient

print(WebSearchClient().search("python asyncio"))
```

Dùng import trực tiếp khi chỉ cần search/fetch trong process; chạy `websift serve` khi cần tool MCP cho AI client.

---

## Mục lục

- [websift — Tài liệu tiếng Việt](#websift--tài-liệu-tiếng-việt)
  - [Mục lục](#mục-lục)
  - [websift là gì?](#websift-là-gì)
  - [Tại sao nên dùng websift?](#tại-sao-nên-dùng-websift)
    - [Điểm mạnh cốt lõi](#điểm-mạnh-cốt-lõi)
    - [Phù hợp cho những ai?](#phù-hợp-cho-những-ai)
  - [So sánh với các dịch vụ khác](#so-sánh-với-các-dịch-vụ-khác)
    - [Bảng so sánh chi tiết](#bảng-so-sánh-chi-tiết)
    - [Khi nào nên chọn cái gì?](#khi-nào-nên-chọn-cái-gì)
  - [Kiến trúc](#kiến-trúc)
    - [Sơ đồ hoạt động](#sơ-đồ-hoạt-động)
    - [Cấu trúc module](#cấu-trúc-module)
  - [Cài đặt](#cài-đặt)
    - [Tùy chọn 1: PyPI (Khuyến nghị)](#tùy-chọn-1-pypi-khuyến-ngị)
    - [Tùy chọn 2: Docker Compose](#tùy-chọn-2-docker-compose)
    - [Tùy chọn 3: Docker (Thủ công)](#tùy-chọn-3-docker-thủ-công)
    - [Tùy chọn 4: Python trực tiếp (Không cần Docker)](#tùy-chọn-4-python-trực-tiếp-không-cần-docker)
  - [Sử dụng](#sử-dụng)
    - [CLI](#cli)
    - [Như một thư viện Python (Import trực tiếp)](#như-một-thư-viện-python-import-trực-tiếp)
    - [Như một MCP Server (Cho AI Clients)](#như-một-mcp-server-cho-ai-clients)
  - [Các công cụ (Tools)](#các-công-cụ-tools)
    - [`web_search(query: str) → str`](#web_searchquery-str--str)
    - [`web_fetch(url: str) → str`](#web_fetchurl-str--str)
  - [Cấu hình](#cấu-hình)
    - [Biến môi trường](#biến-môi-trường)
    - [Giới hạn nội bộ](#giới-hạn-nội-bộ)
  - [Kết nối với các AI Client](#kết-nối-với-các-ai-client)
    - [1. VS Code (GitHub Copilot)](#1-vs-code-github-copilot)
    - [2. Claude Desktop](#2-claude-desktop)
    - [3. Claude Code](#3-claude-code)
    - [4. Copilot CLI](#4-copilot-cli)
    - [5. Cursor](#5-cursor)
    - [6. Windsurf (Codeium)](#6-windsurf-codeium)
    - [7. JetBrains IDEs](#7-jetbrains-ides)
    - [8. MCP Client tổng quát](#8-mcp-client-tổng-quát)
  - [Trường hợp sử dụng](#trường-hợp-sử-dụng)
    - [Nghiên cứu web cho AI Agent](#nghiên-cứu-web-cho-ai-agent)
    - [Tra cứu tài liệu](#tra-cứu-tài-liệu)
    - [Gỡ lỗi (Debugging)](#gỡ-lỗi-debugging)
    - [Phân tích cạnh tranh](#phân-tích-cạnh-tranh)
    - [Tại sao phù hợp cho Agentic AI?](#tại-sao-phù-hợp-cho-agentic-ai)
  - [Bảo mật](#bảo-mật)
    - [Cơ chế bảo vệ tích hợp](#cơ-chế-bảo-vệ-tích-hợp)
    - [Lưu ý về mạng](#lưu-ý-về-mạng)
  - [Phát triển](#phát-triển)
    - [Cấu trúc dự án](#cấu-trúc-dự-án)
    - [Chạy local](#chạy-local)
    - [Chạy với Docker](#chạy-với-docker)
  - [Câu hỏi thường gặp (FAQ)](#câu-hỏi-thường-gặp-faq)
  - [Giấy phép](#giấy-phép)
  - [Lời cảm ơn](#loi-cam-on)

---

## websift là gì?

Đây là một **MCP Server** (Model Context Protocol Server) — một server nhẹ viết bằng Python, cung cấp 2 công cụ cho AI agents:

| Công cụ      | Đầu vào                    | Đầu ra                                                                        |
| -------------- | ----------------------------- | ------------------------------------------------------------------------------- |
| `web_search` | `query` (chuỗi tìm kiếm) | Tiêu đề, URL, và đoạn mô tả ngắn từ DuckDuckGo                        |
| `web_fetch`  | `url` (địa chỉ web)      | Nội dung văn bản đọc được từ trang web (HTML → Markdown, PDF → text) |

MCP (Model Context Protocol) là giao thức chuẩn để kết nối AI agents với các công cụ bên ngoài. Server này cho phép bất kỳ AI client nào (Copilot, Claude, Cursor, Windsurf, v.v.) gọi tìm kiếm web và lấy nội dung trang web mà không cần tích hợp phức tạp.

---

## Tại sao nên dùng websift?

### Điểm mạnh cốt lõi

- **🐍 Dùng như thư viện Python** — `pip install websift` rồi import trực tiếp vào code. Không cần server, không cần Docker, không cần MCP.
- **🆓 Miễn phí (mặc định)** — Provider **DDGS** mặc định không cần API key hay đăng ký. DuckDuckGo và các site đích vẫn có thể throttle/block.
- **🪶 Siêu nhẹ** — Chỉ một tiến trình Python, ~4 thư viện phụ thuộc, chạy trong container Docker nhỏ (`python:3.12-slim` ≈ 150 MB).
- **🔒 Bảo mật mặc định** — Chống SSRF (global-only IP, multi-answer DNS, không userinfo), DNS pinning + SNI, re-validate redirect, giới hạn body/decompress, kiểm tra content-type.
- **🌐 Tương thích mọi MCP Client** — Hoạt động với bất kỳ client MCP nào: VS Code, Claude Desktop, Claude Code, Cursor, Windsurf, JetBrains, và các agent tùy chỉnh.
- **📄 Trích xuất thông minh** — HTML → Markdown qua BeautifulSoup (main-content), PDF → text **chỉ pypdf**, phát hiện file nhị phân, charset BOM → HTTP → meta → UTF-8.
- **🐙 Lối tắt GitHub README** — Fetch `github.com/owner/repo` dùng GitHub API (header không credential).
- **🏠 Tự chủ (Self-hosted)** — Bạn tự chạy process; vẫn có **request ra ngoài** tới search provider và URL fetch.

### Phù hợp cho những ai?

- **🤖 AI Agents & Agentic Workflows** — Cho phép agent tự động tìm kiếm web và đọc trang web theo yêu cầu. Đây là trường hợp sử dụng mạnh nhất của server này.
- **� Script & Ứng dụng Python** — Import `WebSearchClient` trực tiếp vào code của bạn. Không cần server, không cần Docker, không cần MCP.
- **�💻 Trợ lý phát triển** — Để Copilot, Claude, hoặc Cursor tra cứu tài liệu, thông báo lỗi, hoặc thông tin package theo thời gian thực.
- **📊 Nghiên cứu & phân tích** — Lấy và tóm tắt bài viết, bài báo, hoặc trang tài liệu.
- **💰 Triển khai tiết kiệm chi phí** — Thay thế các API tìm kiếm web trả phí (Tavily, Firecrawl, Exa, v.v.) bằng giải pháp tự chủ miễn phí.
- **🔐 Mạng riêng / Air-gapped** — Chạy hoàn toàn trên cơ sở hạ tầng của bạn (tìm kiếm cần internet, nhưng fetch có thể hoạt động với URL nội bộ nếu bạn điều chỉnh quy tắc bảo mật).

---

## So sánh với các dịch vụ khác

### Bảng so sánh chi tiết

| Tính năng                       | **websift**   | Tavily MCP                               | Firecrawl MCP                            | Exa MCP                                  | Brave Search MCP                         |
| --------------------------------- | -------------------------- | ---------------------------------------- | ---------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| **Giá**                    | ✅ Miễn phí              | 💰 Trả phí (có gói free hạn chế)   | 💰 Trả phí                             | 💰 Trả phí                             | 💰 Trả phí (có gói free hạn chế)   |
| **Cần API Key**            | ✅ Không                  | ❌ Có                                   | ❌ Có                                   | ❌ Có                                   | ❌ Có                                   |
| **Tự chủ (Self-hosted)**  | ✅ Có                     | ❌ Không                                | ⚠️ Một phần                          | ❌ Không                                | ❌ Không                                |
| **Tìm kiếm web**          | ✅ DuckDuckGo              | ✅ Độc quyền                          | ❌ (chỉ scrape)                         | ✅ Độc quyền                          | ✅ Brave                                 |
| **Lấy nội dung web**      | ✅ HTML + PDF              | ✅ Có                                   | ✅ Có (sâu)                            | ✅ Có                                   | ❌ Không                                |
| **Chống SSRF**             | ✅ Tích hợp              | ⚠️ Nhà cung cấp quản lý            | ⚠️ Nhà cung cấp quản lý            | ⚠️ Nhà cung cấp quản lý            | ⚠️ Nhà cung cấp quản lý            |
| **Kích thước container** | ~150 MB                    | N/A (SaaS)                               | ~500 MB+                                 | N/A (SaaS)                               | N/A (SaaS)                               |
| **Thư viện phụ thuộc**  | 4 gói                     | N/A                                      | Nhiều                                   | N/A                                      | N/A                                      |
| **Giới hạn tốc độ**    | Upstream DDGS / site đích | Giới hạn nhà cung cấp                | Giới hạn nhà cung cấp                | Giới hạn nhà cung cấp                | Giới hạn nhà cung cấp                |
| **Quyền riêng tư**       | Tự host + outbound       | ⚠️ Dữ liệu gửi đến nhà cung cấp | ⚠️ Dữ liệu gửi đến nhà cung cấp | ⚠️ Dữ liệu gửi đến nhà cung cấp | ⚠️ Dữ liệu gửi đến nhà cung cấp |

### Khi nào nên chọn cái gì?

| Tình huống                                                                     | Khuyến nghị               |
| -------------------------------------------------------------------------------- | --------------------------- |
| Muốn truy cập web**miễn phí, không đăng ký** cho AI                | **websift** ✅ |
| Cần**scrape sâu** (trang render JS, sitemap)                             | Firecrawl                   |
| Cần**tìm kiếm ngữ nghĩa** (AI-powered relevance)                      | Exa                         |
| Muốn tìm kiếm**tối ưu cho agent** (chế độ `extract` của Tavily) | Tavily                      |
| Muốn**tự host** (vẫn có outbound search/fetch)                   | **websift** ✅ |
| Đang xây dựng **AI agent tùy chỉnh** với hạ tầng tối thiểu      | **websift** ✅ |

---

## Kiến trúc

### Sơ đồ hoạt động

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

Luồng ra ngoài: **search** → provider (mặc định DuckDuckGo qua `ddgs`); **fetch** → URL đích / GitHub API cho README. Secret provider không bao giờ đi theo page-fetch.

### Cấu trúc module

```
websift/
├── __init__.py       # WebSearchClient, AppSettings, __version__
├── __main__.py       # python -m websift
├── cli.py            # argparse CLI (serve / search / fetch)
├── settings.py       # AppSettings.from_env() — không đọc env khi import
├── concurrency.py    # WorkLimits (search/fetch/PDF)
├── models.py         # SearchResponse / FetchResult nội bộ
├── config.py         # giới hạn kích thước, user-agent, MIME
├── security.py       # SSRF: global-only IP, multi-answer DNS, không userinfo
├── content.py        # phát hiện loại nội dung (PDF, nhị phân, HTML)
├── http.py           # page fetch: redirect, DNS pin + SNI, body/decompress caps
├── html.py           # HTML → Markdown, main content, truncate
├── client.py         # façade search/fetch công khai
├── provider_http.py  # transport credential cho provider (tách page fetch)
├── providers/        # contract SearchProvider, registry, adapter DDGS + khác
└── server.py         # create_server / ServerApp
server.py             # entry mỏng → websift.cli:main
```

---

## Cài đặt

### Tùy chọn 1: PyPI (Khuyến nghị)

```bash
pip install websift
# MCP server: pip install 'websift[mcp]'
```

Vậy là xong — bạn có thể dùng như **thư viện Python** (import trực tiếp) hoặc như **MCP server** (cho AI clients).

### Tùy chọn 2: Docker Compose

```bash
# Clone và khởi động (không bắt buộc file .env)
git clone <repo-url>
cd websift
docker compose up -d --build
```

MCP server sẽ có sẵn tại `http://localhost:8787/mcp`.

- Chạy non-root (`uid 10001`), entrypoint `websift` từ wheel đã cài.
- Inject secret lúc runtime: `MCP_BEARER_TOKEN=... BRAVE_API_KEY=... docker compose up -d` hoặc `docker compose --env-file .env up -d`.
- Image bind `0.0.0.0` **trong** network namespace của container; bảo vệ bằng firewall/proxy host và/hoặc `MCP_AUTH_MODE=bearer`.

### Tùy chọn 3: Docker (Thủ công)

```bash
docker build -t websift .
docker run -d --name websift -p 8787:8787 \
  -e MCP_AUTH_MODE=none \
  websift
```

### Tùy chọn 4: Python trực tiếp (Không cần Docker)

```bash
# Khuyến nghị: cài package (editable khi dev)
pip install -e ".[dev]"

# Hoặc chỉ runtime deps (mirror pyproject.toml)
pip install -r requirements.txt
pip install -e .

# Chạy server
websift serve
# websift                 # tương đương serve khi không có command
# python -m websift serve
# python server.py serve
```

---

## Sử dụng

### CLI

Sau `pip install websift`, lệnh `websift` hỗ trợ help, version và các subcommand:

```bash
websift --help
websift --version

# Khởi động MCP server (mặc định khi không có command)
websift
websift serve
websift serve --host 0.0.0.0 --port 9000 --transport streamable-http
websift serve --auth-mode bearer --bearer-token 'a-long-random-secret'
websift serve --provider ddgs --max-results 8 --log-level DEBUG

# Lệnh one-shot (không cần MCP server)
websift search "tính năng Python 3.12"
websift search "asyncio tutorial" -n 10 --provider ddgs
websift search "python" --json          # JSON có cấu trúc cho script
websift fetch https://docs.python.org/3/
websift fetch https://example.com/doc.pdf --max-chars 20000
websift fetch https://example.com --json
```

| Lệnh | Mục đích |
| ---- | -------- |
| `websift` / `websift serve` | Chạy MCP server |
| `websift search QUERY` | In kết quả tìm kiếm ra stdout |
| `websift search QUERY --json` | JSON: `ok` / `results` / `error` (exit `1` nếu lỗi) |
| `websift fetch URL` | In nội dung trang/PDF ra stdout |
| `websift fetch URL --json` | JSON: `ok` / `content` / `error` (exit `1` nếu lỗi) |
| `websift --version` / `-V` | In version package |
| `websift --help` / `-h` | Hiện help |

Cờ CLI ghi đè biến môi trường tương ứng cho process hiện tại. Ma trận env đầy đủ nằm ở [Cấu hình](#cấu-hình).

### Đổi tên import (`web_search` → `websift`)

Từ **1.0.0**, import path là `websift` (không còn `web_search`). MCP tools vẫn là `web_search` / `web_fetch`.

### Như một thư viện Python (Import trực tiếp)

Dùng `WebSearchClient` trực tiếp trong code Python — **không cần chạy server**:

```python
from websift import WebSearchClient

client = WebSearchClient()

# Tìm kiếm web (DuckDuckGo mặc định)
results = client.search("tính năng mới Python 3.12")
print(results)

# Lấy nội dung trang web (HTML → Markdown, PDF → text)
content = client.fetch("https://docs.python.org/3/")
print(content)

# Async (chạy sync search/fetch trên worker thread)
# results = await client.asearch("tính năng Python 3.12")
# content = await client.afetch("https://docs.python.org/3/")
```

#### Tùy biến `WebSearchClient`

Truyền kwargs vào constructor — không cần sửa env khi dùng như thư viện:

```python
from websift import WebSearchClient, AppSettings
from websift.settings import ProviderSettings, ExtractionSettings, FetchSettings

# Tinh chỉnh đơn giản
client = WebSearchClient(
    max_results=10,
    timeout=20,              # timeout chung search+fetch (legacy)
    max_page_chars=50_000,
)

# Timeout tách rời + tên provider + cờ extraction
client = WebSearchClient(
    max_results=8,
    search_timeout=15,
    fetch_timeout=45,
    max_page_chars=64_000,
    provider="ddgs",           # hoặc "brave" / "tavily" / "exa" / "searxng"
    include_links=True,
    include_images=False,
    output_format="markdown",  # hoặc "text"
    native_fetch=True,         # Tavily/Exa extract trả phí khi có key
)

# Provider có key (key chỉ nằm trong process — không bao giờ nhận qua MCP tool)
client = WebSearchClient(
    provider="brave",
    api_key="BSA...",
    # base_url="https://api.search.brave.com",  # ghi đè tùy chọn
    fallback_providers=["ddgs"],
    max_results=5,
)

# Cây settings đầy đủ (hoặc AppSettings.from_env())
settings = AppSettings(
    provider=ProviderSettings(name="ddgs", max_results=10, timeout_seconds=20),
    fetch=FetchSettings(timeout_seconds=45),
    extraction=ExtractionSettings(max_page_chars=50_000, include_links=True),
)
client = WebSearchClient(settings=settings)

# Hoặc load từ env
client = WebSearchClient(settings=AppSettings.from_env())
```

| Kwarg | Kiểu | Mô tả |
| ----- | ---- | ----- |
| `max_results` | `int` | Số kết quả tìm kiếm tối đa (mặc định `5`) |
| `timeout` | `int` | Timeout search+fetch chung (giây) khi không set riêng (mặc định `30`) |
| `search_timeout` | `float` | Timeout chỉ cho search |
| `fetch_timeout` | `float` | Timeout chỉ cho fetch |
| `max_page_chars` | `int` | Số ký tự tối đa trả về từ fetch |
| `provider` | `str` hoặc `SearchProvider` | Tên provider (`ddgs`, `brave`, …) hoặc instance |
| `api_key` / `base_url` | `str` | Credential/endpoint cho provider có key hoặc self-hosted |
| `fallback_providers` | sequence `str` | Chuỗi fallback sau provider chính |
| `safe_search` / `region` / `time_range` | `str` | Bộ lọc tìm kiếm tùy chọn |
| `include_links` / `include_images` | `bool` | Tùy chọn trích xuất HTML |
| `output_format` | `str` | `markdown` hoặc `text` |
| `native_fetch` | `bool` | Cho phép Tavily/Exa native extract khi fetch |
| `settings` | `AppSettings` | Cây cấu hình đầy đủ (kwargs nâng cao vẫn overlay khi set) |

**Phù hợp cho:**

- Script tùy chỉnh & tự động hóa
- Nhúng vào ứng dụng của riêng bạn
- Data pipeline & ETL workflow
- Testing & prototyping

### Như một MCP Server (Cho AI Clients)

Chạy server để expose tools cho bất kỳ AI client MCP nào:

```bash
# Khởi động server (mặc định: 127.0.0.1:8787, streamable-http)
websift serve

# Bind / transport tùy chỉnh qua CLI (ghi đè env cho process này)
websift serve --host 0.0.0.0 --port 9000 --transport sse

# Hoặc qua biến môi trường
MCP_PORT=9000 MCP_TRANSPORT=sse websift serve
```

Hoặc qua Python:

```python
from websift.server import create_server
from websift.settings import AppSettings

create_server(AppSettings.from_env()).run()
# hoặc: from websift.cli import main; main(["serve"])
```

**Phù hợp cho:**

- VS Code (GitHub Copilot)
- Claude Desktop / Claude Code
- Cursor, Windsurf, JetBrains IDEs
- Bất kỳ agent MCP tương thích

---

## Các công cụ (Tools)

### `web_search(query: str) → str`

Tìm kiếm trên DuckDuckGo và trả về kết quả đã định dạng với tiêu đề, URL, và đoạn mô tả ngắn.

**Ví dụ:**

```
Agent: web_search("tính năng mới Python 3.12")
Server:
Title: What's New in Python 3.12
URL: https://docs.python.org/3/whatsnew/3.12.html
Snippet: Python 3.12 introduces several performance improvements...

---

Title: Python 3.12 Release Notes
URL: https://www.python.org/downloads/release/python-3120/
Snippet: The Python 3.12 release includes bug fixes and...
```

### `web_fetch(url: str) → str`

Lấy nội dung từ URL và trả về văn bản đọc được. Xử lý:

- **Trang HTML** → chuyển thành Markdown sạch (BeautifulSoup, trích xuất nội dung chính)
- **Tệp PDF** → trích xuất text **chỉ qua pypdf**
- **Văn bản thuần / JSON / XML** → trả về nguyên vẹn
- **Repo GitHub** → tự động lấy README qua GitHub API
- **Tệp nhị phân** → phát hiện và chặn (hình ảnh, tệp thực thi, archive)

**Ví dụ:**

```
Agent: web_fetch("https://github.com/python/cpython")
Server:
README of https://github.com/python/cpython (via GitHub API):

# Python
The Python programming language...
```

---

## Cấu hình

### Biến môi trường

| Biến                       | Mặc định            | Mô tả                                                                 |
| -------------------------- | ------------------- | ----------------------------------------------------------------------- |
| `MCP_HOST`               | `127.0.0.1`       | Địa chỉ bind (chỉ dùng `0.0.0.0` khi cố ý expose)               |
| `MCP_PORT`               | `8787`            | Cổng lắng nghe                                                         |
| `MCP_TRANSPORT`          | `streamable-http` | Transport: `streamable-http`, `sse`, hoặc `stdio`                 |
| `MCP_AUTH_MODE`          | `none`            | `none` hoặc `bearer` (HTTP/SSE)                                    |
| `MCP_BEARER_TOKEN`       | (rỗng)              | Shared secret khi `MCP_AUTH_MODE=bearer`                             |
| `SEARCH_PROVIDER`        | `ddgs`            | Provider tìm kiếm (allowlist)                                          |
| `SEARCH_MAX_RESULTS`     | `5`               | Số kết quả tìm kiếm tối đa                                        |
| `SEARCH_TIMEOUT_SECONDS` | `30`              | Timeout search (giây)                                                   |
| `FETCH_TIMEOUT_SECONDS`  | `30`              | Timeout fetch trang (giây)                                              |
| `SEARCH_TIMEOUT`         | (alias)             | **Deprecated**: nếu set và thiếu timeout cụ thể thì map cả hai |
| `SEARCH_FALLBACK_PROVIDERS` | (rỗng)           | Chuỗi fallback allowlist (không fallback config/auth error)           |
| `SEARCH_RETRY_MAX`       | `1`               | Số lần retry thêm sau lần đầu (DDGS + HTTP providers)               |
| `SEARCH_RETRY_BACKOFF_SECONDS` | `0.5`        | Backoff cơ sở (giây); nhân đôi mỗi lần, có trần                     |
| `PAGE_MAX_CHARS`         | `128000`          | Số ký tự tối đa trả về từ fetch                                 |
| `SEARCH_MAX_CONCURRENCY` | `8`               | Số search đồng thời tối đa                                      |
| `FETCH_MAX_CONCURRENCY`  | `16`              | Số fetch trang đồng thời tối đa                                 |
| `PDF_MAX_CONCURRENCY`    | `2`               | Số parse PDF đồng thời tối đa                                   |
| `CACHE_ENABLED`          | `false`           | Bật cache TTL/LRU trong bộ nhớ cho search/fetch thành công          |
| `SEARCH_CACHE_TTL_SECONDS` | `300`           | TTL cache search khi bật                                              |
| `FETCH_CACHE_TTL_SECONDS`  | `600`           | TTL cache fetch khi bật                                               |
| `CACHE_MAX_ENTRIES`      | `256`             | Số entry cache tối đa                                               |
| `CACHE_MAX_BYTES`        | `33554432`        | Xấp xỉ dung lượng payload cache (byte)                              |

### Provider tìm kiếm

Chỉ cấu hình server-wide (`SEARCH_PROVIDER`). Tool MCP không nhận provider/base URL/API key.

| Provider | Extra | Credential / endpoint | Ghi chú |
| -------- | ----- | --------------------- | ------- |
| **ddgs** (mặc định) | base | không | DuckDuckGo qua `ddgs` |
| **searxng** | `websift[searxng]` | `SEARXNG_BASE_URL` (bắt buộc), `SEARXNG_API_KEY` tùy chọn | Self-hosted; `PROVIDER_ALLOW_HTTP=true` chỉ cho `http://` local |
| **brave** | `websift[brave]` | `BRAVE_API_KEY`, `BRAVE_BASE_URL` tùy chọn | |
| **tavily** | `websift[tavily]` | `TAVILY_API_KEY`, `TAVILY_BASE_URL` tùy chọn | `web_fetch` dùng `/extract` khi `PROVIDER_NATIVE_FETCH=true` |
| **exa** | `websift[exa]` | `EXA_API_KEY`, `EXA_BASE_URL` tùy chọn | |
| **serper**        | `websift[serper]` | `SERPER_API_KEY` (bắt buộc), tùy chọn `SERPER_BASE_URL` | Google SERP qua Serper API |

`pip install 'websift[providers]'` — alias toàn bộ provider HTTP (hiện không thêm wheel ngoài base; adapter dùng stdlib HTTP).

Filter tùy chọn: `SEARCH_SAFE_SEARCH`, `SEARCH_REGION`, `SEARCH_TIME_RANGE`. Fallback opt-in: `SEARCH_FALLBACK_PROVIDERS` (không fallback lỗi config/auth).

`PROVIDER_NATIVE_FETCH=true` (mặc định): Tavily/Exa dùng extract/contents cho `web_fetch` (tốn credit); `false` luôn generic SSRF-safe fetch. Fallback search **không** áp dụng cho fetch.

### Giới hạn nội bộ

| Cài đặt                   | Giá trị | Mô tả                         |
| ---------------------------- | --------- | ------------------------------- |
| Kích thước trang tối đa | 4 MB      | Giới hạn fetch trang thường |
| Kích thước PDF tối đa    | 20 MB     | Giới hạn fetch PDF          |
| Ký tự đầu ra tối đa    | 128,000   | Số ký tự gửi đến LLM      |
| Redirect tối đa            | 5         | Giới hạn chuỗi redirect HTTP |

---

## Kết nối với các AI Client

### 1. VS Code (GitHub Copilot)

> 📖 **Tài liệu chính thức**: [Add and manage MCP servers in VS Code](https://code.visualstudio.com/docs/agent-customization/mcp-servers) | [MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)

#### Qua Extensions View (Dễ nhất)

1. Mở Extensions view (`Ctrl+Shift+X`)
2. Tìm `@mcp` trong ô tìm kiếm
3. Cài đặt MCP server từ gallery

#### Qua `mcp.json` (Server tùy chỉnh)

Tạo `.vscode/mcp.json` trong workspace của bạn:

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

Hoặc để cấu hình toàn cục (cấp người dùng), chạy `MCP: Open User Configuration` từ Command Palette và thêm mục tương tự.

#### Kiểm tra

Mở Chat (`Ctrl+Cmd+I` / `Ctrl+Ctrl+I`) và hỏi: *"Tìm kiếm ghi chú phát hành Python mới nhất"*

### 2. Claude Desktop

> 📖 **Tài liệu chính thức**: [Getting Started with Local MCP Servers on Claude Desktop](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop) | [Desktop Extensions](https://www.anthropic.com/engineering/desktop-extensions)

#### Qua giao diện Cài đặt

1. Mở Claude Desktop → Settings → Extensions
2. Click "Advanced settings" → "Install Extension…"
3. Hoặc thêm thủ công qua tệp cấu hình

#### Qua tệp cấu hình

Sửa `~/.config/claude/claude_desktop_config.json` (Linux) hoặc `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "web-search": {
      "url": "http://localhost:8787/mcp"
    }
  }
}
```

Khởi động lại Claude Desktop sau khi sửa.

### 3. Claude Code

> 📖 **Tài liệu chính thức**: [Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp)

```bash
# Thêm MCP server (transport HTTP)
claude mcp add --transport http web-search http://localhost:8787/mcp

# Kiểm tra kết nối
claude mcp list

# Sử dụng trong hội thoại
claude "Tìm kiếm bản phát hành Rust mới nhất và tóm tắt những thay đổi chính"
```

**Phạm vi (Scopes):**

```bash
# Phạm vi dự án (mặc định, lưu trong .mcp.json)
claude mcp add --transport http web-search http://localhost:8787/mcp

# Phạm vi người dùng (có sẵn trên mọi dự án)
claude mcp add --transport http web-search --scope user http://localhost:8787/mcp
```

### 4. Copilot CLI

> 📖 **Tài liệu chính thức**: [Adding MCP servers for GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)

#### Chế độ tương tác

```
/mcp add
# Server Name: web-search
# Server Type: HTTP
# URL: http://localhost:8787/mcp
# Nhấn Ctrl+S để lưu
```

#### Dòng lệnh

```bash
copilot mcp add web-search --transport http --url http://localhost:8787/mcp
```

#### Tệp cấu hình

Sửa `~/.github/copilot/mcp-config.json`:

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

> 📖 **Tài liệu chính thức**: [Model Context Protocol (MCP) | Cursor Docs](https://cursor.com/docs/mcp)

Tạo `~/.cursor/mcp.json` (toàn cục) hoặc `.cursor/mcp.json` (dự án):

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

Khởi động lại Cursor, sau đó dùng Chat hoặc Agent mode để gọi các công cụ.

### 6. Windsurf (Codeium)

> 📖 **Tài liệu chính thức**: [Cascade MCP Integration](https://docs.windsurf.com/plugins/cascade/mcp)

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

Hoặc dùng giao diện tích hợp: **Settings → Cascade → MCP Servers**.

### 7. JetBrains IDEs

> 📖 **Tài liệu chính thức**: [MCP Server | IntelliJ IDEA Documentation](https://www.jetbrains.com/help/idea/mcp-server.html)

1. Cài plugin "MCP Client" từ JetBrains Marketplace
2. Vào **Settings → Tools → MCP**
3. Thêm server mới:
   - Name: `web-search`
   - Type: `HTTP`
   - URL: `http://localhost:8787/mcp`
4. Apply và khởi động lại

### 8. MCP Client tổng quát

Với bất kỳ client MCP tương thích nào, server có thể truy cập tại:

- **Streamable HTTP** (khuyến nghị): `http://localhost:8787/mcp`
- **SSE**: `http://localhost:8787/mcp/sse` (đặt `MCP_TRANSPORT=sse`)
- **STDIO**: Chạy `python server.py` với `MCP_TRANSPORT=stdio`

Cấu hình HTTP tổng quát:

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

## Trường hợp sử dụng

### Nghiên cứu web cho AI Agent

```
Người dùng: "Tìm benchmark mới nhất cho tối ưu inference LLM"
Agent: web_search("LLM inference optimization benchmarks 2025")
Agent: web_fetch("https://example.com/benchmark-article")
Agent: [Tóm tắt kết quả từ nội dung đã lấy]
```

### Tra cứu tài liệu

```
Người dùng: "Làm thế nào để cấu hình CORS trong FastAPI?"
Agent: web_search("FastAPI CORS configuration")
Agent: web_fetch("https://fastapi.tiangolo.com/tutorial/cors/")
Agent: [Cung cấp ví dụ code từ tài liệu]
```

### Gỡ lỗi (Debugging)

```
Người dùng: "Tôi gặp lỗi 'ModuleNotFoundError: no module named _sqlite3'"
Agent: web_search("ModuleNotFoundError _sqlite3 Python Docker")
Agent: [Tìm giải pháp: cài đặt gói python3-dev]
```

### Phân tích cạnh tranh

```
Người dùng: "Tính năng mới nhất của React 19 là gì?"
Agent: web_search("React 19 new features")
Agent: web_fetch("https://react.dev/blog/2024")
Agent: [Tóm tắt tính năng mới]
```

### Tại sao phù hợp cho Agentic AI?

Server này đặc biệt phù hợp cho Agentic AI vì:

- **🎯 Công cụ xác định** — `web_search` và `web_fetch` có đầu vào và đầu ra rõ ràng, dễ dự đoán. Agent có thể gọi chúng một cách tin cậy.
- **🔑 Không cần xác thực** — Agent không cần quản lý API key, giảm độ phức tạp đáng kể.
- **📦 Tự host** — Một process/container; vẫn cần HTTPS ra ngoài cho search và fetch.
- **🛡️ An toàn SSRF** — Chính sách DNS global-only giảm rủi ro lộ mạng nội bộ từ URL do agent cung cấp.
- **📝 Đầu ra Markdown** — Văn bản sạch, có cấu trúc, LLM có thể xử lý hiệu quả.
- **🌐 Đa số trang web fetch được** — Hỗ trợ HTML, PDF, text, JSON, XML, và cả GitHub README. Hầu hết nội dung web đều có thể đọc được.

---

## Bảo mật

### Cơ chế bảo vệ tích hợp

| Bảo vệ                             | Cách hoạt động                                                                                     |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| **Chống SSRF**                | **Mọi** DNS answer phải là IP global unicast; private/loopback/link-local/special-use bị từ chối |
| **Không userinfo**              | Credential trong authority (`user:pass@host`) bị reject                                              |
| **DNS Pinning + SNI**           | Kết nối tới IP đã pin đã validate; TLS SNI/hostname khớp host yêu cầu                            |
| **Re-check redirect**           | Mỗi redirect chạy lại URL + multi-answer DNS (tối đa 5 hop)                                        |
| **Phát hiện nhị phân**     | Hình ảnh, executable, archive bị chặn                                                               |
| **Giới hạn kích thước**   | Cap body/decompress; 4 MB trang thường, 20 MB PDF, 128,000 ký tự đầu ra mặc định                |
| **Thứ tự charset**             | BOM → HTTP `Content-Type` → HTML meta → UTF-8                                                      |
| **Ranh giới credential**      | Secret provider chỉ trong provider HTTP; page fetch không kế thừa                                   |

### Lưu ý về mạng

- Bind `127.0.0.1` mặc định. Chỉ `MCP_HOST=0.0.0.0` khi cố ý expose (ví dụ Docker); non-loopback emit `UserWarning`.
- **Bearer auth tùy chọn** cho HTTP/SSE: `MCP_AUTH_MODE=bearer` + `MCP_BEARER_TOKEN`. Client gửi `Authorization: Bearer <token>`. STDIO không dùng token. Ưu tiên loopback + client local, hoặc reverse proxy khi expose production.
- Search và fetch luôn tạo **lưu lượng ra ngoài** (provider + site đích). Không phải search offline air-gapped.
- Docker Compose cô lập process trong mạng container; image vẫn có thể bind `0.0.0.0` trong container để publish port.

---

## Phát triển

### Cấu trúc dự án

```
websift/
├── pyproject.toml          # Metadata (dynamic version), deps, console script
├── CHANGELOG.md            # Keep a Changelog
├── docker-compose.yml      # Docker Compose
├── Dockerfile              # Python 3.12-slim
├── requirements.txt        # Mirror runtime deps (ưu tiên pyproject.toml)
├── server.py               # Entry mỏng → websift.cli:main
├── .env.example            # Mẫu biến môi trường
├── .github/workflows/      # Matrix build/test + publish PyPI
├── README.md               # Tài liệu tiếng Anh
├── docs/
│   └── README.vi.md        # Tài liệu tiếng Việt (tệp này)
├── tests/                  # Suite pytest offline (markers: live, provider)
└── websift/
    ├── __init__.py         # WebSearchClient, AppSettings, __version__
    ├── __main__.py         # python -m websift
    ├── cli.py              # argparse CLI
    ├── settings.py         # AppSettings typed
    ├── auth.py             # Bearer + body limit
    ├── concurrency.py      # WorkLimits
    ├── models.py           # Structured internals
    ├── config.py           # Constants
    ├── security.py         # SSRF / DNS
    ├── content.py          # Content-type
    ├── http.py             # Page fetch
    ├── html.py             # HTML → Markdown
    ├── client.py           # Façade công khai
    ├── provider_http.py    # Transport credential provider
    ├── providers/          # DDGS + registry
    └── server.py           # create_server / ServerApp
```

### Đặt tên

| Bề mặt | Tên |
| ------ | --- |
| PyPI / CLI / Docker / import | `websift` |
| MCP tools (ổn định) | `web_search`, `web_fetch` |
| Nguồn version | `websift.__version__` |

### Chạy local

```bash
# Cài từ PyPI
pip install websift

# Hoặc editable + dev tools
pip install -e ".[dev]"

# CLI help / version
websift --help
websift --version

# Chạy MCP server
websift serve

# Cài đặt tùy chỉnh qua CLI (hoặc env)
websift serve --port 9000 --transport sse

# One-shot search / fetch
websift search "test"
websift fetch https://example.com

# Thư viện (không cần server)
python -c "from websift import WebSearchClient; print(WebSearchClient().search('test'))"
```

### Lint, test, build

```bash
ruff check websift tests
ruff format --check websift tests
python -m pytest --cov=websift --cov-report=term-missing --cov-fail-under=85 -m "not live and not provider"
python -m build
twine check dist/*
```

### Chạy với Docker

```bash
# Build và khởi động (không bắt buộc .env)
docker compose up -d --build

# Secret runtime (tùy chọn)
# docker compose --env-file .env up -d

# Xem log
docker compose logs -f

# Dừng
docker compose down
```

Image chạy non-root (`websift` uid 10001), entrypoint `websift`, TCP healthcheck.

---

## Câu hỏi thường gặp (FAQ)

### Hỏi: Có cần API key không?

**Không với provider DDGS mặc định.** DuckDuckGo không cần key. Provider tùy chọn **Brave / Tavily / Exa** cần key qua env server (`BRAVE_API_KEY`, …); **SearXNG** cần `SEARXNG_BASE_URL`. Key **không** qua argument tool MCP — xem bảng provider ở trên.
### Hỏi: Có phải unlimited / không rate limit không?

**Không.** Websift không bán quota, nhưng DuckDuckGo, provider khác và site đích có thể throttle/CAPTCHA/block. MCP call đồng thời cũng bị giới hạn bởi `SEARCH_MAX_CONCURRENCY` / `FETCH_MAX_CONCURRENCY` / `PDF_MAX_CONCURRENCY`.

### Hỏi: Có thể dùng sau firewall không?

Có, nếu cho phép HTTPS ra ngoài tới search provider và site đích. Truy cập vào chỉ cần cho endpoint MCP khi dùng HTTP/SSE (mặc định loopback cổng 8787).

### Hỏi: So với Tavily hay Firecrawl thì sao?

Giải pháp này đơn giản hơn và miễn phí, nhưng không cung cấp render JS, scrape sâu, hay tìm kiếm ngữ nghĩa. Đối với tìm kiếm web cơ bản + lấy nội dung trang, đây là giải pháp thay thế miễn phí tốt. Xem [bảng so sánh](#bảng-so-sánh-chi-tiết) để biết chi tiết.

### Hỏi: Có thể thêm xác thực không?

Có — cho **streamable-http / SSE**:

```bash
export MCP_AUTH_MODE=bearer
export MCP_BEARER_TOKEN='a-long-random-secret'
```

Client phải gửi `Authorization: Bearer <token>`. Token sai/thiếu → **401**, không echo secret. STDIO bỏ qua bearer (tin cậy process-local). Vẫn có thể đặt reverse proxy phía trước và để `MCP_AUTH_MODE=none`.

Giới hạn body tùy chọn: `MCP_MAX_REQUEST_BODY_BYTES=1048576`.
### Hỏi: Hỗ trợ những giao thức transport nào?

- **streamable-http** (khuyến nghị, mặc định) — tiêu chuẩn MCP hiện đại
- **sse** — Server-Sent Events cũ (vẫn được hỗ trợ)
- **stdio** — cho giao tiếp tiến trình local

### Hỏi: Tại sao đầu ra bị giới hạn 128,000 ký tự?

Điều này giữ phản hồi trong khung ngữ cảnh điển hình của LLM trong khi vẫn cung cấp nội dung đáng kể. Bạn có thể hạ/nâng qua `PAGE_MAX_CHARS`, `WebSearchClient(max_page_chars=...)`, hoặc `MAX_PAGE_CHARS` trong `websift/config.py`.

### Hỏi: Có thể dùng cho trang web nội bộ/riêng không?

Mặc định, bảo vệ SSRF chặn các dải IP riêng. Để cho phép trang nội bộ, sửa `websift/security.py` để whitelist domain hoặc dải IP cụ thể.

### Hỏi: Có thể dùng như thư viện Python (không qua MCP) không?

**Có!** Chỉ cần `pip install websift` rồi import trực tiếp:

```python
from websift import WebSearchClient

client = WebSearchClient(max_results=10, search_timeout=20, fetch_timeout=45)
client.search("từ khóa tìm kiếm")
client.fetch("https://example.com")
```

Không cần server, không cần Docker, không cần MCP — chỉ cần Python thuần.

### Hỏi: Có thể publish phiên bản của mình lên PyPI không?

Có. Sau khi thay đổi code:

```bash
# Cài đặt công cụ build
pip install build twine

# Build package
python -m build

# Upload thử (TestPyPI)
twine upload --repository testpypi dist/*

# Upload thật (PyPI)
twine upload dist/*
```

---

## Giấy phép

MIT — xem [LICENSE](LICENSE) để biết chi tiết.

## Lời cảm ơn

- [DuckDuckGo Search (ddgs)](https://github.com/johnbedes/ddgs) — backend tìm kiếm
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) — phân tích HTML
- [pypdf](https://pypdf.readthedocs.io/) — trích xuất text từ PDF
- [FastMCP](https://github.com/modelcontextprotocol/python-sdk) — framework MCP server
- [Model Context Protocol](https://modelcontextprotocol.io/) — giao thức mở cho tích hợp công cụ AI
- [VS Code MCP Documentation](https://code.visualstudio.com/docs/agent-customization/mcp-servers) — hướng dẫn MCP chính thức của VS Code
- [Claude Code MCP Documentation](https://code.claude.com/docs/en/mcp) — hướng dẫn MCP chính thức của Claude Code
- [Cursor MCP Documentation](https://cursor.com/docs/mcp) — hướng dẫn MCP chính thức của Cursor
- [Windsurf MCP Documentation](https://docs.windsurf.com/plugins/cascade/mcp) — hướng dẫn MCP chính thức của Windsurf
- [Copilot CLI MCP Documentation](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers) — hướng dẫn MCP chính thức của GitHub Copilot CLI
- [Claude Desktop MCP Documentation](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop) — hướng dẫn MCP chính thức của Claude Desktop
- [JetBrains MCP Documentation](https://www.jetbrains.com/help/idea/mcp-server.html) — hướng dẫn MCP chính thức của JetBrains
