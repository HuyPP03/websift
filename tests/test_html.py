"""HTML to Markdown and truncate characterization (v0.1.0 quirks)."""

from pathlib import Path

import pytest

from web_search.html import html_to_markdown, truncate

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def test_html_to_markdown_strips_script_style():
    html = """
    <html><head><style>.x{}</style></head>
    <body>
      <script>alert(1)</script>
      <h1>Hello</h1>
    </body></html>
    """
    out = html_to_markdown(html)
    assert "alert" not in out
    assert ".x" not in out
    assert "# Hello" in out


def test_html_to_markdown_headings_and_lists():
    html = """
    <article>
      <h1>Title</h1>
      <p>Intro</p>
      <ul><li>One</li><li>Two</li></ul>
    </article>
    """
    out = html_to_markdown(html, main_content=True)
    assert "# Title" in out
    assert "- One" in out
    assert "- Two" in out
    # v0.1.0 quirk: plain text under <p> is not emitted (NavigableString.name is None,
    # so hasattr(el, "name") is True and text branch never runs).
    assert "Intro" not in out


def test_paragraph_text_not_emitted_baseline_gap():
    """Document baseline gap: <p> text content is dropped."""
    assert html_to_markdown("<p>Hello</p>") == ""
    assert html_to_markdown("<div>visible text</div>") == ""


def test_main_content_prefers_article_when_long_enough():
    # get_text length must be >= MIN_MAIN_CONTENT_CHARS (200) for article selection.
    body = "".join(f"<h2>Section {i} with padding text here</h2>" for i in range(20))
    html = f"""
    <html><body>
      <nav><h1>Nav noise</h1></nav>
      <article>{body}</article>
      <footer><h1>Footer</h1></footer>
    </body></html>
    """
    out = html_to_markdown(html, main_content=True)
    assert "Section 0" in out
    assert "Nav noise" not in out
    assert "Footer" not in out


def test_main_content_falls_back_when_article_too_short():
    html = """
    <html><body>
      <article><h1>short</h1></article>
      <div><h1>Body long</h1>""" + ("x" * 200) + """</div>
    </body></html>
    """
    out = html_to_markdown(html, main_content=True)
    # short article < MIN_MAIN_CONTENT_CHARS → full soup root; both headings possible
    assert "short" in out or "Body long" in out


def test_hidden_and_comments_removed():
    html = """
    <div>
      <!-- secret comment -->
      <p hidden>hidden</p>
      <p aria-hidden="true">aria</p>
      <h1>visible</h1>
    </div>
    """
    out = html_to_markdown(html)
    assert "secret comment" not in out
    assert "hidden" not in out
    assert "aria" not in out
    assert "# visible" in out


def test_fixture_article_file():
    html = (FIXTURES / "article.html").read_text(encoding="utf-8")
    out = html_to_markdown(html, main_content=True)
    assert "Sample Article Title" in out
    assert "console.log" not in out
    assert "color: red" not in out


def test_bs4_missing_fallback(monkeypatch: pytest.MonkeyPatch):
    import builtins

    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "bs4" or name.startswith("bs4."):
            raise ImportError("no bs4")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    out = html_to_markdown("<html><body><p>Hi there</p><script>x</script></body></html>")
    assert "Hi there" in out
    assert "script" not in out.lower() or "x" not in out


def test_truncate_empty():
    assert truncate("", 100) == "(page returned no readable text)"


def test_truncate_under_limit():
    assert truncate("hello", 100) == "hello"


def test_truncate_over_limit():
    text = "a" * 50
    out = truncate(text, 20)
    assert out.startswith("a" * 20)
    assert "truncated" in out
    assert "50 total chars" in out
