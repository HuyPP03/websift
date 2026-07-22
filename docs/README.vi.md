# websift — Tài liệu tiếng Việt

MCP server nhẹ, miễn phí, tự chủ (self-hosted) cung cấp khả năng truy cập web thời gian thực cho AI agents — tìm kiếm DuckDuckGo + lấy nội dung trang web (HTML → Markdown, PDF → text) — với bảo vệ SSRF và DNS pinning tích hợp. **Không cần API key.**

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
- **🆓 Hoàn toàn miễn phí** — Không cần API key, không cần đăng ký, không có giới hạn từ nhà cung cấp bên thứ ba. DuckDuckGo miễn phí, và server này cũng miễn phí.
- **🪶 Siêu nhẹ** — Chỉ một tiến trình Python, ~4 thư viện phụ thuộc, chạy trong container Docker nhỏ (`python:3.12-slim` ≈ 150 MB).
- **🔒 Bảo mật mặc định** — Chống SSRF (Server-Side Request Forgery) bằng cách chặn IP riêng, DNS pinning, xác thực SNI, giới hạn redirect, và kiểm tra loại nội dung.
- **🌐 Tương thích mọi MCP Client** — Hoạt động với bất kỳ client MCP nào: VS Code, Claude Desktop, Claude Code, Cursor, Windsurf, JetBrains, và các agent tùy chỉnh.
- **📄 Trích xuất thông minh** — HTML → Markdown sạch qua BeautifulSoup, PDF → text qua pypdf/pdfminer, phát hiện file nhị phân, tự động phát hiện charset.
- **🐙 Lối tắt GitHub README** — Khi fetch URL `github.com/owner/repo`, tự động dùng GitHub API để lấy README gốc.
- **🏠 Tự chủ (Self-hosted)** — Kiểm soát hoàn toàn dữ liệu của bạn. Không có lưu lượng nào được chuyển qua dịch vụ bên thứ ba.

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
| **Giới hạn tốc độ**    | Chỉ từ DuckDuckGo        | Giới hạn nhà cung cấp                | Giới hạn nhà cung cấp                | Giới hạn nhà cung cấp                | Giới hạn nhà cung cấp                |
| **Quyền riêng tư**       | ✅ Kiểm soát hoàn toàn | ⚠️ Dữ liệu gửi đến nhà cung cấp | ⚠️ Dữ liệu gửi đến nhà cung cấp | ⚠️ Dữ liệu gửi đến nhà cung cấp | ⚠️ Dữ liệu gửi đến nhà cung cấp |

### Khi nào nên chọn cái gì?

| Tình huống                                                                     | Khuyến nghị               |
| -------------------------------------------------------------------------------- | --------------------------- |
| Muốn truy cập web**miễn phí, không đăng ký** cho AI                | **websift** ✅ |
| Cần**scrape sâu** (trang render JS, sitemap)                             | Firecrawl                   |
| Cần**tìm kiếm ngữ nghĩa** (AI-powered relevance)                      | Exa                         |
| Muốn tìm kiếm**tối ưu cho agent** (chế độ `extract` của Tavily) | Tavily                      |
| Cần**quyền riêng tư tối đa** (tự chủ, không gọi bên ngoài)     | **websift** ✅ |
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
┌────────────┐                     │                      │
│  search()  │──► DuckDuckGo (ddgs)│                      │           
│  fetch()   │──► urllib + SSRF    │                      │
│            │    ├── html.py (BS4)│                      │
│            │    ├── http.py      │                      │
│            │    ├── security.py  │                      │
│            │    └── content.py   │                      │
└────────────┘                     └──────────────────────┘
```

### Cấu trúc module

```
web_search/
├── __init__.py    # xuất WebSearchClient + __version__
├── config.py      # hằng số (giới hạn kích thước, user-agent, MIME, ...)
├── security.py    # chống SSRF: kiểm tra IP riêng, DNS resolve + pin
├── content.py     # phát hiện loại nội dung (PDF, nhị phân, HTML)
├── http.py        # fetch HTTP thô: theo dõi redirect, SNI pinning, giải mã charset
├── html.py        # chuyển đổi HTML → Markdown, cắt ngắn văn bản
├── client.py      # WebSearchClient: search / fetch / lối tắt GitHub README
└── server.py      # MCP server module (có thể import hoặc chạy standalone)
server.py          # điểm vào MCP server (delegate về web_search.server)
```

---

## Cài đặt

### Tùy chọn 1: PyPI (Khuyến nghị)

```bash
pip install websift
```

Vậy là xong — bạn có thể dùng như **thư viện Python** (import trực tiếp) hoặc như **MCP server** (cho AI clients).

### Tùy chọn 2: Docker Compose

```bash
# Clone và khởi động
git clone <repo-url>
cd websift
docker compose up -d --build
```

MCP server sẽ có sẵn tại `http://localhost:8787/mcp`.

