"""Video deposits were never classified: _fetch_classify_bytes_sync already
samples an ffmpeg frame for video (media_frame_sample.extract_video_frame_jpeg),
but run_auto_tag_enrich_for_media's img_for_clip gate only invited
photo/gif/empty media_type — "video" was silently excluded (2026-08-22 finding,
confirmed live: an all-video test batch enriched in <100ms with zero fetch
attempts, vs. ~2.9s for a real photo classify)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _fake_session(media_row):
    session = MagicMock()
    query = MagicMock()
    query.filter.return_value.first.return_value = media_row
    session.query.return_value = query
    session.close.return_value = None
    session.commit.return_value = None
    return session


def _media_row(**overrides):
    base = dict(
        id=0,
        media_type="photo",
        source_channel="",
        classification_json=None,
        nsfw_tier=None,
        tags=None,
        pool_id=None,
        status="pending",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch_common(monkeypatch, auto_tag_enrich, media_row):
    monkeypatch.setattr(auto_tag_enrich, "enrich_pipeline_enabled", lambda: True)
    monkeypatch.setattr("app.database.session.SessionLocal", lambda: _fake_session(media_row))
    monkeypatch.setattr("app.services.focus_profile.pause_auto_tag_work", lambda: False)
    monkeypatch.setattr("app.services.lustpress_metadata.lustpress_enabled", lambda: False)
    monkeypatch.setattr("app.services.nsfw_classifier.nsfw_classifier_enabled", lambda: False)
    monkeypatch.setattr(
        "app.services.media_pool_routing.try_assign_pool_from_tags",
        lambda db, mid: {"applied": False},
    )
    monkeypatch.setattr(
        "app.services.media_gatekeeper.apply_gatekeeper_after_ingest", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.services.media_gatekeeper.should_attempt_storage_auto_approve", lambda *a, **k: False
    )
    # _should_enqueue_llm can trip True on minimal fake data — enqueue_auto_tag_llm_if_enabled
    # would then attempt a real Celery .delay() and hang on broker connect in tests.
    monkeypatch.setattr("app.services.auto_tag_llm.enqueue_auto_tag_llm_if_enabled", lambda *a, **k: None)


def test_video_media_triggers_classify_byte_fetch(monkeypatch):
    from app.services import auto_tag_enrich

    media_row = _media_row(id=101, media_type="video", source_channel="telegram:-1003812457581#topic:22569")
    _patch_common(monkeypatch, auto_tag_enrich, media_row)

    fetch_calls = []

    def fake_fetch(mid):
        fetch_calls.append(mid)
        return b"fake-jpeg-frame-bytes"

    monkeypatch.setattr(auto_tag_enrich, "_fetch_classify_bytes_sync", fake_fetch)

    classify_calls = []
    monkeypatch.setattr(
        "app.services.media_lane_vision_classify.classify_and_log_lane_vision",
        lambda db, mid, img_bytes, **k: classify_calls.append((mid, img_bytes)) or None,
    )

    with patch.object(auto_tag_enrich, "_maybe_auto_route_vision_lane"):
        out = auto_tag_enrich.run_auto_tag_enrich_for_media(101)

    assert out["ok"] is True
    assert fetch_calls == [101]
    assert classify_calls == [(101, b"fake-jpeg-frame-bytes")]


def test_photo_media_still_triggers_classify_byte_fetch(monkeypatch):
    """Guard against the fix narrowing the gate instead of widening it."""
    from app.services import auto_tag_enrich

    media_row = _media_row(id=202, media_type="photo", source_channel="telegram:-1003812457581#topic:3058")
    _patch_common(monkeypatch, auto_tag_enrich, media_row)

    fetch_calls = []
    monkeypatch.setattr(
        auto_tag_enrich, "_fetch_classify_bytes_sync", lambda mid: fetch_calls.append(mid) or b"x"
    )
    monkeypatch.setattr(
        "app.services.media_lane_vision_classify.classify_and_log_lane_vision",
        lambda db, mid, img_bytes, **k: None,
    )

    with patch.object(auto_tag_enrich, "_maybe_auto_route_vision_lane"):
        auto_tag_enrich.run_auto_tag_enrich_for_media(202)

    assert fetch_calls == [202]


def test_document_media_type_still_excluded(monkeypatch):
    """Only photo/gif/empty/video should trigger the lazy fetch — not e.g. "document"."""
    from app.services import auto_tag_enrich

    media_row = _media_row(id=303, media_type="document", source_channel="telegram:-1003812457581#topic:5980")
    _patch_common(monkeypatch, auto_tag_enrich, media_row)

    fetch_calls = []
    monkeypatch.setattr(
        auto_tag_enrich, "_fetch_classify_bytes_sync", lambda mid: fetch_calls.append(mid) or b"x"
    )

    with patch.object(auto_tag_enrich, "_maybe_auto_route_vision_lane"):
        auto_tag_enrich.run_auto_tag_enrich_for_media(303)

    assert fetch_calls == []
