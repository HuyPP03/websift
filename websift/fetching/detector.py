"""Narrow detector for HTTP challenge pages and JavaScript-only shells."""

from __future__ import annotations

import re

from websift.models import FetchResult

DETECTOR_VERSION = "challenge-js-shell-v2"

_MIN_RAW_HTML_FOR_EMPTY_CHECK = 500  # raw HTML bytes to consider for JS-rendered check
_MIN_EXTRACTED_CHARS = 50  # extracted text chars below which page is considered empty
_MODULE_SCRIPT_RE = re.compile(r'<script[^>]+type\s*=\s*["\']module["\']', re.IGNORECASE)
_SPA_ROOT_RE = re.compile(
    r"<div[^>]+id\s*=\s*[\"'](?:root|__nuxt|__app|app|___loader)[\"']" r'[^>]*/?\s*>',
    re.IGNORECASE,
)


_CHALLENGE_PLATFORM_RE = re.compile(
    r"(?:cf-chl-|__cf_chl|/cdn-cgi/challenge-platform/|cloudflare\s+ray\s+id)",
    re.IGNORECASE,
)
_CHALLENGE_PROMPT_RE = re.compile(
    r"(?:just\s+a\s+moment|checking\s+your\s+browser|"
    r"enable\s+javascript\s+and\s+cookies\s+to\s+continue|"
    r"verify(?:ing)?\s+you\s+are\s+human)",
    re.IGNORECASE,
)
_NOSCRIPT_JS_SHELL_RE = re.compile(
    r"<noscript[^>]*>[^<]{0,300}(?:please\s+)?(?:you\s+need\s+to\s+)?"
    r"enable\s+javascript(?:\s+to\s+run\s+this\s+app)?[^<]{0,300}</noscript\s*>",
    re.IGNORECASE,
)


def is_challenge_or_js_shell(result: FetchResult, *, raw_html: str | None = None) -> bool:
    """Detect a challenge or JS-only shell from bounded, successful HTTP HTML.

    Callers should pass pre-extraction ``raw_html`` when available. Requiring a
    platform marker plus a challenge prompt, or a specific ``noscript`` shell,
    avoids treating ordinary script-heavy documentation as a browser challenge.
    """
    if not result.ok or "html" not in (result.content_type or "").lower():
        return False
    content = (raw_html if raw_html is not None else result.content or "").strip()
    if not content:
        return False
    content = content[:20_000]
    if _CHALLENGE_PLATFORM_RE.search(content) and _CHALLENGE_PROMPT_RE.search(content):
        return True
    if _NOSCRIPT_JS_SHELL_RE.search(content):
        return True
    # JS-rendered SPA: substantial raw HTML but empty extraction
    if _is_js_rendered_shell(content, result):
        return True
    return False


def _is_js_rendered_shell(raw_html: str, result: FetchResult) -> bool:
    """Return True when raw HTML looks like a JS-only SPA with no server-rendered content."""
    raw_len = len((raw_html or "").encode("utf-8", errors="replace"))
    if raw_len < _MIN_RAW_HTML_FOR_EMPTY_CHECK:
        return False
    extracted = (result.content or "").strip()
    if len(extracted) >= _MIN_EXTRACTED_CHARS:
        return False
    if _SPA_ROOT_RE.search(raw_html) and _MODULE_SCRIPT_RE.search(raw_html):
        return True
    return False
