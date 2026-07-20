"""Content-type detection helpers."""

import re

from web_search.config import BINARY_MAGIC, TEXT_MIME_PREFIXES

_HTML_DOCUMENT_RE = re.compile(r"(<\?xml|<!doctype\s+html|<html[\s>])")


def has_pdf_magic(data: bytes) -> bool:
    return data[:4] == b"%PDF"


def has_binary_magic(data: bytes) -> bool:
    return any(data.startswith(sig) for sig in BINARY_MAGIC)


def is_text_mime(content_type: str) -> bool:
    ct = content_type.lower()
    return any(ct.startswith(p) for p in TEXT_MIME_PREFIXES)


def looks_binary(text: str, threshold: float = 0.02) -> bool:
    """Heuristic: high ratio of control/replacement chars -> binary."""
    if not text:
        return False
    ctrl = sum(
        1 for ch in text
        if ch == "�" or (ord(ch) < 32 and ch not in "\t\n\r")
    )
    return ctrl / len(text) > threshold


def looks_like_html(body: str) -> bool:
    probe = body.lstrip()[:512].lower()
    return bool(re.search(r"<(html|head|body|div|p|span|script|meta)\b", probe))


def looks_like_html_document(body: str) -> bool:
    probe = body.lstrip()[:256].lower()
    return bool(_HTML_DOCUMENT_RE.match(probe))
