"""Tests for telegram.me brand normalization (t.me DNS hold workaround)."""

from __future__ import annotations

from app.data.aof_telegram_links import normalize_telegram_me_brand


def test_normalize_bare_tme():
    assert normalize_telegram_me_brand("t.me/aofmainhub") == "telegram.me/aofmainhub"


def test_normalize_https_tme():
    assert normalize_telegram_me_brand("https://t.me/aofmainhub") == "https://telegram.me/aofmainhub"


def test_normalize_does_not_double_rewrite():
    assert normalize_telegram_me_brand("telegram.me/aofmainhub") == "telegram.me/aofmainhub"
    assert normalize_telegram_me_brand("https://telegram.me/+jKGzJMZAhCZjNjdh") == "https://telegram.me/+jKGzJMZAhCZjNjdh"


def test_watermark_text_rewrites_env(monkeypatch):
    monkeypatch.setenv("TBCC_WATERMARK_TEXT", "t.me/aofmainhub")
    monkeypatch.delenv("TBCC_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("TBCC_PROMO_PUBLIC_BASE_URL", raising=False)
    from app.services import media_watermark as wm

    assert wm.watermark_text() == "telegram.me/aofmainhub"
