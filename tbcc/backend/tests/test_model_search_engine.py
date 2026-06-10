"""Tests for macro model search engine (extension parity)."""

from app.services.model_search_engine import (
    analyze_model_search_html,
    build_model_search_url,
    derive_username_template_from_search_url,
    get_macro_search_sites,
    validate_custom_source_url,
)


def test_build_model_search_url_encodes():
    assert build_model_search_url("https://x.com/?s={username}", "a b") == "https://x.com/?s=a%20b"


def test_derive_template():
    url = "https://example.com/search/my_model?q=1"
    tpl = derive_username_template_from_search_url(url, "my_model")
    assert tpl == "https://example.com/search/{username}?q=1"


def test_analyze_json_array():
    html = '[{"id":1,"title":"a"},{"id":2,"title":"b"},{"id":3,"title":"c"}]'
    r = analyze_model_search_html(html, username="model_a")
    assert r["has_results"] is True
    assert r["count"] == 3
    assert r["confidence"] == "high"


def test_analyze_rejects_count_without_username():
    html = "x" * 8000 + '<div class="video-card"></div><div class="video-card"></div> popular videos gallery'
    r = analyze_model_search_html(html, username="not_in_page")
    assert r["has_results"] is False
    assert r.get("signal") == "no_username_in_html"


def test_analyze_accepts_username_in_page():
    html = (
        "x" * 100
        + '<article></article><article></article> results for cool_model only'
    )
    r = analyze_model_search_html(html, username="cool_model")
    assert r["has_results"] is True


def test_validate_custom_url():
    assert validate_custom_source_url("https://x.com/{username}") is None
    assert "http" in (validate_custom_source_url("ftp://x.com/{username}") or "")


def test_macro_sites_include_builtin_category():
    sites = get_macro_search_sites(category="macro")
    assert len(sites) >= 1
    assert all(s.get("category") == "macro" for s in sites)
    ids = {s["id"] for s in sites}
    assert "leakedzone" in ids or any("macro" in str(s.get("url", "")) for s in sites)
