"""Tests for weekly VIP mega public tease."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from app.services.aof_vip_weekly_mega import (
    build_weekly_mega_public_tease_caption_html,
    vip_weekly_mega_public_tease_enabled,
)


def test_public_tease_enabled_by_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TBCC_VIP_WEEKLY_MEGA_PUBLIC_TEASE_ENABLED", None)
        assert vip_weekly_mega_public_tease_enabled() is True


def test_public_tease_caption_mentions_vip_and_gate():
    mod = MagicMock(label="TABOO Week 12", target_url="https://linkvertise.com/123")
    html = build_weekly_mega_public_tease_caption_html(MagicMock(), mod, "https://linkvertise.com/123")
    assert "VIP" in html
    assert "gated preview" in html
    assert "/subscribe" in html
