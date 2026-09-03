"""Tests for @aofmainhub CTA + daily shop posts."""

from __future__ import annotations

from app.data.aof_network import (
    MAINHUB_SCHED_DAILY_BAIT_NAME,
    MAINHUB_SCHED_DAILY_SUB_NAME,
)
from app.services.mainhub_growth import CTA_CAPTION, _cta_caption, _daily_sub_captions

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
    assert len(_cta_caption()) <= TELEGRAM_PHOTO_CAPTION_MAX


def test_cta_and_daily_copy_lead_with_six_dollar_month():
    assert "$6" in _cta_caption()
    for body in _daily_sub_captions():
        assert "$6" in body
        assert "crypto" in body.lower() or "card" in body.lower()


def test_daily_scheduler_names_are_stable():
    assert "daily subscription" in MAINHUB_SCHED_DAILY_SUB_NAME.lower()
    assert "stars bait" in MAINHUB_SCHED_DAILY_BAIT_NAME.lower()
