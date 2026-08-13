"""Tests for VIP-exclusive public delay."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.aof_vip_exclusive import (
    filter_media_for_public_vip_exclusive,
    media_eligible_for_public_exclusive,
    vip_exclusive_delay_days,
)


def test_vip_exclusive_delay_default_two_days():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TBCC_VIP_EXCLUSIVE_DELAY_DAYS", None)
        assert vip_exclusive_delay_days() == 2


def test_media_eligible_when_older_than_cutoff():
    cutoff = datetime.utcnow() - timedelta(days=2)
    media = MagicMock(created_at=datetime.utcnow() - timedelta(days=5))
    assert media_eligible_for_public_exclusive(media, cutoff=cutoff) is True


def test_media_not_eligible_when_newer_than_cutoff():
    cutoff = datetime.utcnow() - timedelta(days=2)
    media = MagicMock(created_at=datetime.utcnow())
    assert media_eligible_for_public_exclusive(media, cutoff=cutoff) is False


def test_filter_skips_non_mirror_pool():
    pool = MagicMock(name="AOF VIP POOL")
    rows = [MagicMock(created_at=datetime.utcnow())]
    out = filter_media_for_public_vip_exclusive(rows, pool=pool)
    assert out == rows


@patch("app.services.aof_vip_exclusive.is_vip_mirror_pool", return_value=True)
@patch("app.services.aof_vip_exclusive.public_exclusive_cutoff_utc")
def test_filter_drops_new_media_on_mirror_pool(mock_cutoff, _mock_mirror):
    mock_cutoff.return_value = datetime.utcnow() - timedelta(days=2)
    old = MagicMock(created_at=datetime.utcnow() - timedelta(days=5))
    new = MagicMock(created_at=datetime.utcnow())
    pool = MagicMock(name="AOF BIG TITS POOL")
    out = filter_media_for_public_vip_exclusive([old, new], pool=pool)
    assert out == [old]
