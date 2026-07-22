"""Content-type detection helpers."""

from web_search.content import (
    has_binary_magic,
    has_pdf_magic,
    is_text_mime,
    looks_binary,
    looks_like_html,
    looks_like_html_document,
)


def test_pdf_magic():
    assert has_pdf_magic(b"%PDF-1.7\n...") is True
    assert has_pdf_magic(b"%PD") is False
    assert has_pdf_magic(b"") is False


def test_binary_magic_images_and_archives():
    assert has_binary_magic(b"\x89PNG\r\n\x1a\n") is True
    assert has_binary_magic(b"GIF89a....") is True
    assert has_binary_magic(b"\xff\xd8\xff\xe0") is True
    assert has_binary_magic(b"PK\x03\x04....") is True
    assert has_binary_magic(b"\x1f\x8b....") is True
    assert has_binary_magic(b"hello text") is False


def test_text_mime():
    assert is_text_mime("text/html") is True
    assert is_text_mime("TEXT/PLAIN; charset=utf-8") is True
    assert is_text_mime("application/json") is True
    assert is_text_mime("application/xml") is True
    assert is_text_mime("application/javascript") is True
    assert is_text_mime("application/xhtml+xml") is True
    assert is_text_mime("application/pdf") is False
    assert is_text_mime("image/png") is False


def test_looks_binary_control_ratio():
    assert looks_binary("hello world") is False
    assert looks_binary("") is False
    noisy = "\x00" * 10 + "a" * 10
    assert looks_binary(noisy, threshold=0.02) is True
    assert looks_binary("ok" + "�" * 5, threshold=0.02) is True


def test_looks_like_html():
    assert looks_like_html("<html><body>hi</body></html>") is True
    assert looks_like_html("  <div class='x'>") is True
    assert looks_like_html("just plain text") is False


def test_looks_like_html_document():
    assert looks_like_html_document("<!DOCTYPE html><html>") is True
    assert looks_like_html_document("<html lang='en'>") is True
    assert looks_like_html_document("<?xml version='1.0'?><html>") is True
    assert looks_like_html_document("<div>only fragment</div>") is False