### Tùy chọn 3: Docker (Thủ công)

```bash
docker build -t websift .
docker run -d --name websift -p 8787:8787 websift
```

### Tùy chọn 4: Python trực tiếp (Không cần Docker)

```bash
# Cài đặt phụ thuộc
pip install -r requirements.txt

# Chạy server
python server.py
```

---

## Sử dụng

### Như một thư viện Python (Import trực tiếp)

Dùng `WebSearchClient` trực tiếp trong code Python — **không cần chạy server**:

```python
from web_search import WebSearchClient

client = WebSearchClient()

# Tìm kiếm web (DuckDuckGo)
results = client.search("tính năng mới Python 3.12")
print(results)

# Lấy nội dung trang web (HTML → Markdown, PDF → text)
content = client.fetch("https://docs.python.org/3/")
print(content)
```

**Phù hợp cho:**

- Script tùy chỉnh & tự động hóa
- Nhúng vào ứng dụng của riêng bạn
- Data pipeline & ETL workflow
- Testing & prototyping

### Như một MCP Server (Cho AI Clients)

Chạy server để expose tools cho bất kỳ AI client MCP nào:

```bash
# Khởi động server (mặc định: cổng 8787)
websift

# Cổng và transport tùy chỉnh
MCP_PORT=9000 MCP_TRANSPORT=sse websift
```

Hoặc qua Python:

```python
from web_search.server import main
main()
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
- **Tệp PDF** → trích xuất text qua pypdf / pdfminer
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
| `SEARCH_PROVIDER`        | `ddgs`            | Provider tìm kiếm (allowlist)                                          |
| `SEARCH_MAX_RESULTS`     | `5`               | Số kết quả tìm kiếm tối đa                                        |
| `SEARCH_TIMEOUT_SECONDS` | `30`              | Timeout search (giây)                                                   |
| `FETCH_TIMEOUT_SECONDS`  | `30`              | Timeout fetch trang (giây)                                              |
| `SEARCH_TIMEOUT`         | (alias)             | **Deprecated**: nếu set và thiếu timeout cụ thể thì map cả hai |

### Giới hạn nội bộ

| Cài đặt                   | Giá trị | Mô tả                         |
| ---------------------------- | --------- | ------------------------------- |
| Kích thước trang tối đa | 2 MB      | Giới hạn fetch trang thường |
| Kích thước PDF tối đa   | 20 MB     | Giới hạn fetch PDF            |
| Ký tự đầu ra tối đa    | 32,000    | Số ký tự gửi đến LLM      |
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
- **📦 Tự chứa** — Một container duy nhất, không có phụ thuộc bên ngoài ngoài DuckDuckGo.
- **🛡️ An toàn SSRF** — Agent có thể fetch URL một cách an toàn mà không gây rủi ro cho mạng nội bộ.
- **📝 Đầu ra Markdown** — Văn bản sạch, có cấu trúc, LLM có thể xử lý hiệu quả.
- **🌐 Đa số trang web fetch được** — Hỗ trợ HTML, PDF, text, JSON, XML, và cả GitHub README. Hầu hết nội dung web đều có thể đọc được.

---

## Bảo mật

### Cơ chế bảo vệ tích hợp

| Bảo vệ                           | Cách hoạt động                                                                                |
| ---------------------------------- | ------------------------------------------------------------------------------------------------- |
| **Chống SSRF**              | Tất cả IP được giải quyết đều được kiểm tra với dải IP riêng/loopback/link-local  |
| **DNS Pinning**              | DNS resolution được ghim vào IP đầu tiên; xác thực SNI đảm bảo chứng chỉ khớp      |
| **Giới hạn Redirect**      | Tối đa 5 redirect để ngăn vòng lặp redirect và bypass SSRF                                |
| **Kiểm tra Scheme**         | Chỉ cho phép scheme`http://` và `https://`                                                 |
| **Phát hiện nhị phân**   | Hình ảnh, tệp thực thi, archive, và nội dung nhị phân khác được phát hiện và chặn |
| **Giới hạn kích thước** | 2 MB cho trang thường, 20 MB cho PDF, giới hạn 32,000 ký tự đầu ra                        |
| **Phát hiện Charset**      | Phát hiện BOM (UTF-8/16/32), phân tích header Content-Type, fallback thẻ meta                |

