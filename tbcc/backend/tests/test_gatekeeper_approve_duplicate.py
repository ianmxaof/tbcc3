"""operator_approve_media must not crash on a duplicate (file_unique_id, pool_id) row —
treat it as already-approved/skip instead of surfacing a raw IntegrityError."""

from __future__ import annotations

import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import IntegrityError

from app.services.gatekeeper_review import (
    _is_duplicate_file_unique_id_pool_id_violation,
    operator_approve_media,
)


def _dup_integrity_error(msg: str) -> IntegrityError:
    return IntegrityError("UPDATE media ...", {}, Exception(msg))


def _mock_celery_side_effects():
    """Approve fires several unconditional Celery .delay() enqueues (vault archive,
    QA live counter, lane route). A cold import of app.workers.celery_app can block
    trying to reach a broker this test environment can't route to — mock every one
    so this unit test never touches real infra, matching enqueue_micro_pull_for_lane's
    existing mock pattern in test_gatekeeper_review.py."""
    return (
        patch("app.services.gatekeeper_review.enqueue_micro_pull_for_lane"),
        patch(
            "app.services.gatekeeper_review.enqueue_lane_route_for_media",
            return_value={"ok": True, "queued": True},
        ),
        patch("app.services.gatekeeper_review.enqueue_vault_approved_media"),
        patch("app.services.gatekeeper_review._refresh_qa_live_counter_after_decide"),
    )


def test_detects_postgres_named_constraint():
    err = _dup_integrity_error(
        'duplicate key value violates unique constraint "uq_media_file_unique_id_pool_id"'
    )
    assert _is_duplicate_file_unique_id_pool_id_violation(err) is True


def test_detects_sqlite_column_message():
    err = _dup_integrity_error("UNIQUE constraint failed: media.file_unique_id, media.pool_id")
    assert _is_duplicate_file_unique_id_pool_id_violation(err) is True


def test_does_not_match_unrelated_integrity_error():
    err = _dup_integrity_error("NOT NULL constraint failed: media.channel_id")
    assert _is_duplicate_file_unique_id_pool_id_violation(err) is False


def test_approve_skips_route_on_duplicate_instead_of_raising():
    media = MagicMock()
    media.id = 10
    media.status = "pending"
    media.pool_id = 3
    media.source_channel = "-1003271959583"
    media.classification_json = json.dumps({"gatekeeper": {"verdict": "quarantine"}})

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media
    commit_calls = {"n": 0}

    def _commit_side_effect():
        commit_calls["n"] += 1
        if commit_calls["n"] == 1:
            raise _dup_integrity_error(
                'duplicate key value violates unique constraint "uq_media_file_unique_id_pool_id"'
            )
        return None

    db.commit.side_effect = _commit_side_effect

    with ExitStack() as stack:
        for cm in _mock_celery_side_effects():
            stack.enter_context(cm)
        out = operator_approve_media(db, 10, operator_id=7787282561, lane_keys=["milf"])

    assert out["ok"] is True
    assert out["duplicate_route_skipped"] is True
    assert media.status == "approved"
    assert media.pool_id is None  # conflicting route dropped, not force-assigned
    db.rollback.assert_called_once()
    assert db.commit.call_count >= 2  # first (failed) + retry; downstream cleanup may commit too


def test_approve_reraises_unrelated_integrity_error():
    media = MagicMock()
    media.id = 10
    media.status = "pending"
    media.pool_id = 3
    media.source_channel = "-1003271959583"
    media.classification_json = json.dumps({"gatekeeper": {"verdict": "quarantine"}})

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media
    db.commit.side_effect = _dup_integrity_error("NOT NULL constraint failed: media.channel_id")

    try:
        operator_approve_media(db, 10, operator_id=7787282561, lane_keys=["milf"])
        raised = False
    except IntegrityError:
        raised = True
    assert raised is True


def test_approve_normal_path_unaffected():
    media = MagicMock()
    media.id = 10
    media.status = "pending"
    media.pool_id = 8
    media.source_channel = "-1003271959583"
    media.classification_json = json.dumps({"gatekeeper": {"verdict": "quarantine"}})

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media

    with ExitStack() as stack:
        for cm in _mock_celery_side_effects():
            stack.enter_context(cm)
        out = operator_approve_media(db, 10, operator_id=7787282561, lane_keys=["milf"])

    assert out["ok"] is True
    assert out["duplicate_route_skipped"] is False
    assert media.status == "approved"
    db.rollback.assert_not_called()
    assert db.commit.call_count >= 1
