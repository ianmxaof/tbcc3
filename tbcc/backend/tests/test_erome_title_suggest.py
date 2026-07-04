"""Tests for Erome title suggester."""

from app.services.erome_title_suggest import suggest_erome_post


def test_suggest_erome_post_default_when_empty():
    out = suggest_erome_post()
    assert out.get("title")
    assert out.get("tags")
