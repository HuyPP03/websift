"""HTML to Markdown and truncate tests (phase 3)."""

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


def test_paragraph_text_emitted():
    assert "Hello" in html_to_markdown("<p>Hello</p>")
    assert "visible text" in html_to_markdown("<div>visible text</div>")


def test_headings_lists_and_paragraphs():
    html = """
    <article>
      <h1>Title</h1>
      <p>Intro</p>
      <ul><li>One</li><li>Two</li></ul>
    </article>
    """
    out = html_to_markdown(html, main_content=True)
    assert "# Title" in out
    assert "Intro" in out
    assert "- One" in out
    assert "- Two" in out
    # No duplicated list item text from parent+descendant emission.
    assert out.count("One") == 1


def test_no_duplicate_heading_text():
    out = html_to_markdown("<h1>Only Once</h1>")
    assert out.count("Only Once") == 1
    assert out.startswith("# Only Once")


def test_links_kept():
    html = '<p>See <a href="https://example.com/x">docs</a> and <a href="/rel">rel</a>.</p>'
    out = html_to_markdown(html)
    assert "[docs](https://example.com/x)" in out
    assert "[rel](/rel)" in out


def test_links_with_base_url():
    html = '<p><a href="guide">guide</a> <a href="/abs">abs</a></p>'
    out = html_to_markdown(html, base_url="https://example.com/docs/")
    assert "[guide](https://example.com/docs/guide)" in out
    # Root-absolute path resolves to host root (urljoin semantics).
    assert "[abs](https://example.com/abs)" in out


def test_inline_and_fenced_code():
    html = """
    <div>
      <p>Use <code>fetch()</code> please.</p>
      <pre><code class="language-python">print("hi")
</code></pre>
    </div>
    """
    out = html_to_markdown(html)
    assert "`fetch()`" in out
    assert "```python" in out
    assert 'print("hi")' in out
    # Code is not flattened into a single paragraph with neighbors.
    assert "fetch()" in out.split("```")[0]


def test_blockquote():
    out = html_to_markdown("<blockquote><p>Quoted text</p></blockquote>")
    assert "> Quoted text" in out


def test_nested_lists_fixture():
    html = (FIXTURES / "nested_list.html").read_text(encoding="utf-8")
    out = html_to_markdown(html, main_content=True)
    assert "- Parent A" in out
    assert "Child A1" in out
    assert "1. First" in out
    assert "Second-1" in out
    # Nested lines are indented.
    assert any(line.startswith("  - Child") or line.startswith("  -") for line in out.splitlines())


def test_table_fixture():
    html = (FIXTURES / "table.html").read_text(encoding="utf-8")
    out = html_to_markdown(html, main_content=True)
    assert "| Name | Value |" in out or "| Name |" in out
    assert "alpha" in out
    assert "---" in out


def test_image_alt():
    out = html_to_markdown('<p>Logo: <img src="x.png" alt="Company logo"></p>', include_images=True)
    assert "Company logo" in out
    assert "x.png" not in out


def test_image_alt_off_by_default():
    out = html_to_markdown('<p>Logo: <img src="x.png" alt="Company logo"></p>')
    assert "Company logo" not in out


def test_include_links_false():
    out = html_to_markdown('<p>See <a href="https://example.com/x">docs</a>.</p>', include_links=False)
    assert "docs" in out
    assert "https://example.com/x" not in out


def test_output_format_text_strips_markdown():
    out = html_to_markdown("<h1>Title</h1><p>See <a href='https://ex.example'>here</a>.</p>", output_format="text")
    assert "Title" in out
    assert "here" in out
    assert "https://ex.example" not in out
    assert not out.startswith("#")


def test_main_content_prefers_article_when_long_enough():
    body = "".join(f"<p>Section {i} with padding text here for length.</p>" for i in range(12))
    html = f"""
    <html><body>
      <nav><h1>Nav noise</h1></nav>
      <article><h1>Article</h1>{body}</article>
      <footer><h1>Footer</h1></footer>
    </body></html>
    """
    out = html_to_markdown(html, main_content=True)
    assert "Section 0" in out
    assert "Article" in out
    assert "Nav noise" not in out
    assert "Footer" not in out


