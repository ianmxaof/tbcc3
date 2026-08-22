"""_post_media_ingest is the single funnel point for all Telegram-sourced deposit
ingest paths (channel index, direct message index, local-pool import). It must
enqueue the enrich/classify hook for every one of them — previously two of the
three call sites never triggered classify at all (2026-08-22 regression)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _fake_db():
    db = MagicMock()
    db.refresh = MagicMock()
    return db


def test_post_media_ingest_enqueues_enrich_for_new_media():
    from app.services.telegram_storage import _post_media_ingest

    db = _fake_db()
    record = SimpleNamespace(id=101)

    with patch("app.services.media_gatekeeper.apply_gatekeeper_after_ingest"), \
         patch("app.services.media_gatekeeper.should_attempt_storage_auto_approve", return_value=False), \
         patch("app.services.auto_tag_enrich.enqueue_auto_tag_enrich_if_enabled") as enrich:
        _post_media_ingest(db, record, caption="c", message=None, source_label="src")

    enrich.assert_called_once_with(101)


def test_post_media_ingest_enrich_failure_does_not_raise():
    from app.services.telegram_storage import _post_media_ingest

    db = _fake_db()
    record = SimpleNamespace(id=202)

    with patch("app.services.media_gatekeeper.apply_gatekeeper_after_ingest"), \
         patch("app.services.media_gatekeeper.should_attempt_storage_auto_approve", return_value=False), \
         patch(
             "app.services.auto_tag_enrich.enqueue_auto_tag_enrich_if_enabled",
             side_effect=RuntimeError("boom"),
         ):
        _post_media_ingest(db, record, caption="c", message=None, source_label="src")  # must not raise


def test_post_media_ingest_gatekeeper_failure_still_attempts_enrich():
    """Gatekeeper and enrich are independent try/except blocks — one failing
    must not prevent the other from running."""
    from app.services.telegram_storage import _post_media_ingest

    db = _fake_db()
    record = SimpleNamespace(id=303)

    with patch(
        "app.services.media_gatekeeper.apply_gatekeeper_after_ingest",
        side_effect=RuntimeError("gatekeeper down"),
    ), patch("app.services.auto_tag_enrich.enqueue_auto_tag_enrich_if_enabled") as enrich:
        _post_media_ingest(db, record, caption="c", message=None, source_label="src")

    enrich.assert_called_once_with(303)
