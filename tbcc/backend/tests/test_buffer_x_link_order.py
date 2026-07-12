"""Tests for Buffer X first-URL link preview ordering (affiliate-first default)."""

from __future__ import annotations

import pytest

from app.models.promo_affiliate_rotation_cursor import PromoAffiliateRotationCursor
from app.services.buffer_x_link_order import (
    affiliate_first_enabled,
    apply_buffer_x_link_cycle,
    classify_url,
    first_url,
    link_cycle_enabled,
    reorder_caption_urls,
)
from app.services.buffer_flywheel_copy import build_flywheel_x_caption
from app.services.buffer_native_queue_refill import build_native_queue_caption


AFFILIATE = "https://nodress.site/tg/bot?username=Aifasteditbot&ref_id=1"
TELEGRAM = "https://t.me/+hub123"
ALLMYLINKS = "https://allmylinks.com/aof69?utm_source=buffer"
EROME = "https://www.erome.com/a/abc123"


def test_classify_url_categories():
    assert classify_url(AFFILIATE) == "affiliate"
    assert classify_url(TELEGRAM) == "telegram"
    assert classify_url(ALLMYLINKS) == "allmylinks"
    assert classify_url(EROME) == "erome"


def test_reorder_puts_affiliate_first():
    raw = f"TABOO lane on Telegram. hub {TELEGRAM} · revshare {AFFILIATE} · map {ALLMYLINKS}"
    out = reorder_caption_urls(raw, "affiliate")
    assert first_url(out) == AFFILIATE


def test_reorder_puts_allmylinks_first():
    raw = f"lane drop. hub {TELEGRAM} · map {ALLMYLINKS} · try {AFFILIATE}"
    out = reorder_caption_urls(raw, "allmylinks")
    assert first_url(out) == ALLMYLINKS


def test_reorder_multiline_flywheel_style():
    raw = f"New drop — preview on Erome.\n{EROME}\n{TELEGRAM}"
    out = reorder_caption_urls(raw, "telegram")
    assert first_url(out) == TELEGRAM


def test_affiliate_first_default_pins_affiliate(db, monkeypatch):
    monkeypatch.delenv("TBCC_BUFFER_X_AFFILIATE_FIRST", raising=False)
    monkeypatch.setenv("TBCC_BUFFER_X_LINK_CYCLE", "1")
    raw = f"stack. hub {TELEGRAM} · {AFFILIATE} · map {ALLMYLINKS}"
    for _ in range(5):
        out = apply_buffer_x_link_cycle(raw, db=db, advance=True)
        assert first_url(out) == AFFILIATE
        db.commit()


def test_affiliate_first_never_telegram_card(db, monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_X_AFFILIATE_FIRST", "1")
    raw = f"FOMO drop {TELEGRAM} then {AFFILIATE}"
    out = apply_buffer_x_link_cycle(raw, db=db, advance=True)
    assert first_url(out) == AFFILIATE
    assert classify_url(first_url(out) or "") != "telegram"


def test_apply_cycles_when_affiliate_first_off(db, monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_X_AFFILIATE_FIRST", "0")
    monkeypatch.setenv("TBCC_BUFFER_X_LINK_CYCLE", "1")
    raw = f"stack. hub {TELEGRAM} · {AFFILIATE} · map {ALLMYLINKS}"
    categories = {"affiliate", "allmylinks", "telegram"}

    first_urls: set[str] = set()
    for _ in range(len(categories)):
        out = apply_buffer_x_link_cycle(raw, db=db, advance=True)
        first_urls.add(first_url(out) or "")
        db.commit()

    assert TELEGRAM in first_urls
    assert AFFILIATE in first_urls
    assert ALLMYLINKS in first_urls
    assert len(first_urls) == 3


def test_apply_disabled_by_env(db, monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_X_AFFILIATE_FIRST", "0")
    monkeypatch.setenv("TBCC_BUFFER_X_LINK_CYCLE", "0")
    raw = f"hub {TELEGRAM} · {AFFILIATE}"
    out = apply_buffer_x_link_cycle(raw, db=db, advance=True)
    assert first_url(out) == TELEGRAM


def test_single_url_unchanged(db, monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_X_AFFILIATE_FIRST", "1")
    monkeypatch.setenv("TBCC_BUFFER_X_LINK_CYCLE", "1")
    raw = f"only one link {TELEGRAM}"
    assert apply_buffer_x_link_cycle(raw, db=db, advance=True) == raw


def test_cursor_resumes_from_db(db, monkeypatch):
    monkeypatch.setenv("TBCC_BUFFER_X_AFFILIATE_FIRST", "0")
    monkeypatch.setenv("TBCC_BUFFER_X_LINK_CYCLE", "1")
    db.add(PromoAffiliateRotationCursor(placement="x_link_first", network_key="", cursor_index=1))
    db.commit()
    raw = f"hub {TELEGRAM} · {AFFILIATE} · map {ALLMYLINKS}"
    out = apply_buffer_x_link_cycle(raw, db=db, advance=False)
    assert first_url(out) == ALLMYLINKS


def test_build_native_queue_caption_affiliate_first(monkeypatch, db):
    monkeypatch.delenv("TBCC_BUFFER_X_AFFILIATE_FIRST", raising=False)
    monkeypatch.setenv("TBCC_BUFFER_X_LINK_CYCLE", "1")
    monkeypatch.setenv("TBCC_X_USE_LINKVERTISE", "0")
    monkeypatch.setenv("TBCC_AOF_HUB_INVITE_URL", TELEGRAM)
    monkeypatch.setenv("TBCC_ALLMYLINKS_URL", "https://allmylinks.com/aof69")
    monkeypatch.setenv("TBCC_AFFILIATE_UNDRESS_URL", AFFILIATE)
    entry = {
        "text": "email list gets drops first. X gets affiliates + hub. {affiliate} · {hub} · map {allmylinks}",
    }
    for _ in range(3):
        cap = build_native_queue_caption(entry, db=db, advance_link_cycle=True)
        assert first_url(cap) == AFFILIATE
        db.commit()


def test_build_flywheel_x_caption_cycles_erome_and_telegram(monkeypatch, db):
    """No affiliate in flywheel caption — cycle still rotates erome/telegram."""
    monkeypatch.setenv("TBCC_BUFFER_X_AFFILIATE_FIRST", "1")
    monkeypatch.setenv("TBCC_BUFFER_X_LINK_CYCLE", "1")
    monkeypatch.setenv("TBCC_X_USE_LINKVERTISE", "0")
    monkeypatch.setenv("TBCC_AOF_HUB_INVITE_URL", TELEGRAM)
    firsts: set[str] = set()
    for _ in range(2):
        cap = build_flywheel_x_caption(
            "AOF BIG TITS",
            erome_album_url=EROME,
            telegram_invite=TELEGRAM,
            db=db,
            advance_link_cycle=True,
        )
        firsts.add(first_url(cap) or "")
        db.commit()
    assert EROME in firsts
    assert TELEGRAM in firsts


def test_link_cycle_enabled_default_on(monkeypatch):
    monkeypatch.delenv("TBCC_BUFFER_X_LINK_CYCLE", raising=False)
    assert link_cycle_enabled() is True


def test_affiliate_first_enabled_default_on(monkeypatch):
    monkeypatch.delenv("TBCC_BUFFER_X_AFFILIATE_FIRST", raising=False)
    assert affiliate_first_enabled() is True
