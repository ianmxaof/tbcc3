"""Loot roll candidate deliverability filters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.media import Media
from app.services.loot_media_deliverable import (
    filter_roll_candidates,
    is_loot_media_roll_candidate,
    loot_media_has_local_bytes,
)


def _row(
    *,
    mid: int,
    tg: int,
    fid: str = "x",
    status: str = "approved",
    tags: str = "",
    source_channel: str = "",
) -> Media:
    m = MagicMock(spec=Media)
    m.id = mid
    m.telegram_message_id = tg
    m.file_id = fid
    m.status = status
    m.tags = tags
    m.source_channel = source_channel
    return m


def test_saved_message_ref_excluded_under_local_only_default():
    with patch("app.services.loot_media_deliverable.loot_local_bytes_only", return_value=True):
        assert is_loot_media_roll_candidate(_row(mid=1, tg=100)) is False


def test_saved_message_ref_allowed_in_legacy_mode():
    with patch("app.services.loot_media_deliverable.loot_local_bytes_only", return_value=False):
        assert is_loot_media_roll_candidate(_row(mid=1, tg=100)) is True


def test_local_without_bytes_excluded():
    row = _row(mid=2, tg=0, fid="local:abc.jpg")
    with patch("app.services.loot_media_deliverable.loot_media_has_local_bytes", return_value=False):
        assert is_loot_media_roll_candidate(row) is False


def test_local_with_bytes_included():
    row = _row(mid=3, tg=0, fid="local:abc.jpg")
    with patch("app.services.loot_media_deliverable.loot_media_has_local_bytes", return_value=True):
        assert is_loot_media_roll_candidate(row) is True


def test_sent_vault_recycle_is_candidate_even_when_local_only():
    from app.services.loot_media_deliverable import loot_telegram_fetch_peer

    row = _row(mid=4, tg=9001, tags="sent_vault_recycled")
    with patch("app.services.loot_media_deliverable.loot_local_bytes_only", return_value=True):
        with patch("app.services.loot_media_deliverable.loot_media_has_local_bytes", return_value=False):
            assert is_loot_media_roll_candidate(row) is True
    assert loot_telegram_fetch_peer(row) != "me"


def test_filter_roll_candidates():
    rows = [_row(mid=1, tg=0, fid="local:a"), _row(mid=2, tg=50)]
    with patch(
        "app.services.loot_media_deliverable.is_loot_media_roll_candidate",
        side_effect=lambda r: int(r.id) == 2,
    ):
        out = filter_roll_candidates(rows)
    assert [int(r.id) for r in out] == [2]
