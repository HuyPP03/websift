"""HTML to Markdown converter and text truncation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

from websift.config import MIN_MAIN_CONTENT_CHARS

_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "div",
        "dl",
        "dt",
        "dd",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_STRIP_ALWAYS = ("script", "style", "template", "noscript", "head")
_STRIP_BOILERPLATE = ("nav", "footer", "aside")
_SKIP_TAGS = frozenset({"script", "style", "template", "noscript", "head", "svg", "iframe", "object", "embed"})
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_RE = re.compile(r"\n{3,}")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_EMPH_RE = re.compile(r"(\*\*|__|\*|_|`)")
_MD_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+")
_MD_QUOTE_RE = re.compile(r"(?m)^>\s?")
_MD_HR_RE = re.compile(r"(?m)^---\s*$")


@dataclass(frozen=True)
class HtmlRenderOptions:
    include_links: bool = True
    include_images: bool = False
    min_main_content_chars: int = MIN_MAIN_CONTENT_CHARS
    output_format: str = "markdown"  # markdown | text


def html_to_markdown(
    html: str,
    main_content: bool = False,
    *,
    base_url: str | None = None,
    include_links: bool = True,
    include_images: bool = False,
    min_main_content_chars: int = MIN_MAIN_CONTENT_CHARS,
    output_format: str = "markdown",
) -> str:
    opts = HtmlRenderOptions(
        include_links=include_links,
        include_images=include_images,
        min_main_content_chars=min_main_content_chars,
        output_format=(output_format or "markdown").strip().lower(),
    )
    try:
        from bs4 import BeautifulSoup, Comment, NavigableString
    except ImportError:
        return _fallback_strip(html)

    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup, main_content=main_content, Comment=Comment)

    root = _select_root(
        soup,
        main_content=main_content,
        min_main_content_chars=opts.min_main_content_chars,
    )
    blocks = _convert_children(root, base_url=base_url, NavigableString=NavigableString, opts=opts)
    text = "\n\n".join(b for b in blocks if b is not None and str(b).strip() != "")
    text = _BLANK_RE.sub("\n\n", text).strip()
    if opts.output_format == "text":
        text = _markdownish_to_text(text)
    return text


def truncate(text: str, max_chars: int) -> str:
    """Truncate preferring paragraph, then line, then word boundary.

    Final output (including the truncation marker) never exceeds ``max_chars``.
    """
    if not text:
        return "(page returned no readable text)"
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text

    total = len(text)
    # Reserve room for marker; if budget is tiny, hard-cut only.
    marker_tmpl = "\n\n... (truncated, {n} total chars)"
    marker = marker_tmpl.format(n=total)
    if max_chars <= len(marker) + 8:
        return text[:max_chars]

    budget = max_chars - len(marker)
    cut = _best_cut(text, budget)
    body = text[:cut].rstrip()
    # Recompute marker length is fixed for this total; ensure hard cap.
    out = body + marker
    if len(out) > max_chars:
        out = out[:max_chars]
    return out


def _best_cut(text: str, budget: int) -> int:
    if budget >= len(text):
        return len(text)
    window = text[:budget]
    # Prefer paragraph boundary in the last ~40% of the window.
    min_keep = max(0, int(budget * 0.6))
    para = window.rfind("\n\n", min_keep, budget)
    if para >= min_keep:
        return para
    line = window.rfind("\n", min_keep, budget)
    if line >= min_keep:
        return line
    space = window.rfind(" ", min_keep, budget)
    if space >= min_keep:
        return space
    return budget


def _fallback_strip(html: str) -> str:
    text = re.sub(r"<(script|style|template|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _strip_noise(soup, *, main_content: bool, Comment) -> None:
    for tag_name in _STRIP_ALWAYS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    if main_content:
        for tag_name in _STRIP_BOILERPLATE:
            for tag in soup.find_all(tag_name):
                tag.decompose()
    for tag in list(soup.find_all(True)):
        attrs = tag.attrs or {}
        if attrs.get("hidden") is not None or attrs.get("aria-hidden") == "true":
            tag.decompose()
            continue
        style = (attrs.get("style") or "").replace(" ", "").lower()
        if "display:none" in style or "visibility:hidden" in style:
            tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()


def _select_root(soup, *, main_content: bool, min_main_content_chars: int = MIN_MAIN_CONTENT_CHARS):
    if not main_content:
        return soup.body or soup

    candidates = []
    article = soup.find("article")
    if article is not None:
        candidates.append(article)
    main = soup.find("main")
    if main is not None:
        candidates.append(main)
    role_main = soup.find(attrs={"role": re.compile(r"^main$", re.I)})
    if role_main is not None and role_main not in candidates:
        candidates.append(role_main)

    threshold = max(0, int(min_main_content_chars))
    for candidate in candidates:
        if _text_len(candidate) >= threshold:
            return candidate
    return soup.body or soup


def _markdownish_to_text(text: str) -> str:
    """Best-effort strip of markdown markers for HTML_OUTPUT_FORMAT=text."""
    s = _MD_LINK_RE.sub(r"\1", text)
    s = _MD_HEADING_RE.sub("", s)
    s = _MD_QUOTE_RE.sub("", s)
    s = _MD_HR_RE.sub("", s)
    s = _MD_EMPH_RE.sub("", s)
    s = _BLANK_RE.sub("\n\n", s).strip()
    return s


def _text_len(el) -> int:
    return len(el.get_text(separator=" ", strip=True))


def _convert_children(root, *, base_url: str | None, NavigableString, opts: HtmlRenderOptions) -> list[str]:
    if root is None:
        return []
    return _convert_flow(list(root.children), base_url=base_url, NavigableString=NavigableString, opts=opts)


def _convert_flow(nodes: Iterable, *, base_url: str | None, NavigableString, opts: HtmlRenderOptions) -> list[str]:
    blocks: list[str] = []
    inline_buf: list = []

    def flush_inline() -> None:
        if not inline_buf:
            return
        text = _normalize_inline(
            _render_inline_nodes(inline_buf, base_url=base_url, NavigableString=NavigableString, opts=opts)
        )
        inline_buf.clear()
        if text:
            blocks.append(text)

    for node in nodes:
        if isinstance(node, NavigableString):
            if str(node).strip():
                inline_buf.append(node)
            continue
        name = getattr(node, "name", None)
        if name is None or name in _SKIP_TAGS:
            continue
        if name in _BLOCK_TAGS:
            flush_inline()
            blocks.extend(_convert_block(node, base_url=base_url, NavigableString=NavigableString, opts=opts))
        else:
            inline_buf.append(node)
    flush_inline()
    return blocks


def _convert_block(el, *, base_url: str | None, NavigableString, opts: HtmlRenderOptions) -> list[str]:
    name = el.name
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(name[1])
        text = _normalize_inline(
            _render_inline_nodes(el.children, base_url=base_url, NavigableString=NavigableString, opts=opts)
        )
        return [f"{'#' * level} {text}"] if text else []

    if name == "p":
        text = _normalize_inline(
            _render_inline_nodes(el.children, base_url=base_url, NavigableString=NavigableString, opts=opts)
        )
        return [text] if text else []

    if name == "hr":
        return ["---"]

    if name == "br":
        return []

    if name == "pre":
        return [_fence_code(el)]

    if name == "blockquote":
        inner_blocks = _convert_children(el, base_url=base_url, NavigableString=NavigableString, opts=opts)
        if not inner_blocks:
            return []
        quoted: list[str] = []
        for block in inner_blocks:
            lines = block.split("\n")
            quoted.append("\n".join(f"> {line}" if line else ">" for line in lines))
        return ["\n\n".join(quoted)]

    if name in ("ul", "ol"):
        return [
            "\n".join(
                _convert_list(
                    el,
                    ordered=(name == "ol"),
                    depth=0,
                    base_url=base_url,
                    NavigableString=NavigableString,
                    opts=opts,
                )
            )
        ]

    if name == "li":
        # Lone li — treat as unordered item.
        lines = _convert_list_item(
            el, ordered=False, index=1, depth=0, base_url=base_url, NavigableString=NavigableString, opts=opts
        )
        return ["\n".join(lines)] if lines else []

    if name == "table":
        table = _convert_table(el, base_url=base_url, NavigableString=NavigableString, opts=opts)
        return [table] if table else []

    if name in ("thead", "tbody", "tfoot", "tr", "td", "th"):
        # Only meaningful inside table converter; fall through as flow.
        return _convert_children(el, base_url=base_url, NavigableString=NavigableString, opts=opts)

    if name in ("dl",):
        return _convert_children(el, base_url=base_url, NavigableString=NavigableString, opts=opts)

    if name in ("dt", "dd"):
        text = _normalize_inline(
            _render_inline_nodes(el.children, base_url=base_url, NavigableString=NavigableString, opts=opts)
        )
        if not text:
            return []
        return [f"**{text}**" if name == "dt" else text]

    # Generic containers: recurse without double-emitting wrapper text.
    return _convert_children(el, base_url=base_url, NavigableString=NavigableString, opts=opts)


def _convert_list(
    el, *, ordered: bool, depth: int, base_url: str | None, NavigableString, opts: HtmlRenderOptions
) -> list[str]:
    lines: list[str] = []
    index = 0
    for child in el.children:
        if getattr(child, "name", None) != "li":
            continue
        index += 1
        lines.extend(
            _convert_list_item(
                child,
                ordered=ordered,
                index=index,
                depth=depth,
                base_url=base_url,
                NavigableString=NavigableString,
                opts=opts,
            )
        )
    return lines


def _convert_list_item(
    li, *, ordered: bool, index: int, depth: int, base_url: str | None, NavigableString, opts: HtmlRenderOptions
) -> list[str]:
    indent = "  " * depth
    bullet = f"{index}. " if ordered else "- "
    prefix = f"{indent}{bullet}"

    inline_nodes: list = []
    nested_blocks: list[str] = []
    for child in li.children:
        name = getattr(child, "name", None)
        if name in ("ul", "ol"):
            # Flush leading inline before nested list.
            if inline_nodes and not nested_blocks:
                text = _normalize_inline(
                    _render_inline_nodes(inline_nodes, base_url=base_url, NavigableString=NavigableString, opts=opts)
                )
                inline_nodes = []
                if text:
                    nested_blocks.append(prefix + text)
                else:
                    nested_blocks.append(prefix.rstrip())
            elif inline_nodes:
                text = _normalize_inline(
                    _render_inline_nodes(inline_nodes, base_url=base_url, NavigableString=NavigableString, opts=opts)
                )
                inline_nodes = []
                if text:
                    nested_blocks.append(f"{indent}  {text}")
            nested_blocks.extend(
                _convert_list(
                    child,
                    ordered=(name == "ol"),
                    depth=depth + 1,
                    base_url=base_url,
                    NavigableString=NavigableString,
                    opts=opts,
                )
            )
        elif name in _BLOCK_TAGS and name not in ("ul", "ol"):
            if inline_nodes:
                text = _normalize_inline(
                    _render_inline_nodes(inline_nodes, base_url=base_url, NavigableString=NavigableString, opts=opts)
                )
                inline_nodes = []
                if text:
                    if not nested_blocks:
                        nested_blocks.append(prefix + text)
                    else:
                        nested_blocks.append(f"{indent}  {text}")
            for block in _convert_block(child, base_url=base_url, NavigableString=NavigableString, opts=opts):
                for line in block.split("\n"):
                    if not nested_blocks:
                        nested_blocks.append(prefix + line)
                    else:
                        nested_blocks.append(f"{indent}  {line}" if line else "")
        else:
            inline_nodes.append(child)

    if inline_nodes:
        text = _normalize_inline(
            _render_inline_nodes(inline_nodes, base_url=base_url, NavigableString=NavigableString, opts=opts)
        )
        if text:
            if not nested_blocks:
                nested_blocks.append(prefix + text)
            else:
                nested_blocks.append(f"{indent}  {text}")
    if not nested_blocks:
        nested_blocks.append(prefix.rstrip())
    return nested_blocks


def _convert_table(table, *, base_url: str | None, NavigableString, opts: HtmlRenderOptions) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            # Some HTML nests oddly; allow one level.
            cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row = [
            _normalize_inline(
                _render_inline_nodes(cell.children, base_url=base_url, NavigableString=NavigableString, opts=opts)
            ).replace("|", "\\|")
            for cell in cells
        ]
        rows.append(row)
    if not rows:
        return ""

    width = max(len(r) for r in rows)
    for r in rows:
        while len(r) < width:
            r.append("")

    header = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    # If first row has no th and body empty, still emit as single header-like row.
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def _fence_code(pre_el) -> str:
    code_el = pre_el.find("code")
    node = code_el if code_el is not None else pre_el
    code = node.get_text()
    # Drop a single trailing newline common in <pre>
    if code.endswith("\n"):
        code = code[:-1]
    # Prefer language class on code if present.
    lang = ""
    if code_el is not None:
        classes = code_el.get("class") or []
        for c in classes:
            c = str(c)
            if c.startswith("language-"):
                lang = c[len("language-") :]
                break
            if c.startswith("lang-"):
                lang = c[len("lang-") :]
                break
    # Avoid breaking out of fence with triple backticks inside.
    fence = "```"
    if "```" in code:
        fence = "````"
    return f"{fence}{lang}\n{code}\n{fence}"


def _render_inline_nodes(nodes: Iterable, *, base_url: str | None, NavigableString, opts: HtmlRenderOptions) -> str:
    parts: list[str] = []
    for node in nodes:
        parts.append(_render_inline(node, base_url=base_url, NavigableString=NavigableString, opts=opts))
    return "".join(parts)


def _render_inline(node, *, base_url: str | None, NavigableString, opts: HtmlRenderOptions) -> str:
    if isinstance(node, NavigableString):
        return str(node)

    name = getattr(node, "name", None)
    if name is None or name in _SKIP_TAGS:
        return ""

    if name == "br":
        return "\n"

    if name == "img":
        if not opts.include_images:
            return ""
        alt = (node.get("alt") or "").strip()
        return alt

    if name == "a":
        text = _normalize_inline(
            _render_inline_nodes(node.children, base_url=base_url, NavigableString=NavigableString, opts=opts)
        )
        href = (node.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "data:")):
            return text
        if base_url:
            href = urljoin(base_url, href)
        if not text:
            text = href
        if not opts.include_links or opts.output_format == "text":
            return text
        return f"[{text}]({href})"

    if name == "code" or name in ("kbd", "samp"):
        # Nested in pre handled at block level; inline code here.
        inner = node.get_text()
        inner = inner.replace("`", "\\`")
        return f"`{inner}`"

    if name in ("strong", "b"):
        inner = _normalize_inline(
            _render_inline_nodes(node.children, base_url=base_url, NavigableString=NavigableString, opts=opts)
        )
        return f"**{inner}**" if inner else ""

    if name in ("em", "i"):
        inner = _normalize_inline(
            _render_inline_nodes(node.children, base_url=base_url, NavigableString=NavigableString, opts=opts)
        )
        return f"*{inner}*" if inner else ""

    if name in _BLOCK_TAGS:
        # Block inside inline context: flatten to text with spaces.
        return _normalize_inline(
            _render_inline_nodes(node.children, base_url=base_url, NavigableString=NavigableString, opts=opts)
        )

    return _render_inline_nodes(node.children, base_url=base_url, NavigableString=NavigableString, opts=opts)


def _normalize_inline(text: str) -> str:
    # Preserve intentional newlines from <br>, collapse other whitespace runs.
    parts = text.split("\n")
    cleaned = [_WS_RE.sub(" ", p).strip() for p in parts]
    # Drop empty edges but keep internal blank from double br lightly.
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned)
