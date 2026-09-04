"""Approve gate blocks videos with known-bad posters."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def test_operator_approve_blocks_bad_video_poster(monkeypatch):
    from app.services import gatekeeper_review as gk

    media = SimpleNamespace(
        id=88,
        media_type="video",
        status="quarantine",
        pool_id=None,
        classification_json='{"gatekeeper":{"verdict":"quarantine"}}',
        file_unique_id="x",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media

    monkeypatch.setattr(gk, "gatekeeper_verdict_from_media", lambda m: "quarantine")
    monkeypatch.setattr(
        "app.services.video_poster.approve_blocks_bad_video_poster",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.video_poster.cached_thumb_is_usable",
        lambda mid: False,
    )

    out = gk.operator_approve_media(db, 88, operator_id=1)
    assert out["ok"] is False
    assert out["reason"] == "bad_video_poster"
    db.commit.assert_not_called()