def test_main_content_role_main():
    pad = "word " * 50
    html = f"""
    <html><body>
      <div role="main"><h1>Role Main</h1><p>{pad}</p></div>
      <div><h1>Outside</h1></div>
    </body></html>
    """
    out = html_to_markdown(html, main_content=True)
    assert "Role Main" in out
    assert "Outside" not in out


def test_main_content_falls_back_when_article_too_short():
    html = (
        """
    <html><body>
      <article><h1>short</h1></article>
      <div><h1>Body long</h1>"""
        + ("x" * 200)
        + """</div>
    </body></html>
    """
    )
    out = html_to_markdown(html, main_content=True)
    assert "short" in out or "Body long" in out


def test_hidden_comments_template_removed():
    html = """
    <div>
      <!-- secret comment -->
      <template><p>templated</p></template>
      <p hidden>hidden</p>
      <p aria-hidden="true">aria</p>
      <p style="display:none">css-hidden</p>
      <h1>visible</h1>
    </div>
    """
    out = html_to_markdown(html)
    assert "secret comment" not in out
    assert "templated" not in out
    assert "hidden" not in out
    assert "aria" not in out
    assert "css-hidden" not in out
    assert "# visible" in out


def test_fixture_article_file():
    html = (FIXTURES / "article.html").read_text(encoding="utf-8")
    out = html_to_markdown(html, main_content=True)
    assert "Sample Article Title" in out
    assert "first paragraph" in out
    assert "Point one" in out
    assert 'print("hello")' in out
    assert "console.log" not in out
    assert "color: red" not in out
    assert "Copyright" not in out
    assert "Home | About" not in out


def test_fixture_docs_file():
    html = (FIXTURES / "docs.html").read_text(encoding="utf-8")
    out = html_to_markdown(html, main_content=True, include_images=True)
    assert "API Reference" in out
    assert "`fetch`" in out
    assert "[guide](/guide)" in out
    assert "[external docs](https://example.com/ext)" in out
    assert "```python" in out
    assert "Prefer explicit timeouts" in out
    assert "Websift logo" in out
    assert "Related links spam" not in out
    assert "footer noise" not in out


def test_malformed_html_still_readable():
    html = (FIXTURES / "malformed.html").read_text(encoding="utf-8")
    out = html_to_markdown(html)
    assert "Unclosed paragraph" in out or "bold" in out
    assert "Heading after bad nest" in out
    assert "Item one" in out
    assert "bad()" not in out


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
    assert "x" not in out or "script" not in out.lower()


def test_truncate_empty():
    assert truncate("", 100) == "(page returned no readable text)"


def test_truncate_under_limit():
    assert truncate("hello", 100) == "hello"


def test_truncate_hard_limit_includes_marker():
    text = "a" * 200
    out = truncate(text, 80)
    assert len(out) <= 80
    assert "truncated" in out
    assert "200 total chars" in out


def test_truncate_prefers_paragraph_boundary():
    p1 = "First paragraph about alpha " * 3
    p2 = "Second paragraph about beta " * 3
    text = p1.strip() + "\n\n" + p2.strip()
    # Budget large enough for p1 + marker, not full text.
    limit = len(p1) + 40
    out = truncate(text, limit)
    assert len(out) <= limit
    assert "First paragraph" in out
    assert "truncated" in out
    # Should not end mid-marker mess; prefer cutting before p2 when possible.
    body = out.split("\n\n... (truncated")[0]
    assert "Second paragraph" not in body or body.endswith("beta")


def test_truncate_prefers_line_boundary():
    lines = "\n".join(f"line-{i}-content" for i in range(20))
    limit = 80
    out = truncate(lines, limit)
    assert len(out) <= limit
    assert "truncated" in out
    body = out.split("\n\n... (truncated")[0]
    # Body should not end with a partial "line-" mid-token if a prior newline fits.
    assert body.splitlines()[-1].startswith("line-") or body == ""


