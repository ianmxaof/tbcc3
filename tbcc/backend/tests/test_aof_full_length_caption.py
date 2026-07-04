"""Tests for AOF FULL LENGTH caption + send-time wiring."""

from unittest.mock import MagicMock

from app.models.media import Media
from app.services.aof_full_length_caption import (
    MOVIE_BODY_PLACEHOLDER,
    build_movie_body_for_media,
    full_length_caption_templates,
    inject_movie_body,
)


def test_full_length_templates_include_body_placeholder():
    templates = full_length_caption_templates()
    assert len(templates) >= 4
    assert all(MOVIE_BODY_PLACEHOLDER in t for t in templates)


def test_inject_movie_body():
    body = "STAR NAME🍑🍑🍑\n\n#milf #blonde"
    out = inject_movie_body(f"Header\n\n{MOVIE_BODY_PLACEHOLDER}", body)
    assert "Header" in out
    assert "STAR NAME" in out
    assert MOVIE_BODY_PLACEHOLDER not in out


def test_build_movie_body_title_and_hashtags(monkeypatch):
    media = Media(
        id=42,
        telegram_message_id=1,
        file_id="f1",
        file_unique_id="scene_melony_melons_mp4",
        media_type="video",
        status="approved",
        classification_json='{"lustpress": {"title": "Melony Melons"}}',
    )

    def _fake_rows(db, media_id):
        return [("milf", "milf", "niche", "clip"), ("blonde", "blonde", "niche", "clip")]

    monkeypatch.setattr(
        "app.services.aof_full_length_caption._tag_rows_for_media",
        _fake_rows,
    )
    body = build_movie_body_for_media(MagicMock(), media)
    assert "MELONY MELONS" in body
    assert "#milf" in body
    assert "🔶 milf" in body
