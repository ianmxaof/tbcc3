"""Tests for gatekeeper_inbox_split — Phase 2 mixed-bulk inbox auto-split (rule E)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.data.media_gatekeeper_spec import MediaGatekeeperInput, evaluate_media, merge_gatekeeper_json
from app.services.gatekeeper_inbox_split import (
    _is_hard_blocked,
    maybe_auto_split_inbox,
    resolve_proposed_lanes,
)


def _classification_json_for(caption: str, **kwargs) -> str:
    """Build realistic classification_json via the real Phase 1 evaluator."""
    inp = MediaGatekeeperInput(
        media_type=kwargs.pop("media_type", "photo"),
        caption=caption,
        expected_lane=kwargs.pop("expected_lane", "inbox"),
        source_trusted=kwargs.pop("source_trusted", True),
        width=kwargs.pop("width", 1080),
        height=kwargs.pop("height", 1350),
        **kwargs,
    )
    verdict = evaluate_media(inp)
    return json.dumps(merge_gatekeeper_json(None, verdict), ensure_ascii=False)


def _media(caption: str = "", **kwargs) -> MagicMock:
    m = MagicMock()
    m.id = 101
    m.source_channel = "telegram:-1003812457581#topic:22569"
    m.classification_json = _classification_json_for(caption, **kwargs)
    m.filename = ""
    return m


def _db(media: MagicMock) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media
    return db


# ---------------------------------------------------------------------------
# resolve_proposed_lanes — pure blending
# ---------------------------------------------------------------------------


def test_resolve_proposed_lanes_caption_only():
    media = MagicMock(filename="")
    rows = resolve_proposed_lanes(media, None, "#milf drop")
    assert rows
    assert rows[0]["lane"] == "milf"
    assert rows[0]["score"] == 1.0
    assert rows[0]["source"] == "caption"


def test_resolve_proposed_lanes_no_caption_no_clip_empty():
    media = MagicMock(filename="")
    assert resolve_proposed_lanes(media, None, "") == []
    assert resolve_proposed_lanes(media, {}, "plain caption text") == []


def test_resolve_proposed_lanes_clip_uses_real_scores_not_bare_one():
    media = MagicMock(filename="")
    rows = resolve_proposed_lanes(
        media, {"clip_labels": [{"slug": "blowjobs", "score": 0.41}]}, ""
    )
    assert rows == [{"lane": "blowjob", "score": 0.41, "source": "clip"}]


def test_resolve_proposed_lanes_blends_caption_and_clip_marks_mixed():
    media = MagicMock(filename="")
    rows = resolve_proposed_lanes(
        media,
        {"clip_labels": [{"slug": "thick-booty", "score": 0.6}]},
        "#ass drop",
    )
    assert rows[0]["lane"] == "ass"
    # caption exact hit (1.0) beats clip (0.6) but agreement is still recorded
    assert rows[0]["score"] == 1.0
    assert rows[0]["source"] == "mixed"


def test_is_hard_blocked_true_for_age_adjacent_warning():
    gk = {"verdict": "quarantine", "warnings": ["hard_block:age_adjacent"], "blocks": []}
    assert _is_hard_blocked(gk) is True


def test_is_hard_blocked_false_for_clean_quarantine():
    gk = {"verdict": "quarantine", "warnings": ["lane_fit:mismatch"], "blocks": []}
    assert _is_hard_blocked(gk) is False


# ---------------------------------------------------------------------------
# maybe_auto_split_inbox — decision engine
# ---------------------------------------------------------------------------


def _patch_hub_origin(monkeypatch):
    monkeypatch.setattr(
        "app.services.media_gatekeeper.resolve_ingest_origin",
        lambda db, **kw: "storage_hub",
    )


def _patch_scrape_origin(monkeypatch):
    monkeypatch.setattr(
        "app.services.media_gatekeeper.resolve_ingest_origin",
        lambda db, **kw: "scrape",
    )


class _FakeRedis:
    def __init__(self, store: dict[str, str]):
        self.store = store

    def get(self, key):
        return self.store.get(key)

    def set(self, key, val, ex=None):
        self.store[key] = val

    def delete(self, key):
        self.store.pop(key, None)


def _patch_split_redis(monkeypatch) -> dict[str, str]:
    """The split idempotency marker (_split_already_routed/_mark_split_routed)
    talks to Redis, which is unreachable in this test environment — that made
    every prior version of these tests pass even with the guard entirely
    inert (it silently swallows the connection error and always says 'not
    marked yet'). Patch a real fake store so the guard is actually exercised."""
    store: dict[str, str] = {}
    monkeypatch.setattr("app.services.gatekeeper_inbox_split._redis", lambda: _FakeRedis(store))
    return store


def _patch_lane_picker_redis(monkeypatch) -> dict[str, str]:
    store: dict[str, str] = {}
    monkeypatch.setattr("app.services.gatekeeper_lane_picker._redis", lambda: _FakeRedis(store))
    return store


def test_confident_single_lane_auto_routes(monkeypatch):
    _patch_hub_origin(monkeypatch)
    _patch_split_redis(monkeypatch)
    routed = {}
    monkeypatch.setattr(
        "app.services.gatekeeper_review.enqueue_lane_route_for_media",
        lambda mid, lanes: routed.update(media_id=mid, lanes=list(lanes)),
    )
    monkeypatch.setattr(
        "app.services.export_flywheel_service.pool_id_for_network_key",
        lambda db, lane: 8,
    )

    media = _media("#ass drop")
    db = _db(media)
    out = maybe_auto_split_inbox(db, 101, caption="#ass drop")

    assert out["ok"] is True
    assert out["action"] == "auto_route"
    assert out["lane"] == "ass"
    assert routed == {"media_id": 101, "lanes": ["ass"]}
    assert media.status == "approved"
    assert media.pool_id == 8


def test_second_pass_does_not_duplicate_route(monkeypatch):
    """Idempotency guard: apply_gatekeeper_after_ingest calls maybe_auto_split_inbox
    twice per item (ingest-time caption-only, then again once auto_tag_enrich's
    CLIP pass runs) — the second confident decision must not forward again."""
    _patch_hub_origin(monkeypatch)
    _patch_split_redis(monkeypatch)
    call_count = {"n": 0}
    monkeypatch.setattr(
        "app.services.gatekeeper_review.enqueue_lane_route_for_media",
        lambda mid, lanes: call_count.__setitem__("n", call_count["n"] + 1),
    )
    monkeypatch.setattr(
        "app.services.export_flywheel_service.pool_id_for_network_key",
        lambda db, lane: 8,
    )

    media = _media("#ass drop")
    db = _db(media)
    first = maybe_auto_split_inbox(db, 101, caption="#ass drop")
    second = maybe_auto_split_inbox(
        db, 101, caption="#ass drop", enrich={"clip_labels": [{"slug": "thick-booty", "score": 0.9}]}
    )

    assert first["action"] == "auto_route"
    assert second["skipped"] is True
    assert second["reason"] == "already_routed"
    assert call_count["n"] == 1


def test_two_strong_lanes_quarantine_with_both_preselected(monkeypatch):
    _patch_hub_origin(monkeypatch)
    _patch_split_redis(monkeypatch)
    _patch_lane_picker_redis(monkeypatch)

    media = _media("#curvy pic")
    db = _db(media)
    out = maybe_auto_split_inbox(db, 101, caption="#curvy pic")

    assert out["ok"] is True
    assert out["action"] == "quarantine_preselect"
    assert set(out["lanes"]) == {"ass", "big_tits"}


def test_clip_down_milf_caption_confidence_one_may_auto_route(monkeypatch):
    _patch_hub_origin(monkeypatch)
    _patch_split_redis(monkeypatch)
    routed = {}
    monkeypatch.setattr(
        "app.services.gatekeeper_review.enqueue_lane_route_for_media",
        lambda mid, lanes: routed.update(lanes=list(lanes)),
    )
    monkeypatch.setattr(
        "app.services.export_flywheel_service.pool_id_for_network_key",
        lambda db, lane: None,
    )

    media = _media("#milf")
    db = _db(media)
    out = maybe_auto_split_inbox(db, 101, caption="#milf", enrich=None)

    assert out["action"] == "auto_route"
    assert out["lane"] == "milf"
    assert routed == {"lanes": ["milf"]}


def test_clip_down_untagged_caption_does_not_auto_route(monkeypatch):
    _patch_hub_origin(monkeypatch)
    _patch_split_redis(monkeypatch)

    media = _media("")
    db = _db(media)
    out = maybe_auto_split_inbox(db, 101, caption="", enrich=None)

    assert out["ok"] is False
    assert out["skipped"] is True
    assert out["reason"] == "no_signal"


def test_already_approved_untagged_inbox_still_enters_split(monkeypatch):
    """Cursor ACK constraint: untagged trusted inbox already reaches verdict=approve
    at quality ~75 — the split hook must not bail early just because it's approved."""
    _patch_hub_origin(monkeypatch)
    _patch_split_redis(monkeypatch)
    routed = {}
    monkeypatch.setattr(
        "app.services.gatekeeper_review.enqueue_lane_route_for_media",
        lambda mid, lanes: routed.update(lanes=list(lanes)),
    )
    monkeypatch.setattr(
        "app.services.export_flywheel_service.pool_id_for_network_key",
        lambda db, lane: None,
    )

    media = _media("")  # empty caption -> verdict is "approve" per Phase 1 baseline
    gk = json.loads(media.classification_json)["gatekeeper"]
    assert gk["verdict"] == "approve"

    db = _db(media)
    # CLIP came back later (auto_tag_enrich pass) with a confident single label.
    out = maybe_auto_split_inbox(
        db, 101, caption="", enrich={"clip_labels": [{"slug": "blowjobs", "score": 0.9}]}
    )

    assert out["action"] == "auto_route"
    assert out["lane"] == "blowjob"
    assert routed == {"lanes": ["blowjob"]}


def test_scrape_origin_never_auto_splits(monkeypatch):
    _patch_scrape_origin(monkeypatch)
    _patch_split_redis(monkeypatch)

    media = _media("#ass drop")
    db = _db(media)
    out = maybe_auto_split_inbox(db, 101, caption="#ass drop")

    assert out["ok"] is False
    assert out["reason"] == "not_trusted_hub_origin"


def test_age_adjacent_never_auto_routes(monkeypatch):
    _patch_hub_origin(monkeypatch)
    _patch_split_redis(monkeypatch)

    media = _media("jailbait seller proof #ass")
    db = _db(media)
    out = maybe_auto_split_inbox(db, 101, caption="jailbait seller proof #ass")

    assert out["ok"] is False
    assert out["reason"] == "hard_block"


def test_video_with_no_clip_labels_takes_caption_only_branch(monkeypatch):
    """No thumb bytes upstream -> caller passes no clip_labels -> caption-only,
    no download attempted anywhere in this module."""
    _patch_hub_origin(monkeypatch)
    _patch_split_redis(monkeypatch)
    routed = {}
    monkeypatch.setattr(
        "app.services.gatekeeper_review.enqueue_lane_route_for_media",
        lambda mid, lanes: routed.update(lanes=list(lanes)),
    )
    monkeypatch.setattr(
        "app.services.export_flywheel_service.pool_id_for_network_key",
        lambda db, lane: None,
    )

    media = _media("#blowjob clip", media_type="video", duration_seconds=15.0)
    db = _db(media)
    out = maybe_auto_split_inbox(db, 101, caption="#blowjob clip", enrich=None)

    assert out["action"] == "auto_route"
    assert out["lane"] == "blowjob"


# ---------------------------------------------------------------------------
# apply_gatekeeper_after_ingest hook — split must suppress the quarantine card
# ---------------------------------------------------------------------------


def test_auto_routed_item_does_not_also_post_quarantine_review(monkeypatch):
    """Ordering bug guard: split runs before (and can suppress) the quarantine
    review enqueue. Without the fix, a tagged inbox item that auto-routes would
    still get a review card whose Approve tap re-forwards + re-approves it."""
    from app.services.media_gatekeeper import apply_gatekeeper_after_ingest

    _patch_hub_origin(monkeypatch)
    _patch_split_redis(monkeypatch)
    monkeypatch.setattr(
        "app.services.gatekeeper_review.enqueue_lane_route_for_media",
        lambda mid, lanes: None,
    )
    monkeypatch.setattr(
        "app.services.export_flywheel_service.pool_id_for_network_key",
        lambda db, lane: None,
    )
    review_calls = {"n": 0}
    monkeypatch.setattr(
        "app.services.gatekeeper_review.enqueue_quarantine_review",
        lambda mid: review_calls.__setitem__("n", review_calls["n"] + 1),
    )

    media = MagicMock()
    media.id = 101
    media.media_type = "photo"
    media.source_channel = "telegram:-1003812457581#topic:22569"
    media.pool_id = None
    media.file_unique_id = "x101"
    media.nsfw_tier = None
    media.classification_json = None
    media.filename = ""

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media

    out = apply_gatekeeper_after_ingest(db, 101, caption="#ass drop")

    # Tagged inbox item -> gatekeeper verdict alone is "quarantine" (lane_mismatch
    # against expected="inbox"), but caption_confidence=1.0 auto-routes it.
    assert out["verdict"] == "quarantine"
    assert review_calls["n"] == 0
