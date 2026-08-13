"""Tests for @aofmainhub CTA pin copy."""

from __future__ import annotations

from app.services.mainhub_growth import CTA_CAPTION

TELEGRAM_PHOTO_CAPTION_MAX = 1024


def test_cta_caption_includes_five_pillar_keywords():
    low = CTA_CAPTION.lower()
    assert "one feed" in low
    assert "viproll" in low or "god roll" in low
    assert "mega" in low
    assert "early" in low
    assert "companion" in low or "spicybot" in low
    assert "direct where mapped" in low


def test_cta_caption_within_telegram_photo_limit():
    assert len(CTA_CAPTION) <= TELEGRAM_PHOTO_CAPTION_MAX
