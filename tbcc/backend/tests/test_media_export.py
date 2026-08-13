"""TBCC /media/export for aof-forum ingest bridge."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.api.media import (
    _apply_storage_hub_export_filter,
    _clamp_export_limit,
    export_media_for_hub,
)
from app.middleware.internal_api_auth import path_is_public


def test_media_export_not_public_get() -> None:
    assert not path_is_public("/media/export", "GET")
    assert path_is_public("/media/123/file", "GET")
    assert path_is_public("/media/123/thumbnail", "GET")


def test_clamp_export_limit() -> None:
    assert _clamp_export_limit(None) == 20
    assert _clamp_export_limit(5) == 5
    assert _clamp_export_limit(999) == 50
    assert _clamp_export_limit(0) == 1


def test_export_media_for_hub_shape() -> None:
    m1 = SimpleNamespace(
        id=11,
        source_channel="telegram:-1003927742839",
        media_type="photo",
        telegram_message_id=42,
        file_unique_id="abc",
        tags="test",
        pool_id=3,
        status="approved",
    )
    m2 = SimpleNamespace(
        id=12,
        source_channel=None,
        media_type="video",
        telegram_message_id=43,
        file_unique_id="def",
        tags=None,
        pool_id=None,
        status="approved",
    )

    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [m1, m2]

    db = MagicMock()
    db.query.return_value = q

    with patch("app.api.media._pool_name_for_export_row", return_value="AOF LOOT ROOM POOL"):
        with patch("app.api.media._network_key_for_export_row", return_value="main"):
            out = export_media_for_hub(db=db, since_id=10, limit=20, status="approved")
    assert out["count"] == 2
    assert out["next_since_id"] == 12
    assert out["items"][0]["id"] == 11
    assert out["items"][0]["file_path"] == "/media/11/file"
    assert out["items"][0]["pool_name"] == "AOF LOOT ROOM POOL"
    assert out["items"][0]["network_key"] == "main"
    assert out["items"][1]["file_path"] == "/media/12/file"

    q.filter.assert_called()
    filt = q.filter.call_args[0][0]
    assert filt is not None


def test_export_media_for_hub_storage_hub_origin() -> None:
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []

    db = MagicMock()
    db.query.return_value = q

    with patch("app.api.media._apply_storage_hub_export_filter", side_effect=lambda query, _db: query):
        export_media_for_hub(db=db, since_id=0, limit=10, origin="storage_hub")
    assert q.filter.call_count >= 2
