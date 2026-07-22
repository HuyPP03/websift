"""Shared constants for web_search."""

MAX_FETCH_BYTES = 2 * 1024 * 1024  # 2 MB for normal pages (decompressed)
MAX_PDF_FETCH_BYTES = 20 * 1024 * 1024  # 20 MB for PDFs (download)
MAX_COMPRESSED_BYTES = 2 * 1024 * 1024  # wire/compressed download cap
MAX_DECOMPRESSED_BYTES = 4 * 1024 * 1024  # post-decompression cap (bomb guard)
MAX_PAGE_CHARS = 32_000  # chars fed to LLM
MIN_MAIN_CONTENT_CHARS = 200
MAX_REDIRECTS = 5
PDF_MAX_PAGES = 50
PDF_MAX_CHARS = 32_000

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

UNICODE_BOM_CODECS = [
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
]

BINARY_MAGIC = [
    b"\x89PNG",
    b"GIF8",
    b"\xff\xd8\xff",  # images
    b"PK\x03\x04",  # zip/docx/xlsx
    b"\x1f\x8b",  # gzip
    b"BZh",  # bzip2
    b"\x7fELF",  # ELF binary
    b"MZ",  # Windows PE
]

TEXT_MIME_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/xhtml",
)

# Content-Encoding values we accept (applied left-to-right as listed by servers, reverse to decode).
SUPPORTED_CONTENT_ENCODINGS = frozenset({"gzip", "x-gzip", "deflate", "identity"})
