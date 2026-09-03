"""Tag-only backfill: selection query + tag-only re-enrich (no routing/approve side effects)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.media import Media
from app.services.tag_backfill import find_thin_tag_media


def _media(**over):
    base = dict(
        telegram_message_id=1,
        file_id="f",
        file_unique_id="u",
        media_type="photo",
        source_channel="storage_hub:milf",
        tags=None,
        pool_id=8,
        status="approved",
        classification_json=None,
    )
    base.update(over)
    return Media(**base)


def test_find_thin_tag_media_matches_empty_tags(db):
    db.add(_media(file_unique_id="a", tags=None))
    db.commit()
    ids = find_thin_tag_media(db, limit=10)
    assert len(ids) == 1


def test_find_thin_tag_media_skips_rich_tags(db):
    db.add(_media(file_unique_id="b", tags="milf, office, thick, pawg, real"))
    db.commit()
    ids = find_thin_tag_media(db, limit=10, thin_chars=24)
    assert ids == []


def test_find_thin_tag_media_skips_pending(db):
    db.add(_media(file_unique_id="c", tags=None, status="pending"))
    db.commit()
    assert find_thin_tag_media(db, limit=10) == []


def test_find_thin_tag_media_skips_already_backfilled(db):
    db.add(_media(file_unique_id="d", tags=None, classification_json='{"tag_backfill_done": true}'))
    db.commit()
    assert find_thin_tag_media(db, limit=10) == []


def test_find_thin_tag_media_pool_filter(db):
    db.add(_media(file_unique_id="e", tags=None, pool_id=8))
    db.add(_media(file_unique_id="f", tags=None, pool_id=9))
    db.commit()
    ids = find_thin_tag_media(db, limit=10, pool_id=9)
    assert len(ids) == 1


def test_run_tag_backfill_for_media_not_found():
    from app.services.auto_tag_enrich import run_tag_backfill_for_media

    with patch("app.database.session.SessionLocal") as session_local:
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        session_local.return_value = session
        out = run_tag_backfill_for_media(999)
    assert out["ok"] is False
    assert out["error"] == "not_found"


def test_run_tag_backfill_never_calls_gatekeeper_or_pool_routing(monkeypatch):
    """Backfill must never re-decide lane/approve for already-settled media."""
    from app.services.auto_tag_enrich import run_tag_backfill_for_media

    monkeypatch.setenv("TBCC_TAG_BACKFILL_LLM", "0")
    m = _media(file_unique_id="g")
    m.id = 1
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = m

    with (
        patch("app.database.session.SessionLocal", return_value=session),
        patch("app.services.lustpress_metadata.lustpress_enabled", return_value=False),
        patch("app.services.nsfw_classifier.nsfw_classifier_enabled", return_value=False),
        patch("app.services.auto_tag_enrich._fetch_classify_bytes_sync", return_value=None),
        patch("app.services.media_niche_classify.classify_image_bytes_niche") as clip_classify,
        patch("app.services.media_gatekeeper.apply_gatekeeper_after_ingest") as gatekeeper,
        patch("app.services.media_pool_routing.try_assign_pool_from_tags") as pool_route,
    ):
        out = run_tag_backfill_for_media(1)

    assert out["ok"] is True
    gatekeeper.assert_not_called()
    pool_route.assert_not_called()
    clip_classify.assert_not_called()  # no image bytes available, CLIP gate short-circuits
    assert m.classification_json and "tag_backfill_done" in m.classification_json
