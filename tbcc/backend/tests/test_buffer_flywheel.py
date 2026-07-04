"""Tests for X promo image pool + flywheel captions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.buffer_flywheel_copy import build_flywheel_x_caption
from app.services.buffer_x_promo_image import (
    looks_like_direct_image_url,
    load_promo_image_pool,
    pick_promo_image,
)


def test_looks_like_direct_image_url():
    assert looks_like_direct_image_url("https://i.ibb.co/abc/teaser.jpg")
    assert looks_like_direct_image_url("https://promo.example.com/static/promo/aof.png")
    assert not looks_like_direct_image_url("https://imgbb.com/album/xyz")
    assert not looks_like_direct_image_url("http://insecure.com/x.jpg")


def test_load_promo_image_pool_from_env(monkeypatch):
    monkeypatch.setenv("TBCC_X_PROMO_IMAGE_URLS", "https://cdn.example.com/a.jpg,https://cdn.example.com/b.png")
    monkeypatch.setenv("TBCC_X_PROMO_IMAGE_POOL_FILE", str(Path("/nonexistent/pool.json")))
    pool = load_promo_image_pool()
    assert len(pool) == 2
    assert pool[0]["direct_url"].startswith("https://")


def test_pick_promo_image_respects_pool(tmp_path, monkeypatch):
    data = [{"direct_url": "https://i.ibb.co/test/one.jpg", "viewer_url": "https://ibb.co/album/one"}]
    path = tmp_path / "pool.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("TBCC_X_PROMO_IMAGE_POOL_FILE", str(path))
    monkeypatch.setenv("TBCC_BUFFER_X_PROMO_IMAGES", "1")
    picked = pick_promo_image()
    assert picked is not None
    assert picked["direct_url"].endswith("one.jpg")


def test_build_flywheel_x_caption_includes_erome(monkeypatch):
    monkeypatch.setenv("TBCC_X_USE_LINKVERTISE", "0")
    monkeypatch.setenv("TBCC_AOF_HUB_INVITE_URL", "https://t.me/+hub")
    text = build_flywheel_x_caption(
        "AOF BIG TITS",
        erome_album_url="https://www.erome.com/a/abc123",
        telegram_invite="https://t.me/+lane",
    )
    assert "Erome" in text or "erome.com" in text
    assert "erome.com/a/abc123" in text
    assert "t.me/+lane" in text
    assert len(text) <= 280