def test_truncate_zero_budget():
    assert truncate("hello", 0) == ""


def test_truncate_tiny_budget_hard_cuts():
    # Marker does not fit — plain hard cut, no marker.
    out = truncate("abcdefghijklmnopqrstuvwxyz", 10)
    assert out == "abcdefghij"
    assert "truncated" not in out


def test_truncate_word_boundary():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    out = truncate(text, 55)
    assert len(out) <= 55
    assert "truncated" in out
    body = out.split("\n\n... (truncated")[0]
    # Prefer cutting at a space rather than mid-word when possible.
    assert not body.endswith(("alph", "bet", "gamm", "delt", "epsilo"))


def test_hr_and_br():
    out = html_to_markdown("<div><p>A<br>B</p><hr><p>C</p></div>")
    assert "A" in out and "B" in out
    assert "---" in out
    assert "C" in out


def test_strong_em_and_skipped_js_link():
    html = (
        "<p><strong>Bold</strong> and <em>italic</em> "
        '<a href="javascript:alert(1)">x</a> '
        '<a href="https://e.com"></a></p>'
    )
    out = html_to_markdown(html)
    assert "**Bold**" in out
    assert "*italic*" in out
    assert "javascript" not in out
    assert "[https://e.com](https://e.com)" in out


def test_definition_list_and_lone_li():
    out = html_to_markdown("<dl><dt>Term</dt><dd>Definition here</dd></dl>")
    assert "Term" in out
    assert "Definition here" in out
    out2 = html_to_markdown("<li>Orphan item</li>")
    assert "- Orphan item" in out2


def test_list_with_block_child():
    html = "<ul><li><p>Para in li</p><pre><code>x=1</code></pre></li></ul>"
    out = html_to_markdown(html)
    assert "Para in li" in out
    assert "x=1" in out


def test_nested_list_with_trailing_text():
    html = "<ul><li>Head<ul><li>Nest</li></ul>Tail</li></ul>"
    out = html_to_markdown(html)
    assert "Head" in out
    assert "Nest" in out
    assert "Tail" in out


def test_empty_list_item():
    out = html_to_markdown("<ul><li></li><li>ok</li></ul>")
    assert "- ok" in out


def test_pre_without_code_and_lang_class():
    out = html_to_markdown("<pre>raw pre</pre>")
    assert "```" in out
    assert "raw pre" in out
    out2 = html_to_markdown('<pre><code class="lang-js">x</code></pre>')
    assert "```js" in out2


def test_code_with_backticks_uses_longer_fence():
    out = html_to_markdown("<pre><code>a ``` b</code></pre>")
    assert "````" in out


def test_table_pipe_escape_and_ragged_rows():
    html = """
    <table>
      <tr><th>A|B</th><th>C</th></tr>
      <tr><td>1</td></tr>
    </table>
    """
    out = html_to_markdown(html)
    assert "A\\|B" in out or "A|B" in out.replace("\\|", "|")
    assert "1" in out


def test_empty_table():
    assert html_to_markdown("<table></table>") == ""


def test_visibility_hidden_stripped():
    out = html_to_markdown('<div><p style="visibility: hidden">nope</p><p>yes</p></div>')
    assert "nope" not in out
    assert "yes" in out


def test_main_element_selection():
    pad = "content " * 40
    html = f"<html><body><main><h1>MainTag</h1><p>{pad}</p></main><p>outside</p></body></html>"
    out = html_to_markdown(html, main_content=True)
    assert "MainTag" in out
    assert "outside" not in out


def test_svg_and_iframe_skipped():
    out = html_to_markdown('<div><svg><text>svgtext</text></svg><iframe src="x"></iframe><p>keep</p></div>')
    assert "svgtext" not in out
    assert "keep" in out


def test_empty_strong_em():
    out = html_to_markdown("<p><strong></strong><em></em>x</p>")
    assert "x" in out
    assert "**" not in out or out.count("**") == 0
