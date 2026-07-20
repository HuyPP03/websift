"""HTML to Markdown converter and text truncation."""

import re

from web_search.config import MIN_MAIN_CONTENT_CHARS


def html_to_markdown(html: str, main_content: bool = False) -> str:
    try:
        from bs4 import BeautifulSoup, Comment
    except ImportError:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "head", "noscript"]):
        tag.decompose()
    for tag in soup.find_all(True):
        attrs = tag.attrs or {}
        if attrs.get("hidden") or attrs.get("aria-hidden") == "true":
            tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    root = soup
    if main_content:
        for scope in ("article", "main"):
            candidate = soup.find(scope)
            if candidate:
                text = candidate.get_text(separator="\n")
                if len(text.strip()) >= MIN_MAIN_CONTENT_CHARS:
                    root = candidate
                    break

    lines: list[str] = []
    for el in root.descendants:
        if not hasattr(el, "name"):
            txt = str(el).strip()
            if txt:
                lines.append(txt)
        elif el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            lines.append("\n" + "#" * int(el.name[1]) + " " + el.get_text(strip=True))
        elif el.name == "li":
            lines.append("- " + el.get_text(strip=True))
        elif el.name in ("p", "br", "tr", "div"):
            lines.append("")

    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def truncate(text: str, max_chars: int) -> str:
    if not text:
        return "(page returned no readable text)"
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n... (truncated, {len(text)} total chars)"
    return text
