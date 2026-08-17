"""Tests for gatekeeper_prototypes — Phase 3 online CLIP embedding prototype bank.

Synthetic 8-d (or smaller) vectors only — no torch, no real embeddings, no DB.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.gatekeeper_prototypes import (
    cosine_similarity,
    load_centroids,
    maybe_recalc,
    media_is_hard_blocked,
    record_label,
    score_embedding,
)


class _FakeRedis:
    def __init__(self, store: dict[str, str] | None = None):
        self.store = store if store is not None else {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, val, ex=None):
        self.store[key] = val

    def delete(self, key):
        self.store.pop(key, None)


def _patch_redis(monkeypatch, store: dict[str, str] | None = None) -> _FakeRedis:
    fake = _FakeRedis(store)
    monkeypatch.setattr("app.services.gatekeeper_prototypes._redis", lambda: fake)
    return fake


def _label_row(lanes: list[str], embedding: list[float] | None):
    row = MagicMock()
    row.lanes_json = json.dumps(lanes)
    row.embedding_json = json.dumps(embedding) if embedding is not None else None
    return row


# ---------------------------------------------------------------------------
# cosine_similarity — pure math, no numpy
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical_vectors_is_one():
    v = [1.0, 0.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_mismatched_dims_is_zero():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0


def test_cosine_similarity_zero_vector_is_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# record_label — hard block skip, dedupe, cache invalidation
# ---------------------------------------------------------------------------


def test_record_label_skips_hard_blocked_items():
    db = MagicMock()
    out = record_label(
        db, media_id=1, file_unique_id="f1", lanes=["ass"], source="hub_topic", hard_block=True
    )
    assert out == {"ok": False, "skipped": True, "reason": "hard_block"}
    db.add.assert_not_called()


def test_record_label_rolls_back_session_when_dedupe_query_fails(monkeypatch):
    """If gatekeeper_lane_labels doesn't exist yet (island not migrated), the
    dedupe query fails — the session must be rolled back so the caller's
    shared db (apply_gatekeeper_after_ingest / operator_approve_media) isn't
    left in a failed-transaction state for whatever runs after this. The
    dedupe check fails open (assume not-yet-recorded), so the write still
    proceeds on this mock — the point of the test is the rollback call."""
    _patch_redis(monkeypatch)
    db = MagicMock()
    db.query.side_effect = RuntimeError("relation gatekeeper_lane_labels does not exist")

    out = record_label(db, media_id=1, file_unique_id="f1", lanes=["ass"], source="hub_topic")

    assert out["ok"] is True
    db.rollback.assert_called_once()


def test_record_label_rolls_back_session_when_commit_fails(monkeypatch):
    _patch_redis(monkeypatch)
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = []
    db.commit.side_effect = RuntimeError("db unavailable")

    out = record_label(db, media_id=1, file_unique_id="f1", lanes=["ass"], source="hub_topic")

    assert out == {"ok": False, "skipped": True, "reason": "write_failed"}
    db.rollback.assert_called_once()


def test_media_is_hard_blocked_true_for_age_adjacent_warning():
    media = MagicMock()
    media.classification_json = json.dumps(
        {"gatekeeper": {"verdict": "quarantine", "warnings": ["hard_block:age_adjacent"], "blocks": []}}
    )
    assert media_is_hard_blocked(media) is True


def test_media_is_hard_blocked_true_for_zoo_reject():
    media = MagicMock()
    media.classification_json = json.dumps(
        {"gatekeeper": {"verdict": "reject", "warnings": [], "blocks": ["hard_block:zoo"]}}
    )
    assert media_is_hard_blocked(media) is True


def test_media_is_hard_blocked_false_for_clean_approve():
    media = MagicMock()
    media.classification_json = json.dumps({"gatekeeper": {"verdict": "approve", "warnings": [], "blocks": []}})
    assert media_is_hard_blocked(media) is False


def test_record_label_writes_row_with_normalized_lanes(monkeypatch):
    _patch_redis(monkeypatch)
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

    out = record_label(
        db,
        media_id=42,
        file_unique_id="f42",
        lanes=["ASS", "ass", " milf "],
        source="operator_approve",
    )
    assert out["ok"] is True
    assert out["lanes"] == ["ass", "milf"]
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_record_label_dedupes_same_file_source_embedding_state(monkeypatch):
    _patch_redis(monkeypatch)
    db = MagicMock()
    existing = MagicMock()
    existing.embedding_json = None
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = [existing]

    out = record_label(db, media_id=1, file_unique_id="f1", lanes=["ass"], source="hub_topic")
    assert out == {"ok": False, "skipped": True, "reason": "already_recorded"}
    db.add.assert_not_called()


def test_record_label_allows_embedding_upgrade_after_caption_only_row(monkeypatch):
    _patch_redis(monkeypatch)
    db = MagicMock()
    existing = MagicMock()
    existing.embedding_json = None  # caption-only row already recorded
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = [existing]

    out = record_label(
        db, media_id=1, file_unique_id="f1", lanes=["ass"], source="hub_topic", embedding=[1.0] * 8
    )
    assert out["ok"] is True
    assert out["has_embedding"] is True


def test_record_label_invalidates_centroid_cache_on_embedding_write(monkeypatch):
    store = {"tbcc:gk:centroids": json.dumps({"stale": True})}
    _patch_redis(monkeypatch, store)
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

    record_label(
        db, media_id=1, file_unique_id="f1", lanes=["ass"], source="hub_topic", embedding=[1.0] * 8
    )
    assert "tbcc:gk:centroids" not in store


def test_operator_reject_never_moves_a_centroid(monkeypatch):
    store = {"tbcc:gk:centroids": json.dumps({"ass": {"sum": [1.0], "count": 1}})}
    _patch_redis(monkeypatch, store)
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

    out = record_label(db, media_id=1, file_unique_id="f1", lanes=[], source="operator_reject")
    assert out["ok"] is True
    assert out["lanes"] == []
    assert out["has_embedding"] is False
    # No embedding, no lanes -> nothing could have moved, cache left untouched.
    assert "tbcc:gk:centroids" in store


# ---------------------------------------------------------------------------
# Centroids — running sum/count, cache-miss scan, cache-hit skip
# ---------------------------------------------------------------------------


def test_running_sum_and_count_matches_manual_centroid(monkeypatch):
    monkeypatch.setenv("TBCC_GATEKEEPER_PROTOTYPE_MIN", "2")
    _patch_redis(monkeypatch)
    db = MagicMock()
    rows = [
        _label_row(["ass"], [1.0, 0.0, 0.0, 0.0]),
        _label_row(["ass"], [0.0, 1.0, 0.0, 0.0]),
        _label_row(["milf"], [0.0, 0.0, 1.0, 0.0]),  # below PROTOTYPE_MIN, excluded
    ]
    db.query.return_value.filter.return_value.all.return_value = rows

    centroids = load_centroids(db)
    assert "milf" not in centroids
    assert centroids["ass"] == pytest.approx([0.5, 0.5, 0.0, 0.0])


def test_maybe_recalc_returns_cached_sums_without_rescanning(monkeypatch):
    cached_sums = {"ass": {"sum": [2.0, 0.0], "count": 2}}
    store = {"tbcc:gk:centroids": json.dumps(cached_sums)}
    _patch_redis(monkeypatch, store)
    db = MagicMock()
    db.query.side_effect = AssertionError("must not scan on a cache hit")

    out = maybe_recalc(db)
    assert out == cached_sums


def test_score_embedding_ranks_by_cosine(monkeypatch):
    monkeypatch.setenv("TBCC_GATEKEEPER_PROTOTYPE_MIN", "1")
    _patch_redis(monkeypatch)
    db = MagicMock()
    rows = [
        _label_row(["ass"], [1.0, 0.0]),
        _label_row(["milf"], [0.0, 1.0]),
    ]
    db.query.return_value.filter.return_value.all.return_value = rows

    ranked = score_embedding(db, [0.9, 0.1])
    assert ranked[0][0] == "ass"
    assert ranked[0][1] > ranked[1][1]