### Lưu ý về mạng

- Server bind vào `127.0.0.1` mặc định. Chỉ set `MCP_HOST=0.0.0.0` khi cố ý expose (ví dụ Docker).
- Không có xác thực tích hợp — đặt behind reverse proxy (nginx, Caddy) nếu phơi ra bên ngoài.
- Docker Compose cô lập server trong mạng container riêng.

---

## Phát triển

### Cấu trúc dự án

```
websift/
├── pyproject.toml          # Metadata package, dependencies, console script
├── docker-compose.yml      # Cấu hình Docker Compose
├── Dockerfile              # Container Python 3.12-slim
├── requirements.txt        # Phụ thuộc Python
├── server.py               # Điểm vào MCP server (delegate về web_search.server)
├── .env.example            # Mẫu biến môi trường
├── .mcp.json               # Cấu hình MCP cho VS Code
├── README.md               # Tài liệu tiếng Anh
├── docs/
│   └── README.vi.md        # Tài liệu tiếng Việt (tệp này)
└── web_search/
    ├── __init__.py         # Xuất package (WebSearchClient, __version__)
    ├── config.py           # Hằng số và cấu hình
    ├── security.py         # Chống SSRF và DNS pinning
    ├── content.py          # Phát hiện loại nội dung
    ├── http.py             # Fetch HTTP với SNI pinning
    ├── html.py             # Chuyển đổi HTML sang Markdown
    ├── client.py           # WebSearchClient (search + fetch)
    └── server.py           # MCP server module (có thể import hoặc chạy standalone)
```

### Chạy local

```bash
# Cài đặt từ PyPI
pip install websift

# Hoặc cài đặt ở chế độ editable (cho phát triển)
pip install -e .

# Chạy như MCP server
websift

# Chạy với cài đặt tùy chỉnh
MCP_PORT=9000 MCP_TRANSPORT=sse websift

# Hoặc dùng như thư viện (không cần server)
python -c "from web_search import WebSearchClient; print(WebSearchClient().search('test'))"
```

### Chạy với Docker

```bash
# Build và khởi động
docker compose up -d --build

# Xem log
docker compose logs -f

# Dừng
docker compose down
```

---

## Câu hỏi thường gặp (FAQ)

### Hỏi: Có cần API key không?

**Không.** Tìm kiếm DuckDuckGo miễn phí và không cần xác thực. Toàn bộ server chạy mà không cần bất kỳ API key nào.

### Hỏi: Có thể dùng sau firewall không?

Có. Server chỉ cần truy cập HTTPS ra ngoài để đến DuckDuckGo và các trang web mục tiêu. Truy cập vào chỉ cần cho endpoint MCP (cổng 8787).

### Hỏi: So với Tavily hay Firecrawl thì sao?

Giải pháp này đơn giản hơn và miễn phí, nhưng không cung cấp render JS, scrape sâu, hay tìm kiếm ngữ nghĩa. Đối với tìm kiếm web cơ bản + lấy nội dung trang, đây là giải pháp thay thế miễn phí tốt. Xem [bảng so sánh](#bảng-so-sánh-chi-tiết) để biết chi tiết.

### Hỏi: Có thể thêm xác thực không?

Bản thân server không bao gồm xác thực, nhưng bạn có thể đặt behind nginx/Caddy với basic auth hoặc xác thực API key:

```nginx
location /mcp {
    auth_basic "MCP Server";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://localhost:8787/mcp;
}
```

### Hỏi: Hỗ trợ những giao thức transport nào?

- **streamable-http** (khuyến nghị, mặc định) — tiêu chuẩn MCP hiện đại
- **sse** — Server-Sent Events cũ (vẫn được hỗ trợ)
- **stdio** — cho giao tiếp tiến trình local

### Hỏi: Tại sao đầu ra bị giới hạn 32,000 ký tự?

Điều này giữ phản hồi trong khung ngữ cảnh điển hình của LLM trong khi vẫn cung cấp nội dung đáng kể. Bạn có thể điều chỉnh `MAX_PAGE_CHARS` trong `web_search/config.py` nếu cần.

### Hỏi: Có thể dùng cho trang web nội bộ/riêng không?

Mặc định, bảo vệ SSRF chặn các dải IP riêng. Để cho phép trang nội bộ, sửa `web_search/security.py` để whitelist domain hoặc dải IP cụ thể.

### Hỏi: Có thể dùng như thư viện Python (không qua MCP) không?

**Có!** Chỉ cần `pip install websift` rồi import trực tiếp:

```python
from web_search import WebSearchClient
client = WebSearchClient()
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
